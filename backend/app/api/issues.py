from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project

router = APIRouter()

ALLOWED_ISSUE_STATUSES = {
    'open',
    'investigating',
    'waiting_on_customer',
    'waiting_on_engineering',
    'resolved',
}


class IssueCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    issue_type: str | None = None
    severity: str
    status: str
    owner: str | None = None
    project_id: int

    @field_validator('title')
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('title 不能为空')
        return value


class IssueStatusUpdate(BaseModel):
    status: str

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_ISSUE_STATUSES:
            raise ValueError('status 取值无效')
        return value


def serialize_issue(issue: Issue) -> dict[str, object]:
    return {
        'id': issue.id,
        'title': issue.title,
        'description': issue.description,
        'issue_type': issue.issue_type,
        'severity': issue.severity,
        'status': issue.status,
        'owner': issue.owner,
        'project_id': issue.project_id,
    }


@router.get('')
def list_issues(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    issues = db.query(Issue).order_by(Issue.id).all()
    return [serialize_issue(issue) for issue in issues]


@router.post('', status_code=status.HTTP_201_CREATED)
def create_issue(payload: IssueCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='project_id 对应的项目不存在')

    issue = Issue(
        title=payload.title.strip(),
        description=payload.description,
        issue_type=payload.issue_type,
        severity=payload.severity,
        status=payload.status,
        owner=payload.owner,
        project_id=payload.project_id,
    )

    try:
        db.add(issue)
        db.commit()
        db.refresh(issue)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'创建 Issue 失败：{exc!s}') from exc

    return serialize_issue(issue)


@router.patch('/{issue_id}/status')
def update_issue_status(
    issue_id: int,
    payload: IssueStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue is None:
        raise HTTPException(status_code=404, detail='Issue 不存在')

    issue.status = payload.status

    try:
        db.commit()
        db.refresh(issue)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'更新 Issue 状态失败：{exc!s}') from exc

    return serialize_issue(issue)
