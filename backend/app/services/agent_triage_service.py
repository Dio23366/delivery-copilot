from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.ai.issue_summarizer import IssueContext
from app.schemas.agent import (
    ALLOWED_AGENT_TRIAGE_ISSUE_TYPES,
    ALLOWED_AGENT_TRIAGE_SEVERITIES,
    AgentTriageResult,
)


TRIAGE_STRATEGY_VERSION = "agent_triage_v0.1"
DEFAULT_MAX_RETRIES = 2

CONTROLLED_SUBTYPES: dict[str, tuple[str, ...]] = {
    "API": (
        "authentication",
        "authorization",
        "timeout",
        "request_validation",
        "response_error",
        "rate_limit",
        "api_dependency",
    ),
    "Data": (
        "schema_mapping",
        "synchronization",
        "migration",
        "consistency",
        "quality",
        "missing_data",
        "duplication",
    ),
    "Deployment": (
        "pipeline",
        "build",
        "release",
        "environment",
        "dependency",
        "rollback",
    ),
    "Configuration": (
        "environment_variable",
        "credential",
        "permission",
        "parameter",
        "feature_flag",
        "endpoint",
    ),
    "Integration": (
        "connectivity",
        "protocol",
        "third_party_dependency",
        "webhook",
        "messaging",
        "compatibility",
    ),
}

GENERIC_SUBTYPES: dict[str, str] = {
    "API": "api_dependency",
    "Data": "quality",
    "Deployment": "environment",
    "Configuration": "parameter",
    "Integration": "connectivity",
}

ISSUE_TYPE_SIGNALS: dict[str, tuple[str, ...]] = {
    "API": (
        "api",
        "endpoint",
        "request",
        "response",
        "http",
        "rest",
        "graphql",
    ),
    "Data": (
        "data",
        "field",
        "record",
        "schema",
        "sync",
        "synchron",
        "migration",
        "mismatch",
        "duplicate",
    ),
    "Deployment": (
        "deploy",
        "deployment",
        "pipeline",
        "build",
        "release",
        "rollback",
        "ci/cd",
        "cicd",
    ),
    "Configuration": (
        "config",
        "configuration",
        "environment variable",
        "env var",
        "parameter",
        "permission",
        "credential",
        "feature flag",
    ),
    "Integration": (
        "integration",
        "third party",
        "third-party",
        "webhook",
        "protocol",
        "message queue",
        "messaging",
        "connectivity",
    ),
}

SUBTYPE_SIGNALS: dict[str, dict[str, tuple[str, ...]]] = {
    "API": {
        "authentication": (
            "authentication",
            "authenticate",
            "login",
            "token",
            "api key",
            "401",
        ),
        "authorization": (
            "authorization",
            "authorize",
            "forbidden",
            "access denied",
            "403",
        ),
        "timeout": (
            "timeout",
            "timed out",
            "latency",
            "slow response",
        ),
        "request_validation": (
            "request validation",
            "invalid request",
            "bad request",
            "parameter validation",
            "400",
            "422",
        ),
        "response_error": (
            "response error",
            "invalid response",
            "server error",
            "500",
            "502",
            "503",
        ),
        "rate_limit": (
            "rate limit",
            "too many requests",
            "throttle",
            "429",
        ),
        "api_dependency": (
            "api dependency",
            "upstream api",
            "downstream api",
            "external api",
        ),
    },
    "Data": {
        "schema_mapping": (
            "schema mapping",
            "field mapping",
            "column mapping",
            "mapping error",
        ),
        "synchronization": (
            "synchronization",
            "sync failure",
            "sync error",
            "out of sync",
        ),
        "migration": (
            "data migration",
            "migration failure",
            "migration error",
        ),
        "consistency": (
            "inconsistent",
            "inconsistency",
            "data mismatch",
            "mismatch",
        ),
        "quality": (
            "data quality",
            "invalid data",
            "malformed data",
        ),
        "missing_data": (
            "missing data",
            "data missing",
            "missing field",
            "null value",
        ),
        "duplication": (
            "duplicate data",
            "duplicated",
            "duplicate record",
        ),
    },
    "Deployment": {
        "pipeline": (
            "deployment pipeline",
            "pipeline failure",
            "pipeline blocked",
            "ci/cd",
            "cicd",
        ),
        "build": (
            "build failure",
            "build error",
            "compile error",
        ),
        "release": (
            "release failure",
            "release error",
            "release blocked",
        ),
        "environment": (
            "deployment environment",
            "environment issue",
            "environment mismatch",
        ),
        "dependency": (
            "dependency conflict",
            "dependency failure",
            "package conflict",
        ),
        "rollback": (
            "rollback",
            "roll back",
            "revert deployment",
        ),
    },
    "Configuration": {
        "environment_variable": (
            "environment variable",
            "env var",
            "missing env",
        ),
        "credential": (
            "credential",
            "secret",
            "password",
        ),
        "permission": (
            "permission",
            "access denied",
            "privilege",
        ),
        "parameter": (
            "configuration parameter",
            "config parameter",
            "invalid parameter",
        ),
        "feature_flag": (
            "feature flag",
            "feature toggle",
        ),
        "endpoint": (
            "configured endpoint",
            "endpoint configuration",
            "wrong endpoint",
        ),
    },
    "Integration": {
        "connectivity": (
            "connectivity",
            "connection failure",
            "cannot connect",
            "connection refused",
        ),
        "protocol": (
            "protocol mismatch",
            "protocol error",
            "ssl handshake",
            "tls handshake",
        ),
        "third_party_dependency": (
            "third party",
            "third-party",
            "vendor dependency",
        ),
        "webhook": (
            "webhook",
            "callback failure",
            "callback error",
        ),
        "messaging": (
            "message queue",
            "messaging",
            "queue failure",
            "event bus",
        ),
        "compatibility": (
            "compatibility",
            "incompatible",
            "version mismatch",
        ),
    },
}

