from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.application.accounts import login, register
from app.application.sessions import TokenPair, logout_session, refresh_session
from app.application.verification import (
    VerificationTicket,
    confirm_code,
    limit_delivery,
    resend_code,
)
from app.domain.auth import ACCESS_MINUTES, SESSION_DAYS
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.rate_limit import rate_limit
from app.presentation.auth_schemas import (
    ChallengeInput,
    ChangeContactInput,
    LoginInput,
    RefreshInput,
    RegisterInput,
    SessionRead,
    VerificationRead,
    VerifyInput,
)
from app.presentation.dependencies import SessionDep

SettingsDep = Annotated[Settings, Depends(get_settings)]
COOKIE_NAME = "eleven_refresh"
COOKIE_PATH = "/v1/auth"


def auth_request(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client_type: Annotated[
        Literal["native", "web"],
        Header(
            alias="X-Eleven-Client",
            description="native: refresh no corpo; web: cookie HttpOnly e Origin autorizado.",
        ),
    ] = "native",
) -> str:
    """Custom header + exact Origin validation protect cookie mutations from CSRF.

    Native clients have no Origin and never consume browser cookies.
    """
    transport = client_type
    origin = request.headers.get("Origin")
    if transport not in ("native", "web"):
        raise HTTPException(400, "Cliente inválido.")
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(403, "Origem não permitida.")
    if transport == "web" and origin is None:
        raise HTTPException(403, "Origem necessária para acesso Web.")
    path = request.url.path.rsplit("/", 1)[-1]
    limit, seconds = (10, 3600) if path == "register" else (60, 900)
    rate_limit(
        session,
        settings,
        f"auth-ip:{path}",
        request.client.host if request.client else "unknown",
        limit=limit,
        seconds=seconds,
    )
    return transport


TransportDep = Annotated[str, Depends(auth_request)]
router = APIRouter(prefix="/v1/auth", tags=["authentication"])


def present_session(
    pair: TokenPair, response: Response, transport: str, settings: Settings
) -> SessionRead:
    if transport == "web":
        response.set_cookie(
            COOKIE_NAME,
            pair.refresh_token,
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=settings.app_env == "production",
            samesite="strict",
            path=COOKIE_PATH,
        )
    return SessionRead(
        access_token=pair.access_token,
        expires_in=ACCESS_MINUTES * 60,
        refresh_token=pair.refresh_token if transport == "native" else None,
    )


def read_refresh(data: RefreshInput, request: Request, transport: str) -> str | None:
    if transport == "web":
        return request.cookies.get(COOKIE_NAME)
    return data.refresh_token.get_secret_value() if data.refresh_token else None


@router.post(
    "/register", response_model=VerificationRead, response_model_exclude_none=True, status_code=201
)
def register_account(
    data: RegisterInput, session: SessionDep, settings: SettingsDep, transport: TransportDep
) -> VerificationRead:
    result = register(
        session,
        name=data.name,
        contact=data.contact,
        password=data.password.get_secret_value(),
        settings=settings,
    )
    return VerificationRead(**asdict(result))


@router.post(
    "/login", response_model=SessionRead | VerificationRead, response_model_exclude_none=True
)
def login_account(
    data: LoginInput,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    transport: TransportDep,
) -> SessionRead | VerificationRead:
    result = login(
        session,
        contact=data.contact,
        password=data.password.get_secret_value(),
        transport=transport,
        settings=settings,
    )
    if isinstance(result, VerificationTicket):
        return VerificationRead(**asdict(result))
    return present_session(result, response, transport, settings)


@router.post("/verify", response_model=SessionRead, response_model_exclude_none=True)
def verify_contact(
    data: VerifyInput,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    transport: TransportDep,
) -> SessionRead:
    pair = confirm_code(session, data.challenge_token, data.code, transport, settings)
    return present_session(pair, response, transport, settings)


@router.post("/resend", response_model=VerificationRead, response_model_exclude_none=True)
def resend(
    data: ChallengeInput, session: SessionDep, settings: SettingsDep, transport: TransportDep
) -> VerificationRead:
    limit_delivery(session, data.challenge_token, settings)
    return VerificationRead(**asdict(resend_code(session, data.challenge_token, settings)))


@router.post("/change-contact", response_model=VerificationRead, response_model_exclude_none=True)
def change_contact(
    data: ChangeContactInput, session: SessionDep, settings: SettingsDep, transport: TransportDep
) -> VerificationRead:
    limit_delivery(session, data.challenge_token, settings)
    return VerificationRead(
        **asdict(
            resend_code(
                session,
                data.challenge_token,
                settings,
                new_contact=data.contact,
            )
        )
    )


@router.post("/refresh", response_model=SessionRead, response_model_exclude_none=True)
def refresh(
    data: RefreshInput,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    transport: TransportDep,
) -> SessionRead:
    raw = read_refresh(data, request, transport)
    if not raw:
        raise HTTPException(401, "Sua sessão expirou. Entre novamente.")
    return present_session(
        refresh_session(session, raw, transport, settings), response, transport, settings
    )


@router.post("/logout", status_code=204)
def logout(
    data: RefreshInput,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    transport: TransportDep,
) -> None:
    logout_session(session, read_refresh(data, request, transport), transport, settings)
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )
