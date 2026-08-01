from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import Customer, Issue, Project, Requirement


def seed_data(db: Session) -> None:
    if db.query(Customer).first() is not None:
        print('数据库已有数据，跳过初始化。')
        return

    customers = [
        Customer(
            name='Northwind Health',
            industry='Healthcare',
            contact='alice@northwind.example',
            status='active',
            owner='Alice',
        ),
        Customer(
            name='Contoso Retail',
            industry='Finance',
            contact='bob@contoso.example',
            status='active',
            owner='Bob',
        ),
        Customer(
            name='Fabrikam Manufacturing',
            industry='Manufacturing',
            contact='carol@fabrikam.example',
            status='active',
            owner='Carol',
        ),
        Customer(
            name='Wingtip Energy',
            industry='Energy',
            contact='daniel@wingtip.example',
            status='active',
            owner='Daniel',
        ),
    ]
    for index in range(5, 13):
        industries = ['Finance', 'Healthcare', 'Manufacturing', 'Energy']
        customers.append(
            Customer(
                name=f'Enterprise Customer {index}',
                industry=industries[index % len(industries)],
                contact=f'contact{index}@example.com',
                status='active' if index % 2 else 'inactive',
                owner=f'Owner {index}',
            )
        )
    db.add_all(customers)
    db.flush()

    projects = [
        Project(customer_id=customers[0].id, name='Northwind Onboarding', status='active', health='yellow', risk_level='medium', delivery_stage='Discovery'),
        Project(customer_id=customers[1].id, name='Contoso Migration', status='blocked', health='red', risk_level='high', delivery_stage='Implementation'),
        Project(customer_id=customers[2].id, name='Fabrikam Rollout', status='active', health='green', risk_level='low', delivery_stage='Testing'),
        Project(customer_id=customers[3].id, name='Wingtip Go-Live', status='at_risk', health='yellow', risk_level='medium', delivery_stage='Go-live'),
        Project(customer_id=customers[4].id, name='Risk Project Alpha', status='active', health='red', risk_level='high', delivery_stage='Support'),
        Project(customer_id=customers[5].id, name='Risk Project Beta', status='active', health='green', risk_level='low', delivery_stage='Implementation'),
    ]
    for index in range(7, 11):
        projects.append(
            Project(
                customer_id=customers[index - 1].id,
                name=f'Delivery Project {index}',
                status='active',
                health='green',
                risk_level='low',
                delivery_stage=['Discovery', 'Implementation', 'Testing', 'Go-live', 'Support'][index % 5],
            )
        )
    db.add_all(projects)
    db.flush()

    today = date.today()
    requirements = [
        Requirement(project_id=projects[0].id, title='SSO Integration', status='in_progress', priority='high', owner='Delivery Team', due_date=today + timedelta(days=14)),
        Requirement(project_id=projects[1].id, title='Data Sync Validation', status='blocked', priority='critical', owner='Engineering Team', due_date=today - timedelta(days=7)),
        Requirement(project_id=projects[2].id, title='Legacy API Deprecation', status='delivered', priority='high', owner='Product Team', due_date=today - timedelta(days=3)),
        Requirement(project_id=projects[3].id, title='Security Audit Remediation', status='approved', priority='critical', owner='Delivery Team', due_date=today - timedelta(days=10)),
        Requirement(project_id=projects[4].id, title='User Migration Checklist', status='in_progress', priority='medium', owner='Engineering Team', due_date=today - timedelta(days=1)),
        Requirement(project_id=projects[5].id, title='Reporting Dashboard', status='delivered', priority='medium', owner='Product Team', due_date=today - timedelta(days=5)),
    ]
    db.add_all(requirements)
    db.flush()

    issues = [
        Issue(project_id=projects[0].id, title='API timeout during sync', description='The integration API times out during nightly sync jobs.', issue_type='API', status='investigating', severity='high', owner='Engineering Team'),
        Issue(project_id=projects[1].id, title='Customer blocked on test data', description='Test data has not been delivered by the customer team.', issue_type='Data', status='waiting_on_customer', severity='medium', owner='Customer Success'),
        Issue(project_id=projects[1].id, title='Critical data mismatch in production', description='Production records are inconsistent after migration.', issue_type='Data', status='open', severity='critical', owner='Delivery Manager'),
        Issue(project_id=projects[2].id, title='Blocked deployment pipeline', description='CI/CD pipeline is blocked by an invalid environment configuration.', issue_type='Deployment', status='waiting_on_engineering', severity='critical', owner='Engineering Team'),
    ]
    for index in range(5, 16):
        issue_types = ['API', 'Data', 'Deployment', 'Configuration', 'Integration']
        owners = ['Engineering Team', 'Delivery Manager', 'Customer Success']
        issues.append(
            Issue(
                project_id=projects[(index % len(projects))].id,
                title=f'Open Issue {index}',
                description=f'Brief description for open issue {index}.',
                issue_type=issue_types[index % len(issue_types)],
                status='open',
                severity='medium',
                owner=owners[index % len(owners)],
            )
        )
    issues.append(
        Issue(
            project_id=projects[4].id,
            title='Resolved onboarding bug',
            description='A minor onboarding bug was fixed in the latest patch.',
            issue_type='Configuration',
            status='resolved',
            severity='low',
            owner='Delivery Manager',
        )
    )
    db.add_all(issues)
    db.commit()
    print('测试数据初始化完成。')


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()


if __name__ == '__main__':
    main()
