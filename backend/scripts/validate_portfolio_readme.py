from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SCREENSHOT = ROOT / "docs" / "screenshots" / "analysis-68-grounded-rag.png"

PRIVATE_HISTORY_TOKENS = [
    "delivery-copilot-agent-mvp-v1.0.0",
    "delivery-copilot-portfolio-v1.0.0",
    "255191416a87eb97b9936cca14702c24d7fa7921",
    "4253cf6",
    "57cf199",
]


def read_png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    ihdr_offset = 8
    length = struct.unpack(">I", data[ihdr_offset:ihdr_offset + 4])[0]
    chunk_type = data[ihdr_offset + 4:ihdr_offset + 8]
    assert chunk_type == b"IHDR"
    assert length == 13
    width, height = struct.unpack(">II", data[ihdr_offset + 8:ihdr_offset + 16])
    return width, height


def assert_exists(path: Path) -> None:
    assert path.is_file(), f"Missing file: {path}"


def assert_contains(text: str, needle: str) -> None:
    assert needle in text, f"Missing expected text: {needle}"


def assert_not_contains(text: str, needle: str) -> None:
    assert needle not in text, f"Unexpected text present: {needle}"


def assert_link_targets(text: str) -> None:
    for needle in [
        "PRD.md",
        "docs/architecture.md",
        "docs/grounded-rag-acceptance.md",
        "docs/evidence/grounded-rag-analysis-67.json",
        "docs/screenshots/analysis-68-grounded-rag.png",
        "docs/agent/agent-mvp-scope.md",
        "docs/agent/agent-state-and-graph.md",
    ]:
        assert_contains(text, needle)
        target = (ROOT / needle).resolve()
        assert target.exists(), f"Broken link target: {needle}"


def main() -> None:
    assert_exists(README)
    assert_exists(SCREENSHOT)

    readme_text = README.read_text(encoding="utf-8")
    assert readme_text.endswith("\n")

    for token in [
        "# Delivery Copilot",
        "Grounded RAG",
        "Human-in-the-loop",
        "Analysis #68",
        "accepted E2E evidence model: `gpt-5.5`",
        "configurable example default model: `gpt-4.1-mini`",
        "example configuration in `.env.example` and `compose.yaml` defaults to the configurable `gpt-4.1-mini`",
        "issue_summarizer_v4_grounded",
        "Document #3",
        "Enterprise API Integration Runbook",
        "text-embedding-v4",
        "pgvector",
        "1536",
        "rule-based fallback",
        "Citation Snapshot",
        "AgentGraphStepCoordinator",
        "production Runner does not yet call the Coordinator",
        "persistent production Checkpointer",
        "DB/Checkpoint reconciliation",
        "Publicly Verifiable Repository Evidence",
        "checked-in validators rather than references to private development tags or commits",
        "Known Limitations",
        "npm.cmd",
        "Authentication and RBAC are not implemented.",
        "```mermaid",
    ]:
        assert_contains(readme_text, token)

    for forbidden in [
        "## Suggested Tech Stack",
        "## Proposed Development Plan",
        "RBAC completed",
        "authentication completed",
        "Slack integration completed",
        "Jira integration completed",
        "CRM integration completed",
        "Bearer Token",
        "C:\\Users\\",
        *PRIVATE_HISTORY_TOKENS,
    ]:
        assert_not_contains(readme_text, forbidden)

    assert_link_targets(readme_text)

    width, height = read_png_dimensions(SCREENSHOT)
    assert width >= 900
    assert height >= 600

    print("Portfolio README assertions passed")


if __name__ == "__main__":
    main()
