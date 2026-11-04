# Architecture

```
HTTP request
   │
   ▼
routes/tasks.py ── Depends(get_repository) ──► TaskRepository (app.state.repo)
   │                                               │
   │  validates input with models.TaskIn           │  dict[int, Task], ids from 1
   ▼                                               ▼
response_model = models.Task                 list() returns tasks ordered by id
```

* **One repository per application.** `create_app()` stores it on
  `app.state.repo`; handlers receive it through `get_repository`. Tests rely on
  this: every test builds a new app and expects an empty store.
* **Validation belongs in the models.** Field constraints go on `TaskIn` so that
  FastAPI returns `422` with a structured error before a handler runs.
* **Status codes are part of the contract.** Mobile clients branch on them;
  see the API table in the ticket.
