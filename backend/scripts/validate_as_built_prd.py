from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRD = ROOT / "PRD.md"
ORIGINAL = ROOT / "docs" / "product" / "prd-v0.1-original-vision.md"
SUMMARY = ROOT / "docs" / "product" / "prd-change-summary.md"


EXPECTED_PRD_SECTIONS = [
    "## 1. Document Status",
    "## 2. Product Summary",
    "## 3. Product Goals",
    "## 4. Target Users",
    "## 5. Implemented Product Surface",
    "## 6. Agent MVP",
    "## 7. LangGraph Foundation",
    "## 8. Implemented API Workflows",
    "## 9. Persistence Requirements",
    "## 10. Frontend Requirements",
    "## 11. Provider and Failure Behavior",
    "## 12. Auditability and Trust",
    "## 13. Accepted Evidence Boundary",
    "## 14. Explicitly Not Implemented",
    "## 15. Release Position",
]

PRIVATE_HISTORY_TOKENS = [
    "delivery-copilot-agent-mvp-v1.0.0",
    "delivery-copilot-portfolio-v1.0.0",
    "255191416a87eb97b9936cca14702c24d7fa7921",
    "4253cf6",
    "57cf199",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_trailing_spaces(text: str) -> None:
    for line in text.splitlines():
        assert line == line.rstrip(" "), f"Trailing spaces detected: {line!r}"


def assert_contains(text: str, needle: str) -> None:
    assert needle.casefold() in text.casefold(), f"Missing required text: {needle}"


def assert_not_contains(text: str, needle: str) -> None:
    assert needle.casefold() not in text.casefold(), f"Unexpected text present: {needle}"


def numbered_h2_sections(text: str) -> list[int]:
    return [
        int(match.group(1))
        for match in re.finditer(r"(?m)^##\s+(\d+)\.\s+", text)
    ]


def main() -> None:
    for path in (PRD, ORIGINAL, SUMMARY):
        assert path.is_file(), path

    prd_text = read_text(PRD)
    original_text = read_text(ORIGINAL)
    summary_text = read_text(SUMMARY)

    for text in (prd_text, original_text, summary_text):
        assert text.endswith("\n")
        assert_no_trailing_spaces(text)

    assert prd_text.startswith(
        "# Delivery Copilot — As-built Product Requirements and Scope"
    )
    assert numbered_h2_sections(prd_text) == list(range(1, 16))
    for section in EXPECTED_PRD_SECTIONS:
        assert_contains(prd_text, section)

    for token in [
        "as-built specification",
        "persisted Grounded RAG issue analysis",
        "persisted, bounded single-agent investigation workflow",
        "validated LangGraph orchestration foundation",
        "Customer",
        "Project",
        "Requirement",
        "Issue",
        "Knowledge",
        "Human review",
        "AI evaluation",
        "issue_summary",
        "possible_root_cause",
        "recommended_actions",
        "customer_update_draft",
        "risk_level",
        "project_impact",
        "pending",
        "accepted",
        "rejected",
        "edited_and_accepted",
        "load_issue_context",
        "search_knowledge",
        "get_analysis_history",
        "calculate_delivery_risk",
        "agent_runs",
        "agent_steps",
        "agent_tool_calls",
        "AgentGraphStepCoordinator",
        "constructor injection into `AgentRunnerService`",
        "The Runner stores the injected Coordinator but does not invoke it.",
        "full production Runner takeover by LangGraph",
        "persistent production Checkpointer deployment",
        "automatic database/checkpoint reconciliation",
        "rule-based fallback",
        "Citation Snapshot",
        "pgvector",
        "1536-dimensional embeddings",
        "Authentication, authorization, or RBAC",
        "public cloud deployment",
        "CI/CD",
        "multi-agent behavior",
        "They do not establish production SLA, business ROI, security certification, or formal model accuracy.",
    ]:
        assert_contains(prd_text, token)

    assert original_text.startswith("# Product Requirements Document")
    assert numbered_h2_sections(original_text) == list(range(1, 13))
    for token in [
        "## 1. Project Background",
        "## 10. MVP Scope",
        "## 11. Success Metrics",
        "## 12. Future Improvements",
        "AI-powered Enterprise Delivery & Customer Issue Tracking Dashboard",
    ]:
        assert_contains(original_text, token)

    assert summary_text.startswith("# Delivery Copilot PRD Evolution Summary")
    assert numbered_h2_sections(summary_text) == list(range(1, 7))
    for token in [
        "原始 PRD 的产品愿景",
        "当前仍然没有实现的范围",
        "Grounded RAG 阶段实现了什么",
        "Agent MVP 阶段实现了什么",
        "LangGraph Foundation 当前边界",
        "本次 PRD 更新不代表新增功能",
        "future scope",
        "Grounded Issue Summarizer",
        "langgraph==1.2.10",
        "不代表 LangGraph 已全面接管生产 Runner",
        "As-built PRD",
        "不增加运行时功能",
    ]:
        assert_contains(summary_text, token)

    for forbidden in [
        "production deployment completed",
        "RBAC completed",
        "authentication completed",
        "CI/CD completed",
        "served hundreds of customers",
        "achieved 95% accuracy",
        "fine-tuning completed",
        "Bearer Token",
        "C:\\Users\\",
    ] + PRIVATE_HISTORY_TOKENS:
        assert_not_contains(prd_text, forbidden)
        assert_not_contains(summary_text, forbidden)

    print("As-built PRD assertions passed")


if __name__ == "__main__":
    sys.exit(main())
