from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent_graph.coordinator import AgentGraphStepCoordinator  # noqa: E402
from app.services.agent_runner_service import AgentRunnerService  # noqa: E402


TARGET_SHA256 = {
    "README.md": "254587b29b40c211689d3b4b1a0c51af812ea52fd0aa2be80ff29a54ae9baad6",
    "docs/architecture.md": "5d04d751e035855de8dbf695d6a69ca648afcf59ffc67eef7719dcbdd40be087",
    "docs/agent/agent-mvp-scope.md": "9d7525805886e6f870694ea1d18fed38c1557d671c00d15852d815a67ab78923",
    "docs/agent/agent-state-and-graph.md": "7eca39b4085cc9024591d87e972d616fae3af322ac99a9f3ea09f02bb9ae3848",
    "docs/product/prd-change-summary.md": "a97027c1929b0e7c145deb7d16d352e9267adfb02d2868518b9e90ba9647f1c2",
    "backend/scripts/validate_as_built_prd.py": "4c3c3d68b22faa8bf54f313d5d0af35e183b4a91955beb417c72f4abace2ff5a",
    "backend/scripts/validate_architecture_doc.py": "da72931805074ecf51c40628f071113efb8d0c54d8d36b8f447426c0847adcbe",
    "backend/scripts/validate_portfolio_readme.py": "8b1806063211351decd6755375ab5129633c9fb289bc3d8fe9fd8a3c42526fb0",
}

READ_ONLY_SHA256 = {
    "PRD.md": "b591b57007118cfa55658ce721245d6d10930c7cae53f124b2824f32059c74ea",
    "API_DESIGN.md": "5899c03521cd7c74a3ca1f72934a1a2cabf5b40f81057cd4df799d16ae3ad80f",
    "DATABASE_SCHEMA.md": "2b986b4021f8640f9d4152d486e87ed7e5d9bf93b9ff34b0643e9f52e2329025",
    "PAGE_DESIGN.md": "af7d47b399ff5f8b63496c4e688fe02fdd9ab5e616a70a1c30e5bc6576805c03",
    "backend/requirements.txt": "b3125387e7cae65c7174c64c55ae733de254d119e382a426abdfa4678418b86f",
    ".env.example": "1e21e332a1e465f19e1155a315034becb41cf4a77308159ac237915239bdc7d3",
    "compose.yaml": "24d09d27efec56821ba0a774150ab5ead888ee777ca10a9a94026cb28b3cb257",
    "backend/app/services/agent_runner_service.py": "fa853ab1bb2d8527d345515144e3c8102b115efdcf2281f9b913f76ac6bb8730",
    "backend/app/agent_graph/coordinator.py": "a626023dc814d9662178800e168fd656434a1e60fa39ea614e26bcea5a381dbf",
    "docs/grounded-rag-acceptance.md": "68c452c26c411225d2d1e417280a319b3cc9077d1a9ba815b58ba25c9744bdfb",
    "docs/evidence/grounded-rag-analysis-67.json": "5f271902a43e865b930bd22b3f2f428bfe5a2fd7ad07a4be3de77ef2ed74d330",
}

PUBLIC_METHODS = [
    "start_and_run_to_triage_wait",
    "advance_investigation_route",
    "advance_select_tool",
    "advance_execute_tool",
    "advance_evaluate_evidence",
    "advance_generate_analysis",
    "advance_persist_analysis",
    "advance_final_review",
    "advance_request_clarification",
    "advance_investigation_until_boundary",
]

RUNNER_DEPENDENCIES = [
    "orchestration_service",
    "issue_context_service",
    "triage_service",
    "investigation_routing_service",
    "tool_selection_service",
    "guarded_tool_execution_service",
    "tool_result_state_service",
    "evidence_evaluation_service",
    "analysis_generation_service",
    "clarification_request_service",
]

PRIVATE_HISTORY_TOKENS = [
    "delivery-copilot-agent-mvp-v1.0.0",
    "delivery-copilot-portfolio-v1.0.0",
    "255191416a87eb97b9936cca14702c24d7fa7921",
    "4253cf6",
    "57cf199",
]

ASSERTION_COUNT = 0
TEST_COUNT = 0


def check(condition: bool, message: str) -> None:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1
    if not condition:
        raise AssertionError(message)


def run_test(name: str, callback) -> None:
    global TEST_COUNT
    callback()
    TEST_COUNT += 1
    print(f"test={name}:passed")


def sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def runner_class() -> ast.ClassDef:
    source = (ROOT / "backend/app/services/agent_runner_service.py").read_text(
        encoding="utf-8-sig"
    )
    classes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "AgentRunnerService"
    ]
    check(len(classes) == 1, "AgentRunnerService class count")
    return classes[0]


