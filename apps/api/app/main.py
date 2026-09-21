from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.domain.policies import Conflict, DomainError, Forbidden, NotFound
from app.infrastructure.config import get_settings
from app.presentation.routes import router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ELEVEN BR",
        description="Seu time. Seu jogo. — API de fundação",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError) -> JSONResponse:
        status = {NotFound: 404, Forbidden: 403, Conflict: 409}.get(type(error), 400)
        return JSONResponse(status_code=status, content={"detail": str(error)})

    app.include_router(router)
    return app


app = create_app()
