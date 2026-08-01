from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api import agent as agent_api  # noqa: E402
from app.services.agent_runner_service import (  # noqa: E402
    AgentRunnerBoundedLoopError,
)


AGENT_API_PATH = BACKEND_ROOT / "app" / "api" / "agent.py"
ORCHESTRATION_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "agent_orchestration_service.py"
)
RUNNER_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "agent_runner_service.py"
)


class ValidationFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def top_level_function(
    source: str,
    name: str,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if (
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == name
        ):
            start_line = min(
                [node.lineno]
                + [
                    decorator.lineno
                    for decorator in node.decorator_list
                ]
            )
            segment = "".join(
                lines[start_line - 1:node.end_lineno]
            )
            return node, segment

    raise ValidationFailure(f"未找到函数：{name}")


def method_function(
    source: str,
    class_name: str,
    method_name: str,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for class_node in tree.body:
        if (
            not isinstance(class_node, ast.ClassDef)
            or class_node.name != class_name
        ):
            continue

        for node in class_node.body:
            if (
                isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                )
                and node.name == method_name
            ):
                segment = "".join(
                    lines[node.lineno - 1:node.end_lineno]
                )
                return node, segment

    raise ValidationFailure(
        f"未找到方法：{class_name}.{method_name}"
    )


def dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node

    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))

    return None


def call_lines(
    node: ast.AST,
    dotted_target: str,
) -> list[int]:
    result: list[int] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if dotted_name(child.func) == dotted_target:
            result.append(child.lineno)

    return sorted(result)


def assignment_line(
    node: ast.AST,
    target_name: str,
    value_dotted_name: str | None = None,
) -> int:
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        if len(child.targets) != 1:
            continue
        target = child.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id != target_name:
            continue

        if value_dotted_name is not None:
            if dotted_name(child.value) != value_dotted_name:
                continue

        return child.lineno

    raise ValidationFailure(
        f"未找到赋值：{target_name}"
    )


def tuple_assignment_line(
    node: ast.AST,
    names: tuple[str, ...],
) -> int:
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        if len(child.targets) != 1:
            continue
        target = child.targets[0]
        if not isinstance(target, ast.Tuple):
            continue

        actual_names = tuple(
            element.id
            for element in target.elts
            if isinstance(element, ast.Name)
        )
        if actual_names == names:
            return child.lineno

    raise ValidationFailure(
        f"未找到 tuple 赋值：{names}"
    )


class RecordingOrchestration:
    def __init__(
        self,
        *,
        resumed_run: object,
        route_step: object,
        events: list[str],
        error: Exception | None = None,
    ) -> None:
        self.resumed_run = resumed_run
        self.route_step = route_step
        self.events = events
        self.error = error
        self.calls: list[dict[str, object]] = []

    def resume_waiting_investigation_run(
        self,
        db: object,
        *,
        run_id: str,
        triage_result: dict[str, object] | None = None,
        clarification_response: str | None = None,
    ) -> tuple[object, object]:
        self.events.append("resume")
        self.calls.append(
            {
                "db": db,
                "run_id": run_id,
                "triage_result": triage_result,
                "clarification_response": (
                    clarification_response
                ),
            }
        )

        if self.error is not None:
            raise self.error

        return self.resumed_run, self.route_step


class RecordingRunner:
    def __init__(
        self,
        *,
        advanced_run: object,
        events: list[str],
        error: Exception | None = None,
    ) -> None:
        self.advanced_run = advanced_run
        self.events = events
        self.error = error
        self.calls: list[dict[str, object]] = []

    def advance_investigation_until_boundary(
        self,
        db: object,
        *,
        agent_run: object,
        current_step: object,
    ) -> SimpleNamespace:
        self.events.append("runner")
        self.calls.append(
            {
                "db": db,
                "agent_run": agent_run,
                "current_step": current_step,
            }
        )

        if self.error is not None:
            raise self.error

        return SimpleNamespace(
            agent_run=self.advanced_run,
            current_step=None,
            transition_count=4,
            stop_reason="unimplemented_boundary",
            visited_nodes=(
                "route_investigation",
                "select_tool",
                "execute_tool",
                "evaluate_evidence",
            ),
        )


