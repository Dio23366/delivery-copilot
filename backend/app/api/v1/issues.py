from fastapi import APIRouter

router = APIRouter()


@router.get('')
def list_issues() -> list[dict[str, str]]:
    return []
