from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from silicon.settings import Settings
from silicon.shared.db import make_engine


class Status(BaseModel):
    status: Literal["ok", "ready"]


class Error(BaseModel):
    code: str
    message: str
    request_id: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="SILICON API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/api/v1/health", response_model=Status, operation_id="health")
    def health():
        return Status(status="ok")

    @app.get("/api/v1/ready", response_model=Status,
             responses={503: {"model": Error}}, operation_id="ready")
    def ready(request: Request):
        try:
            with engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != "0001_platform":
                    raise RuntimeError("schema revision not ready")
        except (SQLAlchemyError, RuntimeError):
            return JSONResponse(status_code=503, content={
                "code": "DATABASE_NOT_READY", "message": "数据库暂不可用或迁移未完成",
                "request_id": request.state.request_id,
            })
        return Status(status="ready")

    return app
