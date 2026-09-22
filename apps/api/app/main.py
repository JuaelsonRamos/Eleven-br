from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.domain.auth import DeliveryUnavailable, InvalidVerification, RateLimited, Unauthorized
from app.domain.policies import Conflict, DomainError, Forbidden, NotFound
from app.infrastructure.config import get_settings
from app.presentation.auth_routes import router as auth_router
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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-Eleven-Client"],
        allow_credentials=True,
        expose_headers=["Retry-After"],
    )

    @app.middleware("http")
    async def no_store(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(("/v1/auth", "/v1/me", "/v1/teams")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic input/ctx can contain plaintext passwords or verification secrets.
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Confira os campos informados.",
                "errors": [
                    {"field": str(item["loc"][-1]), "message": item["msg"]}
                    for item in error.errors()
                ],
            },
        )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError) -> JSONResponse:
        status = {
            NotFound: 404,
            Forbidden: 403,
            Conflict: 409,
            Unauthorized: 401,
            InvalidVerification: 400,
            RateLimited: 429,
            DeliveryUnavailable: 503,
        }.get(type(error), 400)
        headers = {"Retry-After": str(error.retry_after)} if isinstance(error, RateLimited) else {}
        return JSONResponse(status_code=status, content={"detail": str(error)}, headers=headers)

    app.include_router(router)
    app.include_router(auth_router)
    return app


app = create_app()
