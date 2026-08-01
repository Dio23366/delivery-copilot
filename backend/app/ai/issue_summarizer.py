from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IssueContext:
    issue_id: int
    issue_title: str
    issue_description: str | None
    issue_type: str | None
    severity: str
    status: str
    owner: str | None
    project_name: str | None
    project_status: str | None
    delivery_stage: str | None
    risk_level: str | None
    health: str | None
    customer_name: str | None
    customer_industry: str | None
    customer_contact: str | None


SEVERITY_TO_RISK = {
    'critical': 'critical',
    'high': 'high',
    'medium': 'medium',
    'low': 'low',
}

ISSUE_TYPE_GUIDANCE = {
    'API': '认证、权限、超时、参数、接口依赖',
    'Data': '格式、字段映射、同步、迁移、一致性',
    'Deployment': '环境配置、CI/CD、版本、依赖',
    'Configuration': '参数、环境变量、权限、配置错误',
    'Integration': '系统连接、协议、第三方依赖',
}


def _pick_risk_level(context: IssueContext) -> str:
    if context.status == 'resolved':
        if context.severity in {'high', 'critical'}:
            return 'medium'
        return 'low'

    base_risk = SEVERITY_TO_RISK.get(context.severity, 'medium')
    if context.risk_level == 'high' or context.health == 'critical':
        return 'high' if base_risk != 'critical' else 'critical'
    return base_risk


def _build_root_cause(context: IssueContext) -> str:
    issue_type_hint = ISSUE_TYPE_GUIDANCE.get(context.issue_type or '', '业务流程、依赖或配置问题')
    if context.status == 'resolved':
        if context.issue_type == 'API':
            return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'
        if context.issue_type == 'Data':
            return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'
        if context.issue_type == 'Deployment':
            return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'
        if context.issue_type == 'Configuration':
            return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'
        if context.issue_type == 'Integration':
            return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'
        return f'历史根因可能涉及 {issue_type_hint}，建议结合修复记录进行复盘。'

    if context.issue_type == 'API':
        return f'更像是 API 相关问题，重点排查 {issue_type_hint}。'
    if context.issue_type == 'Data':
        return f'更像是数据链路问题，重点排查 {issue_type_hint}。'
    if context.issue_type == 'Deployment':
        return f'更像是部署链路问题，重点排查 {issue_type_hint}。'
    if context.issue_type == 'Configuration':
        return f'更像是配置问题，重点排查 {issue_type_hint}。'
    if context.issue_type == 'Integration':
        return f'更像是集成问题，重点排查 {issue_type_hint}。'
    return f'当前线索指向 {issue_type_hint}。'


def _build_actions_for_resolved(context: IssueContext) -> list[str]:
    actions = ['确认修复结果', '执行回归测试', '监控是否复发', '记录根因和解决方案', '必要时更新知识库']
    if context.issue_type == 'API':
        actions.append('验证认证、权限、超时和依赖配置')
    elif context.issue_type == 'Data':
        actions.append('验证字段映射、迁移结果和数据一致性')
    elif context.issue_type == 'Deployment':
        actions.append('验证部署环境、版本和依赖')
    elif context.issue_type == 'Configuration':
        actions.append('验证参数和环境配置')
    elif context.issue_type == 'Integration':
        actions.append('验证系统连接和第三方依赖')
    return actions


