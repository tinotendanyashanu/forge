# Tasks API

A small internal service the support team uses to track follow-up tasks.
It is a FastAPI application with an in-memory repository.

```
app/
  main.py            # create_app(): builds the app and its repository
  models.py          # Pydantic request/response models
  repository.py      # TaskRepository: storage and queries
  routes/tasks.py    # HTTP handlers for /tasks
```

## Running locally

```bash
pip install "fastapi==0.115.14" "httpx==0.28.1" uvicorn
uvicorn app.main:create_app --factory --reload
```

In FORGE, use **Run tests** instead: the public tests run in an isolated
sandbox against `create_app()`.

## Conventions

* Handlers stay thin. Storage logic lives in `TaskRepository`.
* Errors use FastAPI's standard shape: `{"detail": "<message>"}`.
* `create_app()` must build a fresh repository every time it is called.
