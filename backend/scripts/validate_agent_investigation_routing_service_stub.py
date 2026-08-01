from __future__ import annotations

import ast
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.agent_investigation_routing_service import (  # noqa: E402
    AGENT_INVESTIGATION_ROUTING_VERSION,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    NEXT_NODE_EVALUATE_EVIDENCE,
    NEXT_NODE_FAILED,
    NEXT_NODE_LIMIT_EXCEEDED,
    NEXT_NODE_SELECT_TOOL,
    AgentInvestigationRoutingService,
)


SERVICE_PATH = (
    BACKEND_DIR
    / "app"
    / "services"
    / "agent_investigation_routing_service.py"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def base_state() -> dict[str, object]:
    return {
        "triage_result": {
            "issue_type": "API",
            "subtype": "authentication",
            "severity": "critical",
        },
        "triage_confirmed": True,
    }


def main() -> None:
    service = AgentInvestigationRoutingService()
    passed = 0

    require(
        AGENT_INVESTIGATION_ROUTING_VERSION
        == "agent_investigation_routing_v0.1",
        "routing version mismatch",
    )
    require(DEFAULT_MAX_STEPS == 16, "max steps mismatch")
    require(DEFAULT_MAX_TOOL_CALLS == 3, "max tool calls mismatch")
    print("PASS: frozen routing version and defaults")
    passed += 1

    outcome = service.route(base_state(), step_count=4, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_SELECT_TOOL,
        "empty investigation should select a tool",
    )
    require(outcome.error_code is None, "unexpected error")
    print("PASS: no evidence routes to select_tool")
    passed += 1

    state = base_state()
    state["tool_results"] = [{"tool_name": "search_knowledge"}]
    outcome = service.route(state, step_count=7, tool_call_count=1)
    require(
        outcome.next_node == NEXT_NODE_EVALUATE_EVIDENCE,
        "tool results should route to evaluation",
    )
    print("PASS: tool results route to evaluate_evidence")
    passed += 1

    state = base_state()
    state["retrieved_evidence"] = [{"citation_id": "K1"}]
    outcome = service.route(state, step_count=7, tool_call_count=1)
    require(
        outcome.next_node == NEXT_NODE_EVALUATE_EVIDENCE,
        "retrieved evidence should route to evaluation",
    )
    print("PASS: retrieved evidence routes to evaluation")
    passed += 1

    state = base_state()
    state["clarification_response"] = "Customer rotated key."
    outcome = service.route(state, step_count=8, tool_call_count=1)
    require(
        outcome.next_node == NEXT_NODE_EVALUATE_EVIDENCE,
        "clarification should route to evaluation",
    )
    print("PASS: clarification routes to evaluation")
    passed += 1

    state = base_state()
    state["max_tool_calls"] = 2
    outcome = service.route(state, step_count=9, tool_call_count=2)
    require(
        outcome.next_node == NEXT_NODE_LIMIT_EXCEEDED,
        "tool limit should terminate safely",
    )
    require(
        outcome.error_code == "max_tool_calls_reached",
        "tool limit error code mismatch",
    )
    print("PASS: max_tool_calls routes to limit_exceeded")
    passed += 1

    state = base_state()
    state["max_tool_calls"] = 2
    state["tool_results"] = [{"ok": True}]
    outcome = service.route(state, step_count=9, tool_call_count=2)
    require(
        outcome.next_node == NEXT_NODE_EVALUATE_EVIDENCE,
        "existing evidence should still be evaluated",
    )
    print("PASS: evidence evaluation survives tool limit")
    passed += 1

    state = base_state()
    state["max_steps"] = 10
    outcome = service.route(state, step_count=10, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_LIMIT_EXCEEDED,
        "step limit should terminate safely",
    )
    require(
        outcome.error_code == "max_steps_reached",
        "step limit error code mismatch",
    )
    print("PASS: max_steps routes to limit_exceeded")
    passed += 1

    outcome = service.route({}, step_count=4, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "missing triage should fail safely",
    )
    require(
        outcome.error_code == "missing_triage_result",
        "missing triage error code mismatch",
    )
    print("PASS: missing triage fails safely")
    passed += 1

    state = base_state()
    state["triage_confirmed"] = False
    outcome = service.route(state, step_count=4, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "unconfirmed triage should fail safely",
    )
    require(
        outcome.error_code == "triage_not_confirmed",
        "triage confirmation error code mismatch",
    )
    print("PASS: explicit unconfirmed triage fails safely")
    passed += 1

    state = base_state()
    state["selected_tool"] = {"tool_name": "search_knowledge"}
    outcome = service.route(state, step_count=5, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "pending selected tool should fail safely",
    )
    require(
        outcome.error_code == "pending_selected_tool",
        "pending selected tool error code mismatch",
    )
    print("PASS: pending selected tool is rejected")
    passed += 1

    outcome = service.route(
        base_state(),
        step_count=-1,
        tool_call_count=0,
    )
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "invalid step count should fail safely",
    )
    require(
        outcome.error_code == "invalid_step_count",
        "invalid step count error code mismatch",
    )
    print("PASS: invalid step_count fails safely")
    passed += 1

    outcome = service.route(
        base_state(),
        step_count=4,
        tool_call_count=True,
    )
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "invalid tool count should fail safely",
    )
    require(
        outcome.error_code == "invalid_tool_call_count",
        "invalid tool count error code mismatch",
    )
    print("PASS: invalid tool_call_count fails safely")
    passed += 1

    state = base_state()
    state["max_steps"] = 0
    outcome = service.route(state, step_count=4, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "invalid max steps should fail safely",
    )
    require(
        outcome.error_code == "invalid_max_steps",
        "invalid max steps error code mismatch",
    )
    print("PASS: invalid max_steps fails safely")
    passed += 1

    state = base_state()
    state["max_tool_calls"] = "3"
    outcome = service.route(state, step_count=4, tool_call_count=0)
    require(
        outcome.next_node == NEXT_NODE_FAILED,
        "invalid max tool calls should fail safely",
    )
    require(
        outcome.error_code == "invalid_max_tool_calls",
        "invalid max tool calls error code mismatch",
    )
    print("PASS: invalid max_tool_calls fails safely")
    passed += 1

    state = base_state()
    state["max_steps"] = 20
    state["max_tool_calls"] = 4
    outcome = service.route(state, step_count=4, tool_call_count=0)
    require(
        outcome.to_state_update()
        == {"max_steps": 20, "max_tool_calls": 4},
        "effective limits state update mismatch",
    )
    require(outcome.reason.strip(), "reason must be nonblank")
    print("PASS: effective limits are serializable")
    passed += 1

    source = SERVICE_PATH.read_text(encoding="utf-8")
    ast.parse(source)
    forbidden_tokens = (
        "sqlalchemy",
        "Session",
        "db.",
        "commit(",
        "rollback(",
        "refresh(",
        "GroundedRetrievalService",
        "IssueAnalysisService",
        "llm",
    )
    for token in forbidden_tokens:
        require(
            token not in source,
            f"routing service contains forbidden token: {token}",
        )
    print("PASS: routing service has no side-effect dependencies")
    passed += 1

    require(passed == 17, f"unexpected pass count: {passed}")
    print("Agent investigation routing service assertions passed")
    print(f"passed_count={passed}")


if __name__ == "__main__":
    main()
