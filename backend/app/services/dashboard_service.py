from datetime import date

from sqlalchemy.orm import Session

from app.models import Customer, Issue, Project, Requirement

CLOSED_ISSUE_STATUSES = ('resolved', 'closed')
DELIVERED_REQUIREMENT_STATUSES = ('delivered', 'rejected')


def get_dashboard_metrics(db: Session) -> dict[str, int]:
    active_customers = db.query(Customer).filter(Customer.status == 'active').count()
    active_projects = db.query(Project).filter(Project.status == 'active').count()
    open_issues = (
        db.query(Issue).filter(Issue.status.notin_(CLOSED_ISSUE_STATUSES)).count()
    )
    critical_issues = (
        db.query(Issue)
        .filter(
            Issue.severity == 'critical',
            Issue.status.notin_(CLOSED_ISSUE_STATUSES),
        )
        .count()
    )
    overdue_requirements = (
        db.query(Requirement)
        .filter(
            Requirement.due_date.isnot(None),
            Requirement.due_date < date.today(),
            Requirement.status.notin_(DELIVERED_REQUIREMENT_STATUSES),
        )
        .count()
    )
    projects_at_risk = (
        db.query(Project)
        .filter(Project.risk_level.in_(['medium', 'high']))
        .count()
    )

    return {
        'active_customers': active_customers,
        'active_projects': active_projects,
        'open_issues': open_issues,
        'critical_issues': critical_issues,
        'overdue_requirements': overdue_requirements,
        'projects_at_risk': projects_at_risk,
    }
