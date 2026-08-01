from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dashboard_service import get_dashboard_metrics

router = APIRouter()


@router.get('/metrics')
def get_metrics(db: Session = Depends(get_db)) -> dict[str, int]:
    return get_dashboard_metrics(db)
