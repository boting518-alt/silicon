from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from silicon.identity.routes import router
from silicon.crm.routes import router as crm_router
from silicon.catalog.routes import router as catalog_router
from silicon.quotes.routes import router as quote_router
from silicon.identity.access import Denied, audit
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

    app.include_router(router(engine, settings))
    app.include_router(crm_router(engine, settings))
    app.include_router(catalog_router(engine, settings))
    app.include_router(quote_router(engine, settings))
    from silicon.publication.routes import router as publication_router
    app.include_router(publication_router(engine, settings))
    from silicon.contracts.routes import router as contract_router
    app.include_router(contract_router(engine, settings))

    from silicon.inventory.routes import router as inventory_router
    app.include_router(inventory_router(engine, settings))
    from silicon.assembly.routes import router as assembly_router
    app.include_router(assembly_router(engine, settings))

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request, exc):
        return JSONResponse(status_code=503, content={"code": "DATABASE_UNAVAILABLE",
            "message": "服务暂不可用", "request_id": request.state.request_id})

    @app.exception_handler(Denied)
    def denied(request, exc):
        if not getattr(request.state, "denial_audited", False):
            with engine.begin() as db:
                audit(db, getattr(request.state, "actor_id", None), getattr(request.state, "tenant_id", None),
                      "access.denied", getattr(request.scope.get("route"), "path", "authentication"),
                      "denied", request.state.request_id)
        return JSONResponse(status_code=exc.status, content={"code": exc.code,
            "message": "身份无效或没有执行此操作的权限", "request_id": request.state.request_id})

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
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
                if revision != "0011_assembly_corrections":
                    raise RuntimeError("schema revision not ready")
        except (SQLAlchemyError, RuntimeError):
            return JSONResponse(status_code=503, content={
                "code": "DATABASE_NOT_READY", "message": "数据库暂不可用或迁移未完成",
                "request_id": request.state.request_id,
            })
        return Status(status="ready")

    return app
