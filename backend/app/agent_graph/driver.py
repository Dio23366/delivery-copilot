from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any


AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION = (
    "agent_graph_single_step_driver_v0.1"
)


class AgentGraphSingleStepDriverError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentGraphSingleStepResult:
    node_name: str
    node_update: Mapping[str, object]
    before_next: tuple[str, ...]
    after_next: tuple[str, ...]
    before_values: Mapping[str, object]
    after_values: Mapping[str, object]
    driver_version: str = (
        AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "driver_version": self.driver_version,
            "node_name": self.node_name,
            "node_update": _thaw_json_value(
                self.node_update
            ),
            "before_next": list(self.before_next),
            "after_next": list(self.after_next),
            "before_values": _thaw_json_value(
                self.before_values
            ),
            "after_values": _thaw_json_value(
                self.after_values
            ),
        }


class AgentGraphSingleStepDriver:
    def execute_next_node(
        self,
        compiled_graph: object,
        *,
        thread_config: Mapping[str, object],
        expected_node: str,
    ) -> AgentGraphSingleStepResult:
        graph = self._validate_compiled_graph(
            compiled_graph
        )
        normalized_config = self._validate_thread_config(
            thread_config
        )
        normalized_expected_node = (
            self._validate_expected_node(expected_node)
        )

        before_snapshot = graph.get_state(
            normalized_config
        )
        before_next = self._snapshot_next(
            before_snapshot,
            phase="before",
        )
        self._validate_scheduled_node(
            before_next,
            expected_node=normalized_expected_node,
        )
        before_values = self._snapshot_values(
            before_snapshot,
            phase="before",
        )

        matching_updates: list[Mapping[str, object]] = []

        for event in graph.stream(
            None,
            normalized_config,
            stream_mode="updates",
            interrupt_after=[
                normalized_expected_node,
            ],
        ):
            if (
                isinstance(event, Mapping)
                and normalized_expected_node in event
            ):
                update = event[
                    normalized_expected_node
                ]
                if not isinstance(update, Mapping):
                    raise AgentGraphSingleStepDriverError(
                        error_code="invalid_node_update",
                        message=(
                            "The scheduled node update must "
                            "be a mapping."
                        ),
                    )
                matching_updates.append(
                    self._freeze_mapping(
                        update,
                        field_name="node_update",
                    )
                )

        if not matching_updates:
            raise AgentGraphSingleStepDriverError(
                error_code="missing_node_update",
                message=(
                    "The graph stream did not emit an update "
                    "for the scheduled node."
                ),
            )

        if len(matching_updates) != 1:
            raise AgentGraphSingleStepDriverError(
                error_code="duplicate_node_update",
                message=(
                    "The graph stream emitted more than one "
                    "update for the scheduled node."
                ),
            )

        node_update = matching_updates[0]
        after_snapshot = graph.get_state(
            normalized_config
        )
        after_next = self._snapshot_next(
            after_snapshot,
            phase="after",
        )
        after_values = self._snapshot_values(
            after_snapshot,
            phase="after",
        )

        return AgentGraphSingleStepResult(
            node_name=normalized_expected_node,
            node_update=node_update,
            before_next=before_next,
            after_next=after_next,
            before_values=before_values,
            after_values=after_values,
        )

    @staticmethod
    def _validate_compiled_graph(
        compiled_graph: object,
    ) -> Any:
        if compiled_graph is None:
            raise TypeError(
                "compiled_graph must not be None"
            )

        for method_name in (
            "get_state",
            "stream",
        ):
            if not callable(
                getattr(
                    compiled_graph,
                    method_name,
                    None,
                )
            ):
                raise TypeError(
                    "compiled_graph must provide callable "
                    f"{method_name}()"
                )

        return compiled_graph

    @staticmethod
    def _validate_thread_config(
        thread_config: Mapping[str, object],
    ) -> dict[str, object]:
        if not isinstance(thread_config, Mapping):
            raise AgentGraphSingleStepDriverError(
                error_code="invalid_thread_config",
                message="thread_config must be a mapping.",
            )

        configurable = thread_config.get(
            "configurable"
        )
        if not isinstance(configurable, Mapping):
            raise AgentGraphSingleStepDriverError(
                error_code="invalid_thread_config",
                message=(
                    "thread_config.configurable must be "
                    "a mapping."
                ),
            )

        thread_id = configurable.get("thread_id")
        if (
            not isinstance(thread_id, str)
            or not thread_id.strip()
            or thread_id != thread_id.strip()
        ):
            raise AgentGraphSingleStepDriverError(
                error_code="missing_thread_id",
                message=(
                    "thread_config must contain a normalized "
                    "nonblank configurable.thread_id."
                ),
            )

        if "checkpoint_id" in configurable:
            raise AgentGraphSingleStepDriverError(
                error_code="checkpoint_id_not_allowed",
                message=(
                    "thread_config must not pin a historical "
                    "checkpoint_id."
                ),
            )

        if "checkpoint_ns" in configurable:
            raise AgentGraphSingleStepDriverError(
                error_code="checkpoint_ns_not_allowed",
                message=(
                    "thread_config must not provide a custom "
                    "checkpoint_ns."
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
            }
        }

    @staticmethod
    def _validate_expected_node(
        expected_node: str,
    ) -> str:
        if (
            not isinstance(expected_node, str)
            or not expected_node.strip()
            or expected_node != expected_node.strip()
        ):
            raise AgentGraphSingleStepDriverError(
                error_code="invalid_expected_node",
                message=(
                    "expected_node must be a normalized "
                    "nonblank string."
                ),
            )

        return expected_node

    @classmethod
    def _snapshot_next(
        cls,
        snapshot: object,
        *,
        phase: str,
    ) -> tuple[str, ...]:
        raw_next = getattr(snapshot, "next", None)

        if not isinstance(raw_next, (tuple, list)):
            raise AgentGraphSingleStepDriverError(
                error_code="invalid_snapshot_next",
                message=(
                    f"The {phase} graph snapshot next value "
                    "must be a sequence."
                ),
            )

        normalized: list[str] = []
        for node_name in raw_next:
            if (
                not isinstance(node_name, str)
                or not node_name.strip()
                or node_name != node_name.strip()
            ):
                raise AgentGraphSingleStepDriverError(
                    error_code="invalid_snapshot_next",
                    message=(
                        f"The {phase} graph snapshot contains "
                        "an invalid node name."
                    ),
                )
            normalized.append(node_name)

        return tuple(normalized)

    @staticmethod
    def _validate_scheduled_node(
        scheduled_nodes: tuple[str, ...],
        *,
        expected_node: str,
    ) -> None:
        if not scheduled_nodes:
            raise AgentGraphSingleStepDriverError(
                error_code="no_scheduled_node",
                message=(
                    "The latest graph checkpoint does not "
                    "schedule a node."
                ),
            )

        if len(scheduled_nodes) != 1:
            raise AgentGraphSingleStepDriverError(
                error_code="multiple_scheduled_nodes",
                message=(
                    "The latest graph checkpoint must schedule "
                    "exactly one node."
                ),
            )

        if scheduled_nodes[0] != expected_node:
            raise AgentGraphSingleStepDriverError(
                error_code="unexpected_scheduled_node",
                message=(
                    "The latest graph checkpoint schedules "
                    f"{scheduled_nodes[0]!r}, not "
                    f"{expected_node!r}."
                ),
            )

    @classmethod
    def _snapshot_values(
        cls,
        snapshot: object,
        *,
        phase: str,
    ) -> Mapping[str, object]:
        values = getattr(snapshot, "values", None)
        if not isinstance(values, Mapping):
            raise AgentGraphSingleStepDriverError(
                error_code="invalid_snapshot_values",
                message=(
                    f"The {phase} graph snapshot values must "
                    "be a mapping."
                ),
            )

        return cls._freeze_mapping(
            values,
            field_name=f"{phase}_values",
        )

    @staticmethod
    def _freeze_mapping(
        value: Mapping[str, object],
        *,
        field_name: str,
    ) -> Mapping[str, object]:
        frozen = _freeze_json_value(
            value,
            field_name=field_name,
        )
        if not isinstance(frozen, Mapping):
            raise AssertionError(
                "Frozen mapping contract was violated"
            )
        return frozen


