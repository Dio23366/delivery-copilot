from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import agent as agent_api  # noqa: E402


AGENT_API_PATH = BACKEND_DIR / "app" / "api" / "agent.py"


class ValidationFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def get_create_function_source(source: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "create_agent_run"
        ):
            segment = ast.get_source_segment(source, node)
            require(segment is not None, "无法提取 create_agent_run 源码")
            return segment
    raise ValidationFailure("未找到 create_agent_run")


class FakeQuery:
    def __init__(self, result: object) -> None:
        self.result = result

    def filter(self, *args: object, **kwargs: object) -> "FakeQuery":
        return self

    def with_for_update(self) -> "FakeQuery":
        return self

    def order_by(self, *args: object, **kwargs: object) -> "FakeQuery":
        return self

    def first(self) -> object:
        return self.result


class FakeSession:
    def __init__(self, query_results: list[object]) -> None:
        self._query_results = iter(query_results)
        self.rollback_count = 0
        self.query_count = 0

    def query(self, model: object) -> FakeQuery:
        self.query_count += 1
        try:
            result = next(self._query_results)
        except StopIteration as exc:
            raise ValidationFailure(
                "FakeSession 收到超出预期的 query() 调用"
            ) from exc
        return FakeQuery(result)

    def rollback(self) -> None:
        self.rollback_count += 1


class RecordingRunner:
    def __init__(
        self,
        *,
        result_run: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result_run = result_run
        self.error = error
        self.calls: list[dict[str, object]] = []

    def start_and_run_to_triage_wait(
        self,
        db: object,
        *,
        run_id: str,
        issue_id: int,
        graph_version: str,
        initial_state: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "db": db,
                "run_id": run_id,
                "issue_id": issue_id,
                "graph_version": graph_version,
                "initial_state": initial_state,
            }
        )
        if self.error is not None:
            raise self.error
        return SimpleNamespace(agent_run=self.result_run)


class ForbiddenRunner:
    def start_and_run_to_triage_wait(
        self,
        *args: object,
        **kwargs: object,
    ) -> object:
        raise ValidationFailure(
            "已有 Active Run 时不应调用 AgentRunnerService"
        )