def runner_methods() -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in runner_class().body
        if isinstance(node, ast.FunctionDef)
    }


def validate_exact_files() -> None:
    for relative_path, expected in {**TARGET_SHA256, **READ_ONLY_SHA256}.items():
        path = ROOT / relative_path
        check(path.is_file(), f"missing file: {relative_path}")
        check(sha256(path) == expected, f"sha256 mismatch: {relative_path}")


def validate_public_document_history_safety() -> None:
    public_docs = [
        "README.md",
        "docs/architecture.md",
        "docs/agent/agent-mvp-scope.md",
        "docs/agent/agent-state-and-graph.md",
        "docs/product/prd-change-summary.md",
    ]
    for relative_path in public_docs:
        text = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        for token in PRIVATE_HISTORY_TOKENS:
            check(token not in text, f"private history token in {relative_path}: {token}")


def validate_runner_constructor_contract() -> None:
    source = (ROOT / "backend/app/services/agent_runner_service.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.agent_graph.coordinator"
    ]
    check(len(imports) == 1, "Coordinator import count")

    methods = runner_methods()
    init = methods["__init__"]
    kwonly_names = [argument.arg for argument in init.args.kwonlyargs]
    check(
        kwonly_names == ["graph_step_coordinator", *RUNNER_DEPENDENCIES],
        f"Runner kw-only arguments: {kwonly_names}",
    )

    index = kwonly_names.index("graph_step_coordinator")
    check(
        ast.unparse(init.args.kwonlyargs[index].annotation)
        == "AgentGraphStepCoordinator | None",
        "Coordinator annotation",
    )
    default = init.args.kw_defaults[index]
    check(
        isinstance(default, ast.Constant) and default.value is None,
        "Coordinator default",
    )

    call_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AgentGraphStepCoordinator"
    ]
    check(call_nodes == [], "Runner must not construct a Coordinator")
    check("execute_next_node" not in source, "Runner must not invoke execute_next_node")

    public_names = [
        node.name
        for node in runner_class().body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    check(public_names == PUBLIC_METHODS, f"Runner public methods: {public_names}")


def validate_runner_runtime_storage() -> None:
    dependencies = {name: object() for name in RUNNER_DEPENDENCIES}
    default_runner = AgentRunnerService(**dependencies)
    check(
        default_runner._graph_step_coordinator is None,
        "Default Coordinator storage",
    )

    coordinator = AgentGraphStepCoordinator(compiled_graph_provider=lambda: object())
    explicit_runner = AgentRunnerService(
        graph_step_coordinator=coordinator,
        **dependencies,
    )
    check(
        explicit_runner._graph_step_coordinator is coordinator,
        "Explicit Coordinator storage",
    )

    try:
        AgentRunnerService(graph_step_coordinator=object(), **dependencies)
    except TypeError as exc:
        check(
            str(exc)
            == "graph_step_coordinator must be an AgentGraphStepCoordinator or None",
            f"Invalid Coordinator message: {exc}",
        )
    else:
        raise AssertionError("Invalid Coordinator accepted")


def validate_api_boundary() -> None:
    text = (ROOT / "backend/app/api/agent.py").read_text(encoding="utf-8-sig")
    check(
        text.count("agent_runner_service = AgentRunnerService()") == 1,
        "Agent API singleton",
    )
    check("AgentGraphStepCoordinator" not in text, "Agent API Coordinator injection")


def validate_ownership_prohibitions() -> None:
    source = (ROOT / "backend/app/services/agent_runner_service.py").read_text(
        encoding="utf-8-sig"
    )
    for token in [
        "AgentGraphSingleStepDriver",
        "compile_agent_graph",
        "PostgresSaver",
        "InMemorySaver",
        "update_state(",
        "execute_next_node",
        ".commit(",
        ".rollback(",
    ]:
        check(token not in source, f"forbidden Runner ownership token: {token}")


def main() -> None:
    run_test("exact_documentation_and_reference_hashes", validate_exact_files)
    run_test("public_document_history_safety", validate_public_document_history_safety)
    run_test("runner_constructor_contract", validate_runner_constructor_contract)
    run_test("runner_runtime_storage", validate_runner_runtime_storage)
    run_test("api_boundary", validate_api_boundary)
    run_test("ownership_prohibitions", validate_ownership_prohibitions)

    check(TEST_COUNT == 6, f"test count: {TEST_COUNT}")
    check(ASSERTION_COUNT >= 70, f"assertion count: {ASSERTION_COUNT}")

    print("Agent Runner Graph Step Coordinator injection foundation assertions passed")
    print(f"test_count={TEST_COUNT}")
    print(f"assertion_count={ASSERTION_COUNT}")
    print("stage=completed")


if __name__ == "__main__":
    main()
