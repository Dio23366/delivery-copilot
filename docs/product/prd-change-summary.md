# Delivery Copilot PRD Evolution Summary

- Status: As-built evolution summary
- Runtime acceptance date: `2026-08-10`
- Source of truth: current public source, migrations, evidence documents, and validators

## 1. 原始 PRD 的产品愿景

原始 PRD 描述的是更广泛的 enterprise delivery copilot：覆盖 Customer、Project、Requirement、Issue、Comments、Risk、Reporting、AI Copilot Workspace，以及多种自动化和集成能力。

这份愿景仍保存在 `docs/product/prd-v0.1-original-vision.md`，用于说明产品最初希望解决的问题，不作为当前实现清单。

项目后来没有为了匹配最初愿景而一次性实现所有模块，而是先收敛到可以真实运行、验证和审计的 AI 工作流。

## 2. 当前仍然没有实现的范围

当前 As-built PRD 没有把原始愿景中的全部能力描述为已完成。以下内容仍属于 future scope：

- Authentication / RBAC / User Management
- Complete Comment Threads
- Independent free-form AI Copilot Workspace
- Complex SLA Engine
- Public Cloud Deployment
- CI/CD
- Multi-tenant Organization Support
- Slack / Jira / CRM integrations
- Customer Portal
- Autonomous enterprise write actions
- Model Fine-tuning
- Multi-agent orchestration
- Production-scale distributed workers / observability / SLA

这些能力没有实现，也不能作为当前作品集能力进行对外宣传。

## 3. Grounded RAG 阶段实现了什么

产品首先从广泛 Copilot 愿景收敛为可验证的 Grounded Issue Summarizer：

- Knowledge Document / Chunk / Embedding persistence
- `text-embedding-v4` + 1536-dimensional pgvector vectors
- global / customer / project retrieval scope
- Top-K cosine retrieval
- Grounded Prompt 和六字段结构化输出
- Citation Snapshot 和 Analysis History
- provider/model/Prompt Version/retrieval metadata persistence
- rule-based fallback
- Human-in-the-loop Review
- AI Evaluation workflow metrics

这一阶段重点证明“分析有证据、结果可追踪、结论可复核”，而不是开放式聊天或未经约束的自动化。

## 4. Agent MVP 阶段实现了什么

在 Grounded RAG 基础上，项目进一步实现了受控、持久化的单 Agent 问题调查流程，并提供 `/agent-runs` 操作界面：

- `AgentRun`、`AgentStep`、`AgentToolCall` 持久化与审计
- deterministic Issue context loading
- triage confirmation、Human Clarification 和 Final Human Review
- 3 个受控动态只读 Tool：`search_knowledge`、`get_analysis_history`、`calculate_delivery_risk`
- Tool contract / policy / guarded execution / replay-aware result reuse
- bounded steps、Tool calls、timeouts、cancel 和 resume
- evidence evaluation、analysis generation 和 Analysis persistence
- active-Run reuse 与关键状态 row locking
- Step timeline 和嵌套 Tool Call 可视化
- Agent state / Tool snapshot 的 browser redaction

运行验收期间还修复了弱证据进入生成、Clarification 无法读取持久化上下文、步骤预算不足、失败 Run 无法 recovery cancel、Review 表单跨 Run 残留等问题。

证据评估与生成过滤当前共用 `0.65` 的保守演示阈值；低于阈值的 Chunk 可保留在审计数据中，但不能进入生成 Prompt 和 Citation Snapshot。

该 Agent MVP 是有状态、可恢复、可审计的单 Agent 工作流，不是通用自治 Agent 平台。

## 5. LangGraph Foundation 当前边界

当前仓库使用 `langgraph==1.2.10`，并验证了：

- typed state
- compiled topology
- nodes and conditional routing
- read-only adapters
- `execute_tool` adapter
- single-step Driver
- checkpoint identity classification
- `AgentGraphStepCoordinator`
- 向 `AgentRunnerService` 的 constructor injection

但当前真实业务执行仍由 `AgentRunnerService` + orchestration/persistence services 负责。Coordinator 被注入并保存，但 Runner 当前不调用它。

因此这是增量迁移基础，**不代表 LangGraph 已全面接管生产 Runner**。当前没有生产级 persistent Checkpointer、自动 DB/Checkpoint reconciliation、distributed workers 或 multi-agent implementation。

## 6. 本次 PRD 更新不代表新增功能

本次 As-built PRD、README、Architecture 和 Agent 说明文档更新，目的是把公开叙事和当前已审计源码重新对齐，尤其明确：

- Grounded RAG 是一个真实子系统，而不是整个系统唯一架构；
- Stateful Agent runtime 已真实实现并验收；
- 当前 Runner 才是实际 orchestration authority；
- LangGraph 是已验证 migration foundation，而不是已接管 runtime；
- deterministic context loading 不应再被误写成当前动态 Tool Registry 的第四个 Tool。

本次文档更新**不增加运行时功能**，不改变 API、数据库 schema、Agent 行为或已接受的 evidence boundary。
