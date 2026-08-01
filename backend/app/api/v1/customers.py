from fastapi import APIRouter

router = APIRouter()


@router.get('')
def list_customers() -> list[dict[str, str]]:
    return []
