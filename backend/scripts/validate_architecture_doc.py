from __future__ import annotations

import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture.md"
README = ROOT / "README.md"
ACC = ROOT / "docs" / "grounded-rag-acceptance.md"
JSON = ROOT / "docs" / "evidence" / "grounded-rag-analysis-67.json"
SCREENSHOT = ROOT / "docs" / "screenshots" / "analysis-68-grounded-rag.png"

PRIVATE_HISTORY_TOKENS = [
    "delivery-copilot-agent-mvp-v1.0.0",
    "delivery-copilot-portfolio-v1.0.0",
    "255191416a87eb97b9936cca14702c24d7fa7921",
    "4253cf6",
    "57cf199",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_png(path: Path) -> None:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    ihdr_len = struct.unpack(">I", data[8:12])[0]
    assert data[12:16] == b"IHDR"
    assert ihdr_len == 13
    width, height = struct.unpack(">II", data[16:24])
    assert width >= 900
    assert height >= 600


def assert_links(text: str) -> None:
    for rel in [
        "../README.md",
        "grounded-rag-acceptance.md",
        "evidence/grounded-rag-analysis-67.json",
        "screenshots/analysis-68-grounded-rag.png",
    ]:
        assert rel in text
    for match in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if match.startswith(("http://", "https://")):
            continue
        target = (DOC.parent / match).resolve()
        assert target.exists(), match


def main() -> None:
    for path in (DOC, README, ACC, JSON, SCREENSHOT):
        assert path.is_file(), path

    assert_png(SCREENSHOT)

    text = read_text(DOC)
    assert text.endswith("\n")
    assert text.startswith("# Delivery Copilot — As-built Architecture")
    assert text.count("## ") >= 15

    for token in [
        "Grounded RAG",
        "Retrieval Query Builder",
        "text-embedding-v4",
        "1536",
        "pgvector",
        "cosine",
        "issue_summarizer_v4_grounded",
        "rule-based fallback",
        "AIAnalysisLog",
        "Citation Snapshot",
        "Analysis #67",
        "Analysis #68",
        "Document #3",
        "Document #4",
        "edited_and_accepted",
        "retrieval_query",
        "knowledge_citations_json",
        "0007_agent_run_terminal",
        "AgentRun",
        "AgentStep",
        "AgentToolCall",
        "AgentGraphStepCoordinator",
        "AgentRunnerService",
        "stores the Coordinator but does not invoke it",
        "validated LangGraph foundation has not taken over the production Runner execution path",
        "Persistent production checkpoint storage and automated DB/Checkpoint reconciliation are not included",
        "Accepted E2E evidence model",
        "gpt-5.5",
        "Configurable example default",
        "gpt-4.1-mini",
        "Authentication and RBAC are not implemented",
        "Knowledge Evidence is treated as untrusted data",
        "archived documents are excluded from new retrieval",
        "historical Citation Snapshots remain immutable",
    ]:
        assert token in text, token

    for forbidden in [
        "RBAC completed",
        "authentication completed",
        "cloud deployment completed",
        "CI/CD completed",
        "sk-",
        "Bearer Token",
        "C:\\Users\\",
        "Workspace-specific host",
        *PRIVATE_HISTORY_TOKENS,
    ]:
        assert forbidden not in text, forbidden

    assert text.count("```mermaid") >= 3
    assert "flowchart" in text
    assert "sequenceDiagram" in text
    assert "stateDiagram-v2" in text
    assert_links(text)

    print("Architecture documentation assertions passed")


if __name__ == "__main__":
    main()
