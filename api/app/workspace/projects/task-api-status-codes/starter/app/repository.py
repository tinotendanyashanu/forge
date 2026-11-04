from app.models import Task, TaskIn


class TaskRepository:
    """In-memory storage. Ids start at 1 and are never reused."""

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def add(self, data: TaskIn) -> Task:
        task = Task(id=self._next_id, **data.model_dump())
        self._tasks[task.id] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)

    def list(self, completed: bool | None = None) -> list[Task]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.id)
        if completed:
            tasks = [t for t in tasks if t.completed == completed]
        return tasks

    def delete(self, task_id: int) -> bool:
        return self._tasks.pop(task_id, None) is not None
