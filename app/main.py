"""NEXOS - app local para criar e gerenciar agentes com base de conhecimento."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import agents, chat, documents, system
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="NEXOS",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(system.router)
app.include_router(agents.router)
app.include_router(documents.router)
app.include_router(chat.router)

app.mount("/static", StaticFiles(directory=settings.web_dir / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.web_dir / "templates" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