@contextmanager
def patched_module(**replacements: object):
    originals = {
        name: getattr(agent_api, name)
        for name in replacements
    }
    try:
        for name, value in replacements.items():
            setattr(agent_api, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(agent_api, name, value)


def call_create(
    *,
    db: FakeSession,
    runner: object,
    serializer,
    issue_id: int = 17,
) -> object:
    with patched_module(
        agent_runner_service=runner,
        _serialize_agent_run=serializer,
    ):
        return agent_api.create_agent_run(
            agent_api.AgentRunCreatePayload(issue_id=issue_id),
            db,
        )


def expect_http_exception(
    *,
    db: FakeSession,
    runner: object,
    expected_status: int,
) -> HTTPException:
    try:
        call_create(
            db=db,
            runner=runner,
            serializer=lambda *_: {"unexpected": True},
        )
    except HTTPException as exc:
        require(
            exc.status_code == expected_status,
            (
                "HTTP 状态码不匹配："
                f"expected={expected_status} actual={exc.status_code}"
            ),
        )
        return exc
    raise ValidationFailure(
        f"预期 HTTPException({expected_status})，但调用成功"
    )


def main() -> None:
    source = AGENT_API_PATH.read_text(encoding="utf-8")
    create_source = get_create_function_source(source)
    ast.parse(source)

    passed = 0

    require(
        '@router.post("/runs")' in source,
        '缺少 @router.post("/runs")',
    )
    print("PASS: route remains POST /runs")
    passed += 1

    require(
        (
            "from app.services.agent_runner_service import ("
            in source
            and "AgentRunnerService," in source
        ),
        "AgentRunnerService class import missing",
    )
    require(
        "agent_runner_service = AgentRunnerService()"
        in source,
        "AgentRunnerService API instance missing",
    )
    print(
        "PASS: runner class import and API instance present"
    )
    passed += 1

    require(
        "agent_orchestration_service.start_run("
        not in create_source,
        "create_agent_run 仍直接调用 start_run",
    )
    print("PASS: new path no direct orchestration start_run")
    passed += 1

    require(
        "start_and_run_to_triage_wait("
        in create_source,
        "create_agent_run 未调用 Runner",
    )
    require(
        "run = runner_result.agent_run"
        in create_source,
        "未从 runner_result.agent_run 取得 Run",
    )
    require(
        "_serialize_agent_run(db, run)"
        in create_source,
        "未继续使用 _serialize_agent_run(db, run)",
    )
    print("PASS: runner result agent_run is serialized")
    passed += 1

    issue = object()
    run = object()
    serialized = {"serialized_run": id(run)}
    serializer_calls: list[tuple[object, object]] = []
    runner = RecordingRunner(result_run=run)
    db = FakeSession([issue, None])

    def serializer(db_arg: object, run_arg: object) -> dict[str, int]:
        serializer_calls.append((db_arg, run_arg))
        return serialized

    result = call_create(
        db=db,
        runner=runner,
        serializer=serializer,
    )
    require(result == serialized, "API 未返回 serializer 结果")
    require(len(runner.calls) == 1, "Runner 调用次数不是 1")
    require(
        serializer_calls == [(db, run)],
        "serializer 未接收 result.agent_run",
    )
    print("PASS: happy path returns serialized runner result")
    passed += 1

    call = runner.calls[0]
    require(call["db"] is db, "Runner db 参数错误")
    require(call["issue_id"] == 17, "Runner issue_id 参数错误")
    require(
        call["graph_version"] == agent_api.AGENT_GRAPH_VERSION,
        "Runner graph_version 参数错误",
    )
    require(
        call["initial_state"] == {"issue_id": 17},
        "Runner initial_state 参数错误",
    )
    run_id = call["run_id"]
    require(isinstance(run_id, str), "run_id 不是字符串")
    require(len(run_id) == 36, "run_id 不是标准 36 字符 UUID")
    require(str(UUID(run_id)) == run_id, "run_id 不是标准 UUID")
    print("PASS: runner arguments and UUID contract")
    passed += 1

    existing_run = object()
    existing_db = FakeSession([issue, existing_run])
    existing_serialized = {"existing": True}

    def existing_serializer(
        db_arg: object,
        run_arg: object,
    ) -> dict[str, bool]:
        require(db_arg is existing_db, "已有 Run serializer db 错误")
        require(
            run_arg is existing_run,
            "已有 Run serializer run 错误",
        )
        return existing_serialized

    existing_result = call_create(
        db=existing_db,
        runner=ForbiddenRunner(),
        serializer=existing_serializer,
    )
    require(
        existing_result == existing_serialized,
        "已有 Active Run 未原样返回",
    )
    require(
        existing_db.rollback_count == 1,
        "已有 Active Run 分支未 rollback",
    )
    print("PASS: existing active run bypasses runner")
    passed += 1

    missing_db = FakeSession([None])
    missing_exc = expect_http_exception(
        db=missing_db,
        runner=ForbiddenRunner(),
        expected_status=404,
    )
    require(
        missing_exc.detail == "Issue 不存在",
        "Issue 不存在 detail 发生变化",
    )
    require(
        missing_db.rollback_count == 1,
        "Issue 不存在分支未 rollback",
    )
    print("PASS: missing issue remains 404")
    passed += 1

    lookup_db = FakeSession([issue, None])
    lookup_exc = expect_http_exception(
        db=lookup_db,
        runner=RecordingRunner(error=LookupError("runner lookup")),
        expected_status=404,
    )
    require(
        lookup_exc.detail == "runner lookup",
        "LookupError detail 未保留",
    )
    print("PASS: runner LookupError maps to 404")
    passed += 1

    value_db = FakeSession([issue, None])
    value_exc = expect_http_exception(
        db=value_db,
        runner=RecordingRunner(error=ValueError("runner conflict")),
        expected_status=409,
    )
    require(
        value_exc.detail == "runner conflict",
        "ValueError detail 未保留",
    )
    print("PASS: runner ValueError maps to 409")
    passed += 1

    sqlalchemy_db = FakeSession([issue, None])
    sqlalchemy_exc = expect_http_exception(
        db=sqlalchemy_db,
        runner=RecordingRunner(
            error=SQLAlchemyError("runner database failure")
        ),
        expected_status=500,
    )
    require(
        sqlalchemy_db.rollback_count == 1,
        "SQLAlchemyError 分支未 rollback",
    )
    require(
        "创建 Agent Run 失败"
        in str(sqlalchemy_exc.detail),
        "SQLAlchemyError 500 detail 前缀发生变化",
    )
    print("PASS: SQLAlchemyError rolls back and maps to 500")
    passed += 1

    require(
        "db.commit(" not in create_source,
        "create_agent_run 不应直接 commit",
    )
    require(
        "db.refresh(" not in create_source,
        "create_agent_run 不应直接 refresh",
    )
    require(
        "agent_persistence_service" not in create_source,
        "create_agent_run 不应直接调用 Persistence Service",
    )
    print("PASS: API preserves runner transaction boundary")
    passed += 1

    require(passed == 12, f"通过数量异常：{passed}")
    print("Agent API runner integration stub assertions passed")
    print(f"passed_count={passed}")


if __name__ == "__main__":
    main()