CandidateGenerator = Callable[
    [IssueContext, int],
    Mapping[str, Any],
]


class AgentTriageError(RuntimeError):
    """Base error raised by Agent Triage."""


class AgentTriageExhaustedError(AgentTriageError):
    """Raised after all allowed triage attempts fail."""

    def __init__(
        self,
        *,
        code: str,
        attempts: int,
        max_retries: int,
        detail: str,
    ) -> None:
        self.code = code
        self.attempts = attempts
        self.max_retries = max_retries
        self.detail = detail

        super().__init__(
            f"{code} after {attempts} attempts: {detail}"
        )


class _RetryableTriageError(AgentTriageError):
    def __init__(
        self,
        *,
        code: str,
        detail: str,
    ) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class AgentTriageOutcome:
    """Validated triage result plus controlled attempt metadata."""

    result: AgentTriageResult
    attempt: int
    max_retries: int
    strategy_version: str = TRIAGE_STRATEGY_VERSION

    def to_state_update(self) -> dict[str, Any]:
        return {
            "triage_suggestion": self.result.model_dump(
                mode="json"
            ),
            "triage_attempt": self.attempt,
            "max_retries": self.max_retries,
        }


class AgentTriageService:
    """Pure deterministic triage service with finite retries."""

    def __init__(
        self,
        *,
        candidate_generator: CandidateGenerator | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries must be nonnegative"
            )

        self._candidate_generator = (
            candidate_generator
            or self._generate_rule_based_candidate
        )
        self.max_retries = max_retries

    @property
    def max_attempts(self) -> int:
        return self.max_retries + 1

    def triage(
        self,
        context: IssueContext,
    ) -> AgentTriageOutcome:
        last_code = "triage_validation_failed"
        last_detail = "No triage attempt completed"

        for attempt in range(
            1,
            self.max_attempts + 1,
        ):
            try:
                candidate = self._candidate_generator(
                    context,
                    attempt,
                )
                result = self._validate_candidate(
                    candidate
                )

                return AgentTriageOutcome(
                    result=result,
                    attempt=attempt,
                    max_retries=self.max_retries,
                )
            except _RetryableTriageError as exc:
                last_code = exc.code
                last_detail = exc.detail
            except ValidationError as exc:
                last_code = (
                    "triage_validation_failed"
                )
                last_detail = self._summarize_validation_error(
                    exc
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                last_code = (
                    "triage_validation_failed"
                )
                last_detail = str(exc)

        raise AgentTriageExhaustedError(
            code=last_code,
            attempts=self.max_attempts,
            max_retries=self.max_retries,
            detail=last_detail,
        )

    def _validate_candidate(
        self,
        candidate: Mapping[str, Any],
    ) -> AgentTriageResult:
        result = AgentTriageResult.model_validate(
            dict(candidate)
        )

        allowed_subtypes = CONTROLLED_SUBTYPES.get(
            result.issue_type
        )

        if (
            allowed_subtypes is None
            or result.subtype not in allowed_subtypes
        ):
            raise _RetryableTriageError(
                code="triage_subtype_mismatch",
                detail=(
                    f"Subtype {result.subtype!r} does not "
                    f"belong to {result.issue_type!r}"
                ),
            )

        return result

    def _generate_rule_based_candidate(
        self,
        context: IssueContext,
        attempt: int,
    ) -> Mapping[str, Any]:
        del attempt

        text = self._normalize_text(
            context.issue_title,
            context.issue_description,
        )

        issue_type, type_source = (
            self._resolve_issue_type(
                context.issue_type,
                text,
            )
        )

        severity = (
            context.severity.strip()
            if isinstance(
                context.severity,
                str,
            )
            else ""
        )

        if (
            severity
            not in ALLOWED_AGENT_TRIAGE_SEVERITIES
        ):
            raise _RetryableTriageError(
                code="triage_validation_failed",
                detail=(
                    "Issue severity must be one of the "
                    "controlled Delivery Copilot values"
                ),
            )

        subtype, subtype_specific = (
            self._resolve_subtype(
                issue_type,
                text,
            )
        )

        confidence = self._confidence_for(
            type_source=type_source,
            subtype_specific=subtype_specific,
        )

        reason = (
            f"Issue Type {issue_type!r} was "
            f"{type_source}; subtype {subtype!r} "
            f"was selected from "
            f"{'a specific controlled signal' if subtype_specific else 'the controlled generic fallback'}; "
            f"severity {severity!r} was preserved."
        )

        return {
            "issue_type": issue_type,
            "subtype": subtype,
            "severity": severity,
            "confidence": confidence,
            "reason": reason,
        }

    @staticmethod
    def _normalize_text(
        *values: str | None,
    ) -> str:
        return " ".join(
            value.strip().lower()
            for value in values
            if isinstance(value, str)
            and value.strip()
        )

    @staticmethod
    def _contains_signal(
        text: str,
        signal: str,
    ) -> bool:
        return signal in text

    def _resolve_issue_type(
        self,
        current_issue_type: str | None,
        text: str,
    ) -> tuple[str, str]:
        normalized_current = (
            current_issue_type.strip()
            if isinstance(
                current_issue_type,
                str,
            )
            else ""
        )

        if (
            normalized_current
            in ALLOWED_AGENT_TRIAGE_ISSUE_TYPES
        ):
            return (
                normalized_current,
                "preserved",
            )

        scored_types: list[tuple[int, str]] = []

        for issue_type, signals in (
            ISSUE_TYPE_SIGNALS.items()
        ):
            score = sum(
                1
                for signal in signals
                if self._contains_signal(
                    text,
                    signal,
                )
            )

            if score > 0:
                scored_types.append(
                    (score, issue_type)
                )

        if not scored_types:
            raise _RetryableTriageError(
                code="triage_unclassifiable",
                detail=(
                    "No controlled Issue Type signal "
                    "was found"
                ),
            )

        scored_types.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        return (
            scored_types[0][1],
            "inferred",
        )

    def _resolve_subtype(
        self,
        issue_type: str,
        text: str,
    ) -> tuple[str, bool]:
        subtype_signals = (
            SUBTYPE_SIGNALS[issue_type]
        )

        scored_subtypes: list[
            tuple[int, int, str]
        ] = []

        for order, (
            subtype,
            signals,
        ) in enumerate(
            subtype_signals.items()
        ):
            score = sum(
                1
                for signal in signals
                if self._contains_signal(
                    text,
                    signal,
                )
            )

            if score > 0:
                scored_subtypes.append(
                    (
                        score,
                        order,
                        subtype,
                    )
                )

        if not scored_subtypes:
            return (
                GENERIC_SUBTYPES[issue_type],
                False,
            )

        scored_subtypes.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        return (
            scored_subtypes[0][2],
            True,
        )

    @staticmethod
    def _confidence_for(
        *,
        type_source: str,
        subtype_specific: bool,
    ) -> float:
        if (
            type_source == "preserved"
            and subtype_specific
        ):
            return 0.95

        if (
            type_source == "inferred"
            and subtype_specific
        ):
            return 0.85

        if type_source == "preserved":
            return 0.75

        return 0.60

    @staticmethod
    def _summarize_validation_error(
        error: ValidationError,
    ) -> str:
        errors = error.errors(
            include_url=False
        )

        if not errors:
            return "AgentTriageResult validation failed"

        first = errors[0]
        location = ".".join(
            str(part)
            for part in first.get(
                "loc",
                (),
            )
        )
        message = str(
            first.get(
                "msg",
                "validation failed",
            )
        )

        if location:
            return f"{location}: {message}"

        return message
