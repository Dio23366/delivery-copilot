# Delivery Copilot PRD Evolution Summary

## 1. 原始 PRD 的产品愿景
原始 PRD 描述的是更广泛的 enterprise delivery copilot：覆盖 Customer、Project、Requirement、Issue、Comments、Risk、Reporting、AI Copilot Workspace，以及多种自动化和集成能力。

这份愿景仍保存在 `docs/product/prd-v0.1-original-vision.md`，用于说明产品最初希望解决的问题，不作为当前实现清单。

## 2. 当前仍然没有实现的范围
当前 As-built PRD 没有把愿景中的全部能力描述为已完成。以下内容仍属于 future scope：

- Authentication / RBAC / User Management
- Complete Comment Threads
- Independent AI Copilot Workspace
- Complex SLA Engine
- Public Cloud Deployment
- CI/CD
- Multi-tenant Organization Support
- Slack / Jira / CRM integrations
- Customer Portal
- Fully Autonomous AI Actions
- Model Fine-tuning
- Multi-agent orchestration

这些能力没有实现，也不能作为当前作品集能力进行对外宣传。

## 3. Grounded RAG 阶段实现了什么
产品首先从广泛 Copilot 愿景收敛为可验证的 Grounded Issue Summarizer：

- 知识文档、Chunk、Embedding 和 pgvector Top-K Retrieval
- global / customer / project 范围解析
- Grounded Prompt 和六字段结构化输出
- Citation Snapshot 和 Analysis History
- rule-based fallback
- Human-in-the-loop Review
- AI Evaluation workflow metrics

这一阶段重点证明“分析有证据、结果可追踪、结论可复核”，而不是开放式聊天或未经约束的自动化。

## 4. Agent MVP 阶段实现了什么
在 Grounded RAG 基础上，项目进一步实现了受控的单 Agent 问题调查流程：

- `AgentRun`、`AgentStep`、`AgentToolCall` 持久化与审计
- triage confirmation、Human Clarification 和 final Human Review
- 受控只读工具选择、执行与 replay-aware 结果复用
- bounded steps、tool calls、retries、timeouts、cancel 和 resume
- evidence evaluation、analysis generation 和 atomic persistence

该 Agent MVP 是有状态、可恢复、可审计的单 Agent 工作流，不是通用自治 Agent 平台。

## 5. LangGraph Foundation 当前边界
当前仓库使用 `langgraph==1.2.10`，并验证了 typed state、compiled topology、nodes、routing、adapters、single-step Driver、checkpoint identity、Coordinator，以及向 `AgentRunnerService` 的 constructor injection。

这是增量迁移基础，不代表 LangGraph 已全面接管生产 Runner。当前没有生产级持久化 Checkpointer、自动 DB/Checkpoint reconciliation、distributed workers 或 multi-agent implementation。

## 6. 本次 PRD 更新不代表新增功能
本次 PRD 与说明文档更新不增加运行时功能，而是把公开叙事、架构说明和 Validator 与当前已审计源码对齐。

这是一份 As-built PRD 及其演进说明，不是新的愿景承诺。实现状态以当前代码、数据库迁移、证据文件和可执行 Validator 为准。