@contextmanager
def patched_api(
    *,
    orchestration: object,
    runner: object,
    serializer: object,
):
    originals = {
        "agent_orchestration_service": (
            agent_api.agent_orchestration_service
        ),
        "agent_runner_service": (
            agent_api.agent_runner_service
        ),
        "_serialize_agent_run": (
            agent_api._serialize_agent_run
        ),
    }

    try:
        agent_api.agent_orchestration_service = orchestration
        agent_api.agent_runner_service = runner
        agent_api._serialize_agent_run = serializer
        yield
    finally:
        for name, value in originals.items():
            setattr(agent_api, name, value)


def expect_http_exception(
    *,
    run_id: str,
    payload: agent_api.AgentRunResumePayload,
    db: Mock,
    orchestration: object,
    runner: object,
    serializer: object,
    status_code: int,
) -> HTTPException:
    with patched_api(
        orchestration=orchestration,
        runner=runner,
        serializer=serializer,
    ):
        try:
            agent_api.resume_agent_run(
                run_id=run_id,
                payload=payload,
                db=db,
            )
        except HTTPException as exc:
            require(
                exc.status_code == status_code,
                (
                    "HTTP 状态码不匹配："
                    f"expected={status_code} "
                    f"actual={exc.status_code}"
                ),
            )
            return exc

    raise ValidationFailure(
        f"预期 HTTPException({status_code})，但调用成功"
    )


