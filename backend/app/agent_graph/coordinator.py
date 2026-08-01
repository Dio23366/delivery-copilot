from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

from app.agent_graph.driver import (
    AgentGraphSingleStepDriver,
    AgentGraphSingleStepDriverError,
    AgentGraphSingleStepResult,
)
from app.agent_graph.state import (
    AGENT_LANGGRAPH_NODES,
    AgentGraphStateContractError,
    build_checkpoint_config,
    validate_agent_graph_state,
)


AGENT_GRAPH_STEP_COORDINATOR_VERSION = (
    "agent_graph_step_coordinator_v0.1"
)


class AgentGraphStepCoordinatorError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        relation: str | None = None,
        inspection: AgentGraphCheckpointInspection | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.relation = relation
        self.inspection = inspection


@dataclass(frozen=True, slots=True)
class AgentGraphCheckpointInspection:
    relation: str
    expected_node: str
    thread_config: Mapping[str, object]
    persisted_state: Mapping[str, object]
    checkpoint_values: Mapping[str, object]
    checkpoint_next: tuple[str, ...]
    coordinator_version: str = (
        AGENT_GRAPH_STEP_COORDINATOR_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "coordinator_version": self.coordinator_version,
            "relation": self.relation,
            "expected_node": self.expected_node,
            "thread_config": _thaw_json_value(
                self.thread_config
            ),
            "persisted_state": _thaw_json_value(
                self.persisted_state
            ),
            "checkpoint_values": _thaw_json_value(
                self.checkpoint_values
            ),
            "checkpoint_next": list(
                self.checkpoint_next
            ),
        }


@dataclass(frozen=True, slots=True)
class AgentGraphStepCoordinationResult:
    inspection: AgentGraphCheckpointInspection
    driver_result: AgentGraphSingleStepResult
    coordinator_version: str = (
        AGENT_GRAPH_STEP_COORDINATOR_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "coordinator_version": self.coordinator_version,
            "inspection": self.inspection.as_dict(),
            "driver_result": self.driver_result.as_dict(),
        }


