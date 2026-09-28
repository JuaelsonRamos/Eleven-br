from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.application import join_requests, team_discovery
from app.infrastructure.config import get_settings
from app.infrastructure.rate_limit import rate_limit
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.join_schemas import (
    AdminRequestRead,
    ApproveInput,
    CodeInput,
    ConfirmInput,
    LookupRead,
    RequestDetail,
    RequestRead,
    SearchRead,
)

router = APIRouter(tags=["team-join-requests"])


@router.get("/v1/teams/join/search", response_model=SearchRead)
def search(
    session: SessionDep,
    user: CurrentUser,
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchRead:
    limit_discovery(session, user, request)
    return SearchRead.model_validate(team_discovery.search(session, user.id, q, offset, limit))


def limit_discovery(session: SessionDep, user: CurrentUser, request: Request) -> None:
    settings = get_settings()
    rate_limit(session, settings, "team-code-user", str(user.id), limit=20, seconds=900)
    rate_limit(
        session,
        settings,
        "team-code-ip",
        request.client.host if request.client else "unknown",
        limit=60,
        seconds=900,
    )


@router.post("/v1/teams/join/lookup", response_model=LookupRead)
def lookup(data: CodeInput, session: SessionDep, user: CurrentUser, request: Request) -> LookupRead:
    limit_discovery(session, user, request)
    return LookupRead.model_validate(join_requests.lookup(session, user_id=user.id, code=data.code))


@router.post("/v1/teams/{team_id}/join-requests", response_model=RequestRead, status_code=201)
def create(
    team_id: UUID, data: CodeInput, session: SessionDep, user: CurrentUser, request: Request
) -> RequestRead:
    limit_discovery(session, user, request)
    return RequestRead.model_validate(
        join_requests.request_entry(session, user_id=user.id, team_id=team_id, code=data.code)
    )


@router.get("/v1/me/join-requests", response_model=list[RequestRead])
def mine(
    session: SessionDep, user: CurrentUser, offset: Annotated[int, Query(ge=0)] = 0
) -> list[RequestRead]:
    return [
        RequestRead.model_validate(item)
        for item in join_requests.mine(session, user_id=user.id, offset=offset)
    ]


@router.post("/v1/me/join-requests/{request_id}/cancel", response_model=RequestRead)
def cancel(request_id: UUID, session: SessionDep, user: CurrentUser) -> RequestRead:
    return RequestRead.model_validate(
        join_requests.cancel(session, user_id=user.id, request_id=request_id)
    )


@router.get("/v1/teams/{team_id}/join-requests", response_model=list[AdminRequestRead])
def pending(team_id: UUID, session: SessionDep, user: CurrentUser) -> list[AdminRequestRead]:
    return [
        AdminRequestRead.model_validate(item)
        for item in join_requests.list_pending(session, user_id=user.id, team_id=team_id)
    ]


@router.get("/v1/teams/{team_id}/join-requests/{request_id}", response_model=RequestDetail)
def detail(
    team_id: UUID, request_id: UUID, session: SessionDep, user: CurrentUser
) -> RequestDetail:
    return RequestDetail.model_validate(
        join_requests.detail(session, user_id=user.id, team_id=team_id, request_id=request_id)
    )


@router.post("/v1/teams/{team_id}/join-requests/{request_id}/approve", response_model=RequestRead)
def approve(
    team_id: UUID, request_id: UUID, data: ApproveInput, session: SessionDep, user: CurrentUser
) -> RequestRead:
    return RequestRead.model_validate(
        join_requests.approve(
            session,
            user_id=user.id,
            team_id=team_id,
            request_id=request_id,
            membership_id=data.membership_id,
            confirm=data.confirm,
        )
    )


@router.post("/v1/teams/{team_id}/join-requests/{request_id}/reject", response_model=RequestRead)
def reject(
    team_id: UUID, request_id: UUID, data: ConfirmInput, session: SessionDep, user: CurrentUser
) -> RequestRead:
    return RequestRead.model_validate(
        join_requests.reject(
            session, user_id=user.id, team_id=team_id, request_id=request_id, confirm=data.confirm
        )
    )
