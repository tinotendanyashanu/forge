from fastapi import FastAPI

from app.repository import TaskRepository
from app.routes import tasks


def create_app() -> FastAPI:
    """Builds the API with a fresh, empty repository."""
    app = FastAPI(title="Tasks API")
    app.state.repo = TaskRepository()
    app.include_router(tasks.router)
    return app
