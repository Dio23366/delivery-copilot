from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_AGENT_TRIAGE_ISSUE_TYPES = frozenset(
    {
        "API",
        "Data",
        "Deployment",
        "Configuration",
        "Integration",
    }
)

ALLOWED_AGENT_TRIAGE_SEVERITIES = frozenset(
    {
        "low",
        "medium",
        "high",
        "critical",
    }
)


class AgentTriageResult(BaseModel):
    """Validated AI triage suggestion for an Agent Run."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str
    subtype: str = Field(
        min_length=1,
        max_length=120,
    )
    severity: str
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    reason: str = Field(
        min_length=1,
        max_length=2000,
    )

    @field_validator("issue_type")
    @classmethod
    def validate_issue_type(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            normalized
            not in ALLOWED_AGENT_TRIAGE_ISSUE_TYPES
        ):
            allowed = ", ".join(
                sorted(
                    ALLOWED_AGENT_TRIAGE_ISSUE_TYPES
                )
            )
            raise ValueError(
                f"issue_type must be one of: {allowed}"
            )

        return normalized

    @field_validator("subtype")
    @classmethod
    def validate_subtype(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "subtype must be nonblank"
            )

        return normalized

    @field_validator("severity")
    @classmethod
    def validate_severity(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            normalized
            not in ALLOWED_AGENT_TRIAGE_SEVERITIES
        ):
            allowed = ", ".join(
                sorted(
                    ALLOWED_AGENT_TRIAGE_SEVERITIES
                )
            )
            raise ValueError(
                f"severity must be one of: {allowed}"
            )

        return normalized

    @field_validator("reason")
    @classmethod
    def validate_reason(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "reason must be nonblank"
            )

        return normalized
