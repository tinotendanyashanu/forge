from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.models import Task, TaskIn
from app.repository import TaskRepository

router = APIRouter(prefix="/tasks", tags=["tasks"])
NOT_FOUND = "Task not found"


def get_repository(request: Request) -> TaskRepository:
    return request.app.state.repo


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskIn, repo: TaskRepository = Depends(get_repository)) -> Task:
    return repo.add(body)


@router.get("")
def list_tasks(completed: bool | None = None, repo: TaskRepository = Depends(get_repository)) -> list[Task]:
    return repo.list(completed)


@router.get("/{task_id}")
def get_task(task_id: int, repo: TaskRepository = Depends(get_repository)) -> Task:
    task = repo.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, repo: TaskRepository = Depends(get_repository)) -> Response:
    if not repo.delete(task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
