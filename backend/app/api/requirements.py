from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Requirement

router = APIRouter()

ALLOWED_REQUIREMENT_STATUSES = {'draft', 'approved', 'in_progress', 'blocked', 'delivered'}


class RequirementCreate(BaseModel):
    title: str = Field(min_length=1)
    priority: str
    status: str
    owner: str | None = None
    due_date: date | None = None
    project_id: int

    @field_validator('title')
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('title 不能为空')
        return value


class RequirementStatusUpdate(BaseModel):
    status: str

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_REQUIREMENT_STATUSES:
            raise ValueError('status 取值无效')
        return value


def serialize_requirement(requirement: Requirement) -> dict[str, object]:
    return {
        'id': requirement.id,
        'title': requirement.title,
        'priority': requirement.priority,
        'status': requirement.status,
        'owner': requirement.owner,
        'due_date': requirement.due_date.isoformat() if requirement.due_date else None,
        'project_id': requirement.project_id,
    }


@router.get('')
def list_requirements(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    requirements = db.query(Requirement).order_by(Requirement.id).all()
    return [serialize_requirement(requirement) for requirement in requirements]


@router.post('', status_code=status.HTTP_201_CREATED)
def create_requirement(payload: RequirementCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='project_id 对应的项目不存在')

    requirement = Requirement(
        title=payload.title.strip(),
        priority=payload.priority,
        status=payload.status,
        owner=payload.owner,
        due_date=payload.due_date,
        project_id=payload.project_id,
    )

    try:
        db.add(requirement)
        db.commit()
        db.refresh(requirement)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'创建 Requirement 失败：{exc!s}') from exc

    return serialize_requirement(requirement)


@router.patch('/{requirement_id}/status')
def update_requirement_status(
    requirement_id: int,
    payload: RequirementStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if requirement is None:
        raise HTTPException(status_code=404, detail='Requirement 不存在')

    requirement.status = payload.status

    try:
        db.commit()
        db.refresh(requirement)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'更新 Requirement 状态失败：{exc!s}') from exc

    return serialize_requirement(requirement)