def _freeze_json_value(
    value: object,
    *,
    field_name: str,
) -> object:
    if value is None or type(value) in {
        bool,
        int,
        str,
    }:
        return value

    if type(value) is float:
        if not math.isfinite(value):
            raise AgentGraphSingleStepDriverError(
                error_code="non_json_safe_value",
                message=(
                    f"{field_name} contains a non-finite "
                    "floating-point value."
                ),
            )
        return value

    if isinstance(value, Mapping):
        frozen_items: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise AgentGraphSingleStepDriverError(
                    error_code="non_json_safe_value",
                    message=(
                        f"{field_name} contains a non-string "
                        "mapping key."
                    ),
                )
            frozen_items[key] = _freeze_json_value(
                nested_value,
                field_name=f"{field_name}.{key}",
            )
        return MappingProxyType(frozen_items)

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(
                nested_value,
                field_name=f"{field_name}[]",
            )
            for nested_value in value
        )

    raise AgentGraphSingleStepDriverError(
        error_code="non_json_safe_value",
        message=(
            f"{field_name} contains an unsupported "
            f"JSON value: {type(value).__name__}."
        ),
    )


def _thaw_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _thaw_json_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, tuple):
        return [
            _thaw_json_value(nested_value)
            for nested_value in value
        ]

    return value
