"""Garudan Server — FastAPI application factory."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .config import settings
from .routes import auth, terminal, system, docker_routes, files

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("garudan_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Garudan Server starting on %s:%s", settings.host, settings.port)
    yield
    logger.info("Garudan Server shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Garudan Server",
        description="Backend API for the Garudan mobile app",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Routers
    app.include_router(auth.router)
    app.include_router(terminal.router)
    app.include_router(system.router)
    app.include_router(docker_routes.router)
    app.include_router(files.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
