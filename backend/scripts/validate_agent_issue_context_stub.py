from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

from app.ai.issue_summarizer import IssueContext
from app.models.issue import Issue
from app.services.agent_issue_context_service import (
    AgentIssueContextService,
)


class FakeQuery:
    def __init__(self, result) -> None:
        self.result = result
        self.options_count = 0
        self.filter_count = 0
        self.first_count = 0

    def options(self, *values):
        if not values:
            raise AssertionError(
                "Expected eager-load option"
            )

        self.options_count += 1
        return self

    def filter(self, *values):
        if not values:
            raise AssertionError(
                "Expected Issue filter"
            )

        self.filter_count += 1
        return self

    def first(self):
        self.first_count += 1
        return self.result


class FakeSession:
    def __init__(self, result) -> None:
        self.query_model = None
        self.fake_query = FakeQuery(result)

    def query(self, model):
        self.query_model = model
        return self.fake_query


def build_full_issue():
    customer = SimpleNamespace(
        name="Example Customer",
        industry="Manufacturing",
        contact="customer@example.com",
    )

    project = SimpleNamespace(
        name="API Integration",
        status="active",
        delivery_stage="Testing",
        risk_level="high",
        health="at_risk",
        customer=customer,
    )

    return SimpleNamespace(
        id=17,
        title="Authentication request rejected",
        description="The API returns HTTP 401.",
        issue_type="API",
        severity="high",
        status="investigating",
        owner="Delivery Engineer",
        project=project,
    )


def assert_lookup_error(
    callback: Callable[[], object],
    expected_text: str,
) -> None:
    try:
        callback()
    except LookupError as exc:
        assert expected_text in str(exc)
        return

    raise AssertionError(
        "Expected LookupError containing: "
        + expected_text
    )


def test_full_context_mapping() -> None:
    service = AgentIssueContextService()
    context = service.build_issue_context(
        build_full_issue()
    )

    assert isinstance(context, IssueContext)
    assert context.issue_id == 17
    assert (
        context.issue_title
        == "Authentication request rejected"
    )
    assert (
        context.issue_description
        == "The API returns HTTP 401."
    )
    assert context.issue_type == "API"
    assert context.severity == "high"
    assert context.status == "investigating"
    assert context.owner == "Delivery Engineer"
    assert context.project_name == "API Integration"
    assert context.project_status == "active"
    assert context.delivery_stage == "Testing"
    assert context.risk_level == "high"
    assert context.health == "at_risk"
    assert context.customer_name == "Example Customer"
    assert (
        context.customer_industry
        == "Manufacturing"
    )
    assert (
        context.customer_contact
        == "customer@example.com"
    )


def test_missing_project_maps_optional_fields() -> None:
    service = AgentIssueContextService()

    issue = SimpleNamespace(
        id=18,
        title="Standalone issue",
        description=None,
        issue_type=None,
        severity="medium",
        status="open",
        owner=None,
        project=None,
    )

    context = service.build_issue_context(issue)

    assert context.issue_id == 18
    assert context.issue_description is None
    assert context.issue_type is None
    assert context.owner is None
    assert context.project_name is None
    assert context.project_status is None
    assert context.delivery_stage is None
    assert context.risk_level is None
    assert context.health is None
    assert context.customer_name is None
    assert context.customer_industry is None
    assert context.customer_contact is None


def test_missing_customer_maps_customer_fields() -> None:
    service = AgentIssueContextService()

    project = SimpleNamespace(
        name="Internal Project",
        status="planning",
        delivery_stage="Discovery",
        risk_level=None,
        health="healthy",
        customer=None,
    )

    issue = SimpleNamespace(
        id=19,
        title="Configuration review",
        description=None,
        issue_type="Configuration",
        severity="low",
        status="open",
        owner="Project Owner",
        project=project,
    )

    context = service.build_issue_context(issue)

    assert context.project_name == "Internal Project"
    assert context.project_status == "planning"
    assert context.delivery_stage == "Discovery"
    assert context.risk_level is None
    assert context.health == "healthy"
    assert context.customer_name is None
    assert context.customer_industry is None
    assert context.customer_contact is None


def test_serialization_matches_contract() -> None:
    service = AgentIssueContextService()
    context = service.build_issue_context(
        build_full_issue()
    )

    serialized = service.serialize_issue_context(
        context
    )

    expected_keys = {
        "issue_id",
        "issue_title",
        "issue_description",
        "issue_type",
        "severity",
        "status",
        "owner",
        "project_name",
        "project_status",
        "delivery_stage",
        "risk_level",
        "health",
        "customer_name",
        "customer_industry",
        "customer_contact",
    }

    assert set(serialized) == expected_keys
    assert len(serialized) == 15
    assert serialized["issue_id"] == 17
    assert (
        serialized["customer_contact"]
        == "customer@example.com"
    )


def test_load_issue_context_queries_issue() -> None:
    issue = build_full_issue()
    db = FakeSession(issue)
    service = AgentIssueContextService()

    context = service.load_issue_context(
        db,
        issue_id=17,
    )

    assert db.query_model is Issue
    assert db.fake_query.options_count == 1
    assert db.fake_query.filter_count == 1
    assert db.fake_query.first_count == 1
    assert context.issue_id == 17
    assert context.project_name == "API Integration"


def test_missing_issue_is_rejected() -> None:
    db = FakeSession(None)
    service = AgentIssueContextService()

    assert_lookup_error(
        lambda: service.load_issue_context(
            db,
            issue_id=999999,
        ),
        "Issue not found: 999999",
    )

    assert db.query_model is Issue
    assert db.fake_query.options_count == 1
    assert db.fake_query.filter_count == 1
    assert db.fake_query.first_count == 1


TESTS: tuple[Callable[[], None], ...] = (
    test_full_context_mapping,
    test_missing_project_maps_optional_fields,
    test_missing_customer_maps_customer_fields,
    test_serialization_matches_contract,
    test_load_issue_context_queries_issue,
    test_missing_issue_is_rejected,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    print(f"validator_test_count={len(TESTS)}")
    print("issue_context_field_count=15")
    print(
        "loader_data_chain="
        "Issue->Project->Customer->IssueContext"
    )
    print(
        "agent_issue_context_stub_validation="
        "passed"
    )


if __name__ == "__main__":
    main()
