from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer

router = APIRouter()

ALLOWED_CUSTOMER_STATUSES = {'active', 'inactive', 'prospect'}


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    contact: str | None = None
    status: str
    owner: str = Field(min_length=1)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('name 不能为空')
        return value

    @field_validator('industry')
    @classmethod
    def validate_industry(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('industry 不能为空')
        return value

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_CUSTOMER_STATUSES:
            raise ValueError('status 取值无效')
        return value

    @field_validator('owner')
    @classmethod
    def validate_owner(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('owner 不能为空')
        return value


class CustomerStatusUpdate(BaseModel):
    status: str

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ALLOWED_CUSTOMER_STATUSES:
            raise ValueError('status 取值无效')
        return value


def serialize_customer(customer: Customer) -> dict[str, object]:
    return {
        'id': customer.id,
        'name': customer.name,
        'industry': customer.industry,
        'contact': customer.contact,
        'status': customer.status,
        'owner': customer.owner,
    }


@router.get('')
def list_customers(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    customers = db.query(Customer).order_by(Customer.id).all()
    return [serialize_customer(customer) for customer in customers]


@router.post('', status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    name = payload.name.strip()
    exists = db.query(Customer).filter(Customer.name == name).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail='Customer name already exists')

    customer = Customer(
        name=name,
        industry=payload.industry.strip(),
        contact=payload.contact.strip() if isinstance(payload.contact, str) and payload.contact.strip() else None,
        status=payload.status,
        owner=payload.owner.strip(),
    )

    try:
        db.add(customer)
        db.commit()
        db.refresh(customer)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'创建 Customer 失败：{exc!s}') from exc

    return serialize_customer(customer)


@router.patch('/{customer_id}')
def update_customer_status(
    customer_id: int,
    payload: CustomerStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(status_code=404, detail='Customer 不存在')

    customer.status = payload.status

    try:
        db.commit()
        db.refresh(customer)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'更新 Customer 状态失败：{exc!s}') from exc

    return serialize_customer(customer)
