from fastapi import APIRouter

router = APIRouter()


@router.get('/metrics')
def get_metrics() -> dict[str, int]:
    return {
        'active_customers': 0,
        'active_projects': 0,
        'open_issues': 0,
        'critical_issues': 0,
        'overdue_requirements': 0,
        'projects_at_risk': 0,
    }
