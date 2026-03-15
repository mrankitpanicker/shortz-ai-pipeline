"""
api/server.py — FastAPI application factory.

Creates and configures the Shortz API server with:
    • generation routes (from api.routes.generation)
    • request logging middleware
    • global exception handler

This is the modular entry point. The root-level api_server.py serves
as a backward-compatible entrypoint that imports from here.

Usage:
    uvicorn api.server:create_app --factory
"""

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.logging_config import setup_logging
from api.routes.generation import router as generation_router

log = setup_logging("api")


def create_app() -> FastAPI:
    """Application factory pattern — creates a configured FastAPI instance."""
    application = FastAPI(
        title="Shortz Video Generation API",
        description="Redis-backed job queue for AI video generation.",
        version="1.0.0",
    )

    # --- Middleware ---
    @application.middleware("http")
    async def log_requests(request, call_next):
        response = await call_next(request)
        log.debug("%s %s → %s", request.method, request.url.path, response.status_code)
        return response

    # --- Routes ---
    application.include_router(generation_router)

    # --- Global exception handler ---
    @application.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        log.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return application


# Pre-built app instance for `uvicorn api.server:app`
app = create_app()


if __name__ == "__main__":
    import uvicorn
    from core.config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)