class AgentGraphStepCoordinator:
    def __init__(
        self,
        *,
        compiled_graph_provider: Callable[[], object],
        driver: AgentGraphSingleStepDriver | None = None,
    ) -> None:
        if not callable(compiled_graph_provider):
            raise TypeError(
                "compiled_graph_provider must be callable"
            )
        if (
            driver is not None
            and not isinstance(
                driver,
                AgentGraphSingleStepDriver,
            )
        ):
            raise TypeError(
                "driver must be an "
                "AgentGraphSingleStepDriver or None"
            )

        self._compiled_graph_provider = (
            compiled_graph_provider
        )
        self._driver = (
            driver
            if driver is not None
            else AgentGraphSingleStepDriver()
        )

    def execute_next_node(
        self,
        *,
        run_id: str,
        expected_node: str,
        persisted_state: Mapping[str, object],
    ) -> AgentGraphStepCoordinationResult:
        normalized_run_id = self._validate_run_id(
            run_id
        )
        normalized_expected_node = (
            self._validate_expected_node(
                expected_node
            )
        )
        normalized_persisted_state = (
            self._validate_persisted_state(
                persisted_state
            )
        )

        if (
            normalized_persisted_state["run_id"]
            != normalized_run_id
        ):
            raise AgentGraphStepCoordinatorError(
                error_code=(
                    "persisted_run_identity_mismatch"
                ),
                message=(
                    "persisted_state.run_id does not "
                    "match run_id."
                ),
            )

        thread_config = build_checkpoint_config(
            run_id=normalized_run_id
        )
        frozen_thread_config = self._freeze_mapping(
            thread_config,
            field_name="thread_config",
        )
        frozen_persisted_state = self._freeze_mapping(
            normalized_persisted_state,
            field_name="persisted_state",
        )

        compiled_graph = self._acquire_compiled_graph()

        try:
            checkpoint_snapshot = (
                compiled_graph.get_state(
                    thread_config
                )
            )
        except Exception as exc:
            raise AgentGraphStepCoordinatorError(
                error_code="checkpoint_read_failed",
                message=(
                    "The latest graph checkpoint could "
                    "not be read."
                ),
                relation="checkpoint_read_failure",
            ) from exc

        checkpoint_values = (
            self._snapshot_values(
                checkpoint_snapshot
            )
        )
        checkpoint_next = self._snapshot_next(
            checkpoint_snapshot
        )

        inspection = self._inspect_checkpoint(
            expected_node=(
                normalized_expected_node
            ),
            thread_config=frozen_thread_config,
            persisted_state=frozen_persisted_state,
            checkpoint_values=checkpoint_values,
            checkpoint_next=checkpoint_next,
        )

        if (
            inspection.relation
            != "checkpoint_matches_persisted_state"
        ):
            self._raise_blocked_relation(
                inspection
            )

        driver_result = self._driver.execute_next_node(
            compiled_graph,
            thread_config=thread_config,
            expected_node=(
                normalized_expected_node
            ),
        )

        return AgentGraphStepCoordinationResult(
            inspection=inspection,
            driver_result=driver_result,
        )

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise AgentGraphStepCoordinatorError(
                error_code="invalid_run_id",
                message=(
                    "run_id must be normalized "
                    "nonblank text."
                ),
            )
        return run_id

    @staticmethod
    def _validate_expected_node(
        expected_node: str,
    ) -> str:
        if (
            not isinstance(expected_node, str)
            or not expected_node.strip()
            or expected_node
            != expected_node.strip()
            or expected_node
            not in AGENT_LANGGRAPH_NODES
        ):
            raise AgentGraphStepCoordinatorError(
                error_code="invalid_expected_node",
                message=(
                    "expected_node must be a frozen "
                    "Agent Graph node name."
                ),
            )
        return expected_node

    @staticmethod
    def _validate_persisted_state(
        persisted_state: Mapping[str, object],
    ) -> dict[str, object]:
        try:
            validated = validate_agent_graph_state(
                persisted_state
            )
        except (
            AgentGraphStateContractError,
            TypeError,
        ) as exc:
            raise AgentGraphStepCoordinatorError(
                error_code="invalid_persisted_state",
                message=(
                    "persisted_state does not satisfy "
                    "the Agent Graph state contract."
                ),
            ) from exc

        return dict(validated)

    def _acquire_compiled_graph(self) -> Any:
        try:
            compiled_graph = (
                self._compiled_graph_provider()
            )
        except Exception as exc:
            raise AgentGraphStepCoordinatorError(
                error_code=(
                    "compiled_graph_provider_failed"
                ),
                message=(
                    "compiled_graph_provider raised "
                    "an exception."
                ),
            ) from exc

        if not callable(
            getattr(
                compiled_graph,
                "get_state",
                None,
            )
        ):
            raise AgentGraphStepCoordinatorError(
                error_code=(
                    "compiled_graph_provider_failed"
                ),
                message=(
                    "compiled_graph_provider must return "
                    "an object with callable get_state()."
                ),
            )

        return compiled_graph

    @classmethod
    def _snapshot_values(
        cls,
        checkpoint_snapshot: object,
    ) -> Mapping[str, object]:
        values = getattr(
            checkpoint_snapshot,
            "values",
            None,
        )
        if not isinstance(values, Mapping):
            raise AgentGraphStepCoordinatorError(
                error_code=(
                    "checkpoint_state_mismatch"
                ),
                message=(
                    "Checkpoint values must be a mapping."
                ),
                relation="checkpoint_state_mismatch",
            )

        return cls._freeze_mapping(
            values,
            field_name="checkpoint_values",
        )

    @staticmethod
    def _snapshot_next(
        checkpoint_snapshot: object,
    ) -> tuple[str, ...]:
        raw_next = getattr(
            checkpoint_snapshot,
            "next",
            None,
        )
        if not isinstance(raw_next, (tuple, list)):
            raise AgentGraphStepCoordinatorError(
                error_code=(
                    "checkpoint_state_mismatch"
                ),
                message=(
                    "Checkpoint next must be a sequence."
                ),
                relation="checkpoint_state_mismatch",
            )

        normalized: list[str] = []
        for node_name in raw_next:
            if (
                not isinstance(node_name, str)
                or not node_name.strip()
                or node_name
                != node_name.strip()
            ):
                raise AgentGraphStepCoordinatorError(
                    error_code=(
                        "checkpoint_state_mismatch"
                    ),
                    message=(
                        "Checkpoint next contains an "
                        "invalid node name."
                    ),
                    relation=(
                        "checkpoint_state_mismatch"
                    ),
                )
            normalized.append(node_name)

        return tuple(normalized)

    @classmethod
    def _inspect_checkpoint(
        cls,
        *,
        expected_node: str,
        thread_config: Mapping[str, object],
        persisted_state: Mapping[str, object],
        checkpoint_values: Mapping[str, object],
        checkpoint_next: tuple[str, ...],
    ) -> AgentGraphCheckpointInspection:
        if (
            not checkpoint_values
            and not checkpoint_next
        ):
            return cls._build_inspection(
                relation="checkpoint_missing",
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        identity_fields = (
            "state_schema_version",
            "run_id",
            "issue_id",
            "graph_version",
        )
        identity_matches = all(
            field_name in checkpoint_values
            and checkpoint_values[field_name]
            == persisted_state[field_name]
            for field_name in identity_fields
        )

        if not identity_matches:
            return cls._build_inspection(
                relation=(
                    "checkpoint_identity_mismatch"
                ),
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        try:
            validated_checkpoint_state = (
                validate_agent_graph_state(
                    checkpoint_values
                )
            )
        except (
            AgentGraphStateContractError,
            TypeError,
        ):
            return cls._build_inspection(
                relation="checkpoint_state_mismatch",
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        persisted_transition_count = int(
            persisted_state["transition_count"]
        )
        checkpoint_transition_count = int(
            validated_checkpoint_state[
                "transition_count"
            ]
        )

        if (
            persisted_transition_count
            > checkpoint_transition_count
        ):
            return cls._build_inspection(
                relation="database_ahead",
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        if (
            checkpoint_transition_count
            > persisted_transition_count
        ):
            return cls._build_inspection(
                relation="graph_ahead",
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        if (
            dict(validated_checkpoint_state)
            != _thaw_json_value(persisted_state)
            or checkpoint_next
            != (expected_node,)
        ):
            return cls._build_inspection(
                relation="checkpoint_state_mismatch",
                expected_node=expected_node,
                thread_config=thread_config,
                persisted_state=persisted_state,
                checkpoint_values=checkpoint_values,
                checkpoint_next=checkpoint_next,
            )

        return cls._build_inspection(
            relation=(
                "checkpoint_matches_persisted_state"
            ),
            expected_node=expected_node,
            thread_config=thread_config,
            persisted_state=persisted_state,
            checkpoint_values=checkpoint_values,
            checkpoint_next=checkpoint_next,
        )

    @classmethod
    def _build_inspection(
        cls,
        *,
        relation: str,
        expected_node: str,
        thread_config: Mapping[str, object],
        persisted_state: Mapping[str, object],
        checkpoint_values: Mapping[str, object],
        checkpoint_next: tuple[str, ...],
    ) -> AgentGraphCheckpointInspection:
        return AgentGraphCheckpointInspection(
            relation=relation,
            expected_node=expected_node,
            thread_config=cls._freeze_mapping(
                thread_config,
                field_name="thread_config",
            ),
            persisted_state=cls._freeze_mapping(
                persisted_state,
                field_name="persisted_state",
            ),
            checkpoint_values=cls._freeze_mapping(
                checkpoint_values,
                field_name="checkpoint_values",
            ),
            checkpoint_next=tuple(checkpoint_next),
        )

    @staticmethod
    def _raise_blocked_relation(
        inspection: AgentGraphCheckpointInspection,
    ) -> None:
        error_contract = {
            "checkpoint_missing": (
                "checkpoint_bootstrap_required",
                "A graph checkpoint must be "
                "bootstrapped before execution.",
            ),
            "checkpoint_identity_mismatch": (
                "checkpoint_identity_mismatch",
                "Checkpoint identity does not match "
                "the persisted AgentRun state.",
            ),
            "database_ahead": (
                "database_ahead_reconciliation_required",
                "The database state is ahead of "
                "the graph checkpoint.",
            ),
            "graph_ahead": (
                "graph_ahead_reconciliation_required",
                "The graph checkpoint is ahead of "
                "the database state.",
            ),
            "checkpoint_state_mismatch": (
                "checkpoint_state_mismatch",
                "Checkpoint state or scheduled node "
                "does not match persisted state.",
            ),
        }
        error_code, message = error_contract[
            inspection.relation
        ]
        raise AgentGraphStepCoordinatorError(
            error_code=error_code,
            message=message,
            relation=inspection.relation,
            inspection=inspection,
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
    if (
        value is None
        or isinstance(
            value,
            (str, bool, int),
        )
    ):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(
                f"{field_name} contains a non-finite float"
            )
        return value

    if isinstance(value, Mapping):
        frozen_items = {
            key: _freeze_json_value(
                item,
                field_name=(
                    f"{field_name}.{key}"
                ),
            )
            for key, item in value.items()
            if isinstance(key, str)
        }
        if len(frozen_items) != len(value):
            raise TypeError(
                f"{field_name} contains a non-string key"
            )
        return MappingProxyType(frozen_items)

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(
                item,
                field_name=(
                    f"{field_name}[{index}]"
                ),
            )
            for index, item in enumerate(value)
        )

    raise TypeError(
        f"{field_name} contains a non-JSON value: "
        f"{type(value).__name__}"
    )


def _thaw_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _thaw_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _thaw_json_value(item)
            for item in value
        ]

    return value
