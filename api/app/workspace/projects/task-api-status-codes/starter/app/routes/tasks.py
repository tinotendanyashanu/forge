from fastapi import APIRouter, Depends, Request

from app.models import Task, TaskIn
from app.repository import TaskRepository

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_repository(request: Request) -> TaskRepository:
    return request.app.state.repo


@router.post("")
def create_task(body: TaskIn, repo: TaskRepository = Depends(get_repository)) -> Task:
    return repo.add(body)


@router.get("")
def list_tasks(completed: bool | None = None, repo: TaskRepository = Depends(get_repository)) -> list[Task]:
    return repo.list(completed)


@router.get("/{task_id}")
def get_task(task_id: int, repo: TaskRepository = Depends(get_repository)) -> Task | None:
    return repo.get(task_id)


@router.delete("/{task_id}")
def delete_task(task_id: int, repo: TaskRepository = Depends(get_repository)):
    repo.delete(task_id)
    return {"deleted": True}