def _build_actions_for_active(context: IssueContext) -> list[str]:
    actions: list[str] = []
    if context.status == 'open':
        actions.append('立即分配负责人并开始诊断')
    elif context.status == 'investigating':
        actions.append('继续收集日志并确认影响范围')
    elif context.status == 'waiting_on_customer':
        actions.append('向客户补充所需数据或操作清单')
    elif context.status == 'waiting_on_engineering':
        actions.append('升级到工程团队并设定处理时限')

    if context.issue_type == 'API':
        actions.append('检查认证、权限、超时和接口依赖')
    elif context.issue_type == 'Data':
        actions.append('核对字段映射、同步逻辑和迁移结果')
    elif context.issue_type == 'Deployment':
        actions.append('检查环境配置、CI/CD 和版本一致性')
    elif context.issue_type == 'Configuration':
        actions.append('复核环境变量、权限和配置项')
    elif context.issue_type == 'Integration':
        actions.append('确认第三方接口、协议和连接状态')

    if context.delivery_stage == 'Testing':
        actions.append('补充回归测试并验证边界场景')
    if context.delivery_stage == 'Go-live':
        actions.append('评估上线窗口对生产环境的影响')
    if context.project_status == 'completed':
        actions.append('判断是否属于售后或回归问题')

    if context.risk_level == 'high' or context.health == 'critical':
        actions.append('同步升级项目风险并通知关键干系人')

    return actions[:3]


def _build_customer_update(context: IssueContext) -> str:
    summary_subject = context.issue_title or f'Issue #{context.issue_id}'
    if context.status == 'resolved':
        if context.customer_name:
            return (
                f'Dear {context.customer_name}, the issue related to {summary_subject} has been resolved. '
                'We have validated the fix and are monitoring the environment for recurrence. '
                'We will continue to observe the service and provide an update if further action is required.'
            )
        return (
            f'The issue related to {summary_subject} has been resolved. '
            'We have validated the fix and are monitoring the environment for recurrence.'
        )

    if context.customer_name:
        return (
            f'Dear {context.customer_name}, we are currently investigating the issue related to {summary_subject}. '
            f'This appears to be a {context.issue_type or "general"} related matter'
            f'{" for the " + (context.customer_industry or "customer") + " environment" if context.customer_industry else ""}. '
            f'We will keep you updated as we confirm the impact and next steps.'
        )
    return f'We are investigating {summary_subject} and will provide the next update soon.'


def _clean_issue_summary(text: str) -> str:
    text = text.replace('.。', '.').replace('。.', '.').replace('!！', '!').replace('！!', '!').replace('?？', '?').replace('？?', '?')
    return text


def summarize_issue(context: IssueContext) -> dict[str, object]:
    risk_level = _pick_risk_level(context)
    summary_subject = context.issue_title or f'Issue #{context.issue_id}'
    project_part = f'，关联项目为 {context.project_name}' if context.project_name else ''
    customer_part = f'，客户为 {context.customer_name}' if context.customer_name else ''

    issue_summary = (
        f'{summary_subject} 当前处于 {context.status} 状态，严重级别为 {context.severity}'
        f'{project_part}{customer_part}。'
    )
    if context.issue_description:
        issue_summary += f' 描述摘要：{context.issue_description.strip()[:120]}。'
    issue_summary = _clean_issue_summary(issue_summary)

    possible_root_cause = _build_root_cause(context)
    if context.status == 'resolved':
        recommended_actions = _build_actions_for_resolved(context)
    else:
        recommended_actions = _build_actions_for_active(context)

    project_impact = 'Project impact appears limited.'
    if context.status == 'resolved':
        project_impact = 'The issue is resolved and the project impact is currently reduced.'
    elif context.risk_level == 'high' or context.health == 'critical':
        project_impact = 'This issue is likely to have a significant impact on the project timeline and delivery confidence.'
    elif context.delivery_stage == 'Go-live':
        project_impact = 'This issue could affect go-live readiness and should be monitored closely.'
    elif context.delivery_stage == 'Testing':
        project_impact = 'This issue may delay testing completion and requires validation after the fix.'
    elif context.project_status == 'completed':
        project_impact = 'This looks like a post-delivery issue and should be handled as a support/regression case.'

    return {
        'issue_id': context.issue_id,
        'issue_summary': issue_summary,
        'possible_root_cause': possible_root_cause,
        'recommended_actions': recommended_actions,
        'customer_update_draft': _build_customer_update(context),
        'risk_level': risk_level,
        'project_impact': project_impact,
    }
