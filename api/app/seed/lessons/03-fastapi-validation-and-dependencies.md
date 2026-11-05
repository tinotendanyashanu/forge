+++
slug = "fastapi-validation-and-dependencies"
skill = "fastapi"
topic = "request-validation"
difficulty = "beginner"
title = "FastAPI: validation, responses and dependencies"
summary = "How FastAPI turns type hints into request validation, filters responses, and shares resources such as database sessions through dependencies."
estimated_minutes = 22
objectives = [
  "Explain how FastAPI validates path, query and body parameters and when it returns 422.",
  "Use response_model to control exactly which fields leave the API.",
  "Use dependencies, including yield dependencies, and explain per-request caching.",
]
prerequisites = ["http-requests-and-semantics"]
misconceptions = [
  "Type hints in FastAPI are only documentation.",
  "Returning an ORM object is safe because private fields are 'probably' not serialised.",
  "A dependency used by two other dependencies runs twice per request.",
]
checks = ["fa-path-param-validation", "fa-response-model-filtering", "fa-dependency-caching"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pending independent human review"

[[resources]]
title = "FastAPI tutorial: Path parameters and validation"
url = "https://fastapi.tiangolo.com/tutorial/path-params/"

[[resources]]
title = "FastAPI tutorial: Response model"
url = "https://fastapi.tiangolo.com/tutorial/response-model/"

[[resources]]
title = "FastAPI tutorial: Dependencies"
url = "https://fastapi.tiangolo.com/tutorial/dependencies/"
+++
## Why it matters

Most API bugs and many security incidents happen at the boundary: input that was never validated, or output that included a field nobody meant to expose. FastAPI moves both concerns into declarations you can read and test, and its dependency system gives every request the resources it needs (database sessions, the current user) without global state.

## Mental model

FastAPI reads your function signature as a contract.

- Each parameter says **where** a value comes from (path, query string, body, header) and **what type** it must be.
- The `response_model` says what the client is **allowed to see**.
- `Depends(...)` says "before calling me, call this provider and give me its result".

Before your code runs, FastAPI checks the contract. If the request breaks it, your handler is never called.

## How it works

**Validation.** A parameter that appears in the path template is a path parameter; a simple-typed parameter that does not is a query parameter; a Pydantic model parameter is the JSON body. FastAPI uses Pydantic to convert and validate each value. On failure it returns `422 Unprocessable Content` with a JSON list describing every failing field and why.

**Response filtering.** With `response_model=UserPublic`, whatever your handler returns is validated against `UserPublic` and only its fields are serialised. Fields that exist on the returned object but not on the model are dropped.

**Dependencies.** A dependency is any callable. FastAPI resolves dependencies recursively, and by default caches each dependency's result for the duration of one request, so two dependants that both need `get_db` receive the same session. A dependency written as a generator (`yield`) runs its setup before the handler and its cleanup afterwards, which is the right shape for sessions and connections.

## Worked example

```python
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

app = FastAPI()


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: int
    email: EmailStr


async def get_db():
    session = SessionLocal()
    try:
        yield session          # handler runs here
    finally:
        await session.close()  # always runs, even on errors


@app.post("/users", response_model=UserPublic, status_code=201)
async def create_user(body: UserCreate, db=Depends(get_db)):
    if await db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    return user                # hashed_password is dropped by UserPublic
```

- `{"email": "not-an-email", "password": "x"}` never reaches the handler: FastAPI returns `422`, naming the `email` field.
- A duplicate email reaches the handler, which returns `409`: valid input that conflicts with existing state.
- The response contains only `id` and `email`, even though the ORM object also has `hashed_password`.

## Common mistakes

- **One model for everything.** Using the same model for input, storage and output leaks fields such as `hashed_password` or lets clients set fields such as `is_admin`. Separate `UserCreate`, the ORM `User`, and `UserPublic`.
- **Blocking calls in `async def` handlers.** A synchronous database driver or `time.sleep` inside `async def` stalls every request on that worker. Use async libraries, or declare the handler with plain `def` so FastAPI runs it in a thread pool.
- **Creating an engine per request.** Create the engine once per process (in a lifespan handler) and hand out sessions per request through a dependency.

## In production

Dependencies are how real FastAPI services do authentication (`current_user = Depends(get_current_user)`), authorisation (`Depends(require_role("admin"))`), database sessions, rate limiting and feature flags. In tests, `app.dependency_overrides[get_db] = get_test_db` swaps a dependency without touching the handlers, which is one of the main reasons to use them.

## Trade-offs and limits

Validation proves shape and type, not business rules that need the database (such as "email is unique"); those still belong in your code or in database constraints, which are the final guarantee under concurrency. Rich validation adds a little CPU per request, which is almost always worth it. Per-request caching of dependencies is usually what you want; pass `use_cache=False` when a dependency must run each time it is declared.

## Check your understanding

1. `GET /items/abc` hits a route declared with `item_id: int`. What happens?
   - Answer: FastAPI returns `422` with a validation error for `item_id`; the handler is not called.
2. Why is `response_model` a security control and not only documentation?
   - Answer: it guarantees only declared fields are serialised, so internal fields cannot leak by accident.
3. Two dependencies each declare `Depends(get_db)`. How many sessions does one request get by default?
   - Answer: one; the result is cached for the request.

## Practice

Build a tiny API with `POST /notes` and `GET /notes/{id}`. Use separate input and output models, a `yield` dependency that provides an in-memory store, and return `404` for unknown ids. Then write three tests with `TestClient`: invalid body returns `422`, the response never includes an internal `owner_secret` field, and overriding the store dependency works.
