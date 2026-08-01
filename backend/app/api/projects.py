from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Project

router = APIRouter()

ALLOWED_PROJECT_STATUSES = {'planning', 'active', 'on_hold', 'completed', 'cancelled'}
ALLOWED_DELIVERY_STAGES = {'Discovery', 'Implementation', 'Testing', 'Go-live', 'Support'}
ALLOWED_RISK_LEVELS = {'low', 'medium', 'high'}

RISK_LEVEL_TO_HEALTH = {
    'low': 'healthy',
    'medium': 'at_risk',
    'high': 'critical',
}


def calculate_health(risk_level: str | None) -> str:
    return RISK_LEVEL_TO_HEALTH.get(risk_level or 'medium', 'at_risk')


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    customer_id: int
    status: str
    delivery_stage: str | None = None
    risk_level: str | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('name 不能为空')
        return value

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_PROJECT_STATUSES:
            raise ValueError('status 取值无效')
        return value

    @field_validator('delivery_stage')
    @classmethod
    def validate_delivery_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_DELIVERY_STAGES:
            raise ValueError('delivery_stage 取值无效')
        return value

    @field_validator('risk_level')
    @classmethod
    def validate_risk_level(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_RISK_LEVELS:
            raise ValueError('risk_level 取值无效')
        return value


class ProjectUpdate(BaseModel):
    status: str | None = None
    delivery_stage: str | None = None
    risk_level: str | None = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_PROJECT_STATUSES:
            raise ValueError('status 取值无效')
        return value

    @field_validator('delivery_stage')
    @classmethod
    def validate_delivery_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_DELIVERY_STAGES:
            raise ValueError('delivery_stage 取值无效')
        return value

    @field_validator('risk_level')
    @classmethod
    def validate_risk_level(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_RISK_LEVELS:
            raise ValueError('risk_level 取值无效')
        return value


def serialize_project(project: Project) -> dict[str, object]:
    return {
        'id': project.id,
        'name': project.name,
        'customer_id': project.customer_id,
        'status': project.status,
        'health': project.health,
        'risk_level': project.risk_level,
        'delivery_stage': project.delivery_stage,
    }


@router.get('')
def list_projects(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    projects = db.query(Project).order_by(Project.id).all()
    return [serialize_project(project) for project in projects]


@router.post('', status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if customer is None:
        raise HTTPException(status_code=404, detail='customer_id 对应的客户不存在')

    project = Project(
        name=payload.name.strip(),
        customer_id=payload.customer_id,
        status=payload.status,
        delivery_stage=payload.delivery_stage,
        risk_level=payload.risk_level,
        health=calculate_health(payload.risk_level),
    )

    try:
        db.add(project)
        db.commit()
        db.refresh(project)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'创建 Project 失败：{exc!s}') from exc

    return serialize_project(project)


@router.patch('/{project_id}')
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if payload.status is None and payload.delivery_stage is None and payload.risk_level is None:
        raise HTTPException(status_code=400, detail='至少需要提供一个可更新字段')

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='Project 不存在')

    if payload.status is not None:
        project.status = payload.status
    if payload.delivery_stage is not None:
        project.delivery_stage = payload.delivery_stage
    if payload.risk_level is not None:
        project.risk_level = payload.risk_level
        project.health = calculate_health(payload.risk_level)

    try:
        db.commit()
        db.refresh(project)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'更新 Project 失败：{exc!s}') from exc

    return serialize_project(project)
