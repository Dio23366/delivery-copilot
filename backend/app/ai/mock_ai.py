from app.ai.prompts import (
    CUSTOMER_UPDATE_PROMPT,
    ISSUE_SUMMARY_PROMPT,
    REQUIREMENT_PROMPT,
    RISK_PROMPT,
)


def mock_requirement_parse(text: str) -> dict[str, object]:
    return {
        'source_text': text,
        'requirement_title': 'Customer requested SSO integration',
        'priority': 'high',
        'business_impact': 'Reduces login friction for enterprise users',
        'suggested_owner': 'Implementation Engineer',
        'due_date': '2026-07-31',
        'acceptance_criteria': [
            'Users can sign in with SSO',
            'Login flow works for the customer tenant',
        ],
        'prompt_used': REQUIREMENT_PROMPT,
    }


def mock_issue_summary(issue_description: str, comments: list[str]) -> dict[str, object]:
    return {
        'issue_description': issue_description,
        'comment_count': len(comments),
        'issue_summary': 'The issue is blocking delivery because the sync flow fails during validation.',
        'possible_root_cause': 'Likely caused by an upstream API timeout or missing test data.',
        'current_status': 'investigating',
        'next_steps': ['Verify API timeout logs', 'Confirm test data with the customer'],
        'customer_facing_update': 'We are investigating the issue and will share the next update soon.',
        'prompt_used': ISSUE_SUMMARY_PROMPT,
    }


def mock_risk_analysis(payload: dict[str, object]) -> dict[str, object]:
    overdue_requirements = int(payload.get('overdue_requirements', 0))
    blocked_issues = int(payload.get('blocked_issues', 0))
    critical_issues = int(payload.get('critical_issues', 0))
    delivery_completion_rate = float(payload.get('delivery_completion_rate', 0.0))
    project_stage = str(payload.get('project_stage', 'active'))

    score = overdue_requirements + blocked_issues * 2 + critical_issues * 3
    if delivery_completion_rate < 0.5:
        score += 2

    if score >= 8:
        risk_level = 'high'
    elif score >= 4:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {
        'risk_level': risk_level,
        'risk_explanation': f'Project stage is {project_stage} and the current delivery signals indicate {risk_level} risk.',
        'recommended_actions': [
            'Review blocked items with the owner',
            'Escalate critical issues if they affect timeline',
            'Update the customer with a clear status note',
        ],
        'prompt_used': RISK_PROMPT,
    }


def mock_customer_update_draft(project_status: str, issue_status: str) -> dict[str, object]:
    return {
        'draft_message': (
            f'The project is currently {project_status}, and the related issue is {issue_status}. '
            'We are actively working on the next steps and will provide another update shortly.'
        ),
        'tone': 'professional',
        'key_points': [
            'Current project status shared',
            'Issue status acknowledged',
            'Next update promised',
        ],
        'prompt_used': CUSTOMER_UPDATE_PROMPT,
    }
