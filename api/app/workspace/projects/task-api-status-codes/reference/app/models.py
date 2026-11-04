from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # 1 = most urgent, 5 = least urgent.
    priority: int = Field(default=3, ge=1, le=5)
    completed: bool = False


class Task(TaskIn):
    id: int