def main() -> None:
    agent_source = AGENT_API_PATH.read_text(
        encoding="utf-8"
    )
    orchestration_source = ORCHESTRATION_PATH.read_text(
        encoding="utf-8"
    )
    runner_source = RUNNER_PATH.read_text(
        encoding="utf-8"
    )

    resume_node, resume_source = top_level_function(
        agent_source,
        "resume_agent_run",
    )
    _, orchestration_method_source = method_function(
        orchestration_source,
        "AgentOrchestrationService",
        "resume_waiting_investigation_run",
    )
    _, runner_method_source = method_function(
        runner_source,
        "AgentRunnerService",
        "advance_investigation_until_boundary",
    )

    passed = 0

    require(
        '@router.post("/runs/{run_id}/resume")'
        in resume_source,
        "Resume 路由发生变化",
    )
    print("PASS: Resume route remains POST /runs/{run_id}/resume")
    passed += 1

    resume_calls = call_lines(
        resume_node,
        (
            "agent_orchestration_service."
            "resume_waiting_investigation_run"
        ),
    )
    runner_calls = call_lines(
        resume_node,
        (
            "agent_runner_service."
            "advance_investigation_until_boundary"
        ),
    )
    old_runner_calls = call_lines(
        resume_node,
        (
            "agent_runner_service."
            "advance_investigation_route"
        ),
    )
    require(
        len(resume_calls) == 1,
        f"Resume orchestration 调用次数异常：{resume_calls}",
    )
    require(
        len(runner_calls) == 1,
        f"Bounded Runner 调用次数异常：{runner_calls}",
    )
    require(
        not old_runner_calls,
        f"Resume 仍直接调用单步 route：{old_runner_calls}",
    )
    print("PASS: exactly one Resume and one bounded Runner call")
    passed += 1

    tuple_line = tuple_assignment_line(
        resume_node,
        ("run", "route_investigation_step"),
    )
    loop_result_line = assignment_line(
        resume_node,
        "loop_result",
    )
    advanced_run_line = assignment_line(
        resume_node,
        "run",
        "loop_result.agent_run",
    )
    require(
        tuple_line < loop_result_line < advanced_run_line,
        "Resume/bounded loop/advanced Run 赋值顺序错误",
    )
    print("PASS: Resume result feeds bounded loop then advanced Run")
    passed += 1

    serialize_calls = call_lines(
        resume_node,
        "_serialize_agent_run",
    )
    require(
        len(serialize_calls) == 1,
        "Resume serializer 调用次数不是 1",
    )
    require(
        advanced_run_line < serialize_calls[0],
        "serializer 未使用 bounded loop 推进后的 Run",
    )
    require(
        "_serialize_agent_run(db, run)"
        in resume_source,
        "serializer 参数合同发生变化",
    )
    print("PASS: bounded-loop Run is serialized")
    passed += 1

    require(
        "db.commit(" not in resume_source,
        "API Resume 不应直接 commit",
    )
    require(
        "db.refresh(" not in resume_source,
        "API Resume 不应直接 refresh",
    )
    require(
        "agent_persistence_service" not in resume_source,
        "API Resume 不应直接调用 Persistence",
    )
    print("PASS: API transaction ownership remains unchanged")
    passed += 1

    commit_position = orchestration_method_source.find(
        "db.commit()"
    )
    return_position = orchestration_method_source.find(
        "return agent_run, agent_step"
    )
    require(
        commit_position >= 0
        and return_position > commit_position,
        "Resume Orchestration 未在返回前 commit",
    )
    require(
        "db.rollback()" in orchestration_method_source,
        "Resume Orchestration 缺少 rollback",
    )
    for transaction_call in (
        "db.commit(",
        "db.rollback(",
        "db.refresh(",
        "db.flush(",
    ):
        require(
            transaction_call not in runner_method_source,
            (
                "Bounded Runner 不应直接拥有事务："
                f"{transaction_call}"
            ),
        )
    print("PASS: Resume commit precedes transaction-free bounded loop")
    passed += 1

    require(
        "except AgentRunnerBoundedLoopError as exc:"
        in resume_source,
        "Resume 未显式处理 bounded loop error",
    )
    print("PASS: bounded loop error has explicit API mapping")
    passed += 1

    events: list[str] = []
    resumed_run = object()
    route_step = object()
    advanced_run = object()
    db = Mock()
    orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=events,
    )
    runner = RecordingRunner(
        advanced_run=advanced_run,
        events=events,
    )
    serializer_calls: list[tuple[object, object]] = []

    def serializer(
        db_arg: object,
        run_arg: object,
    ) -> dict[str, object]:
        events.append("serialize")
        serializer_calls.append((db_arg, run_arg))
        return {"advanced": run_arg is advanced_run}

    with patched_api(
        orchestration=orchestration,
        runner=runner,
        serializer=serializer,
    ):
        result = agent_api.resume_agent_run(
            run_id="run-001",
            payload=agent_api.AgentRunResumePayload(
                triage_result={"confirmed": True},
            ),
            db=db,
        )

    require(
        result == {"advanced": True},
        "Triage Resume 未返回推进后的 Run",
    )
    require(
        events == ["resume", "runner", "serialize"],
        f"调用顺序错误：{events}",
    )
    print("PASS: Resume order is resume -> bounded loop -> serialize")
    passed += 1

    require(
        orchestration.calls
        == [
            {
                "db": db,
                "run_id": "run-001",
                "triage_result": {"confirmed": True},
                "clarification_response": None,
            }
        ],
        f"Resume orchestration 参数错误：{orchestration.calls}",
    )
    print("PASS: triage Resume arguments preserved")
    passed += 1

    require(
        runner.calls
        == [
            {
                "db": db,
                "agent_run": resumed_run,
                "current_step": route_step,
            }
        ],
        f"Bounded Runner 参数错误：{runner.calls}",
    )
    print("PASS: bounded loop receives resumed Run and route Step")
    passed += 1

    require(
        serializer_calls == [(db, advanced_run)],
        f"serializer 参数错误：{serializer_calls}",
    )
    require(
        db.commit.call_count == 0,
        "API Resume 不应直接 commit",
    )
    print("PASS: serializer receives bounded-loop Run only")
    passed += 1

    clarification_events: list[str] = []
    clarification_orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=clarification_events,
    )
    clarification_runner = RecordingRunner(
        advanced_run=advanced_run,
        events=clarification_events,
    )

    with patched_api(
        orchestration=clarification_orchestration,
        runner=clarification_runner,
        serializer=lambda *_: {"ok": True},
    ):
        clarification_result = agent_api.resume_agent_run(
            run_id="run-clarification",
            payload=agent_api.AgentRunResumePayload(
                clarification_response="  More context  ",
            ),
            db=db,
        )

    require(
        clarification_result == {"ok": True},
        "Clarification Resume 返回值错误",
    )
    require(
        clarification_orchestration.calls[0][
            "clarification_response"
        ]
        == "More context",
        "Clarification 未正确 trim",
    )
    require(
        len(clarification_runner.calls) == 1,
        "Clarification Resume 未调用 bounded loop 一次",
    )
    print("PASS: clarification is trimmed and bounded")
    passed += 1

    lookup_events: list[str] = []
    lookup_orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=lookup_events,
        error=LookupError("missing run"),
    )
    lookup_runner = RecordingRunner(
        advanced_run=advanced_run,
        events=lookup_events,
    )
    lookup_serializer = Mock()

    lookup_exc = expect_http_exception(
        run_id="missing-run",
        payload=agent_api.AgentRunResumePayload(
            clarification_response="Context",
        ),
        db=Mock(),
        orchestration=lookup_orchestration,
        runner=lookup_runner,
        serializer=lookup_serializer,
        status_code=404,
    )
    require(
        lookup_exc.detail == "missing run",
        "LookupError detail 未保留",
    )
    require(
        lookup_events == ["resume"],
        f"LookupError 后不应调用 bounded loop：{lookup_events}",
    )
    require(
        lookup_serializer.call_count == 0,
        "LookupError 后不应 serialize",
    )
    print("PASS: LookupError maps to 404 before bounded loop")
    passed += 1

    bounded_events: list[str] = []
    bounded_orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=bounded_events,
    )
    bounded_runner = RecordingRunner(
        advanced_run=advanced_run,
        events=bounded_events,
        error=AgentRunnerBoundedLoopError(
            error_code="runner_loop_stalled",
            message="loop stalled",
        ),
    )
    bounded_serializer = Mock()

    bounded_exc = expect_http_exception(
        run_id="run-stalled",
        payload=agent_api.AgentRunResumePayload(
            triage_result={"confirmed": True},
        ),
        db=Mock(),
        orchestration=bounded_orchestration,
        runner=bounded_runner,
        serializer=bounded_serializer,
        status_code=409,
    )
    require(
        bounded_exc.detail == "loop stalled",
        "Bounded loop error detail 未保留",
    )
    require(
        bounded_events == ["resume", "runner"],
        f"Bounded loop error 顺序错误：{bounded_events}",
    )
    require(
        bounded_serializer.call_count == 0,
        "Bounded loop error 后不应 serialize",
    )
    print("PASS: bounded loop error maps to 409")
    passed += 1

    value_events: list[str] = []
    value_orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=value_events,
    )
    value_runner = RecordingRunner(
        advanced_run=advanced_run,
        events=value_events,
        error=ValueError("route conflict"),
    )
    value_serializer = Mock()

    value_exc = expect_http_exception(
        run_id="run-conflict",
        payload=agent_api.AgentRunResumePayload(
            triage_result={"confirmed": True},
        ),
        db=Mock(),
        orchestration=value_orchestration,
        runner=value_runner,
        serializer=value_serializer,
        status_code=409,
    )
    require(
        value_exc.detail == "route conflict",
        "ValueError detail 未保留",
    )
    require(
        value_events == ["resume", "runner"],
        f"ValueError 顺序错误：{value_events}",
    )
    require(
        value_serializer.call_count == 0,
        "ValueError 后不应 serialize",
    )
    print("PASS: ValueError maps to 409 after Resume")
    passed += 1

    sqlalchemy_events: list[str] = []
    sqlalchemy_db = Mock()
    sqlalchemy_orchestration = RecordingOrchestration(
        resumed_run=resumed_run,
        route_step=route_step,
        events=sqlalchemy_events,
    )
    sqlalchemy_runner = RecordingRunner(
        advanced_run=advanced_run,
        events=sqlalchemy_events,
        error=SQLAlchemyError("route database failure"),
    )
    sqlalchemy_serializer = Mock()

    sqlalchemy_exc = expect_http_exception(
        run_id="run-database",
        payload=agent_api.AgentRunResumePayload(
            clarification_response="Context",
        ),
        db=sqlalchemy_db,
        orchestration=sqlalchemy_orchestration,
        runner=sqlalchemy_runner,
        serializer=sqlalchemy_serializer,
        status_code=500,
    )
    require(
        "恢复 Agent Run 失败"
        in str(sqlalchemy_exc.detail),
        "SQLAlchemyError 500 detail 前缀发生变化",
    )
    require(
        sqlalchemy_events == ["resume", "runner"],
        f"SQLAlchemyError 调用顺序错误：{sqlalchemy_events}",
    )
    require(
        sqlalchemy_db.rollback.call_count == 1,
        "SQLAlchemyError 分支应 rollback 一次",
    )
    require(
        sqlalchemy_serializer.call_count == 0,
        "SQLAlchemyError 后不应 serialize",
    )
    print("PASS: SQLAlchemyError maps to 500 and rolls back")
    passed += 1

    require(
        passed == 16,
        f"专项合同通过数量异常：{passed}",
    )
    print(
        "Agent Resume bounded Runner continuation assertions passed"
    )
    print(f"passed_count={passed}")


if __name__ == "__main__":
    main()
