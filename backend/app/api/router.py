from fastapi import APIRouter

from app.api import ai, customers, dashboard, issues, knowledge, projects, requirements
from app.api import agent

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix='/dashboard', tags=['dashboard'])
api_router.include_router(customers.router, prefix='/customers', tags=['customers'])
api_router.include_router(projects.router, prefix='/projects', tags=['projects'])
api_router.include_router(requirements.router, prefix='/requirements', tags=['requirements'])
api_router.include_router(issues.router, prefix='/issues', tags=['issues'])
api_router.include_router(ai.router, prefix='/ai', tags=['ai'])
api_router.include_router(knowledge.router, prefix='/knowledge', tags=['knowledge'])
api_router.include_router(agent.router, prefix="/agent", tags=["Agent"])
