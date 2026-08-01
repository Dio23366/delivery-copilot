def calculate_risk_level(overdue_requirements: int, blocked_issues: int, critical_issues: int, delivery_completion_rate: float) -> str:
    score = overdue_requirements + blocked_issues * 2 + critical_issues * 3
    if delivery_completion_rate < 0.5:
        score += 2
    if score >= 8:
        return 'high'
    if score >= 4:
        return 'medium'
    return 'low'
