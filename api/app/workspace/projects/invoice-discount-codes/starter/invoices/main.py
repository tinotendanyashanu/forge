from fastapi import FastAPI

from invoices import routes
from invoices.db import connect, migrate


def create_app(db_path: str) -> FastAPI:
    conn = connect(db_path)
    migrate(conn)
    app = FastAPI(title="Invoices API")
    app.state.db = conn
    app.include_router(routes.router)
    return app
