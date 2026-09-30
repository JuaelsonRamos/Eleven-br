"""Opponents center routes; business rules live in the application modules."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.application import challenges, fixtures, opponents
from app.domain.team_identity import Modality
from app.infrastructure.config import get_settings
from app.infrastructure.rate_limit import rate_limit
from app.presentation.dependencies import CurrentUser, SessionDep

router = APIRouter(prefix="/v1/teams/{team_id}/opponents", tags=["opponents"])
Offset = Annotated[int, Query(ge=0, le=1000)]


def limited(session: SessionDep, user: CurrentUser, scope: str, limit: int) -> None:
    # Per account, never per team ID: nobody can exhaust another team's quota.
    rate_limit(
        session, get_settings(), f"opponents-{scope}", str(user.id), limit=limit, seconds=3600
    )


@router.get("")
def central(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return opponents.central(session, user.id, team_id)


@router.put("/settings")
def settings(
    team_id: UUID, data: opponents.SettingsInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    limited(session, user, "action", 60)
    return opponents.update_settings(session, user.id, team_id, data)


@router.get("/search")
def search(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    modality: Modality,
    category: opponents.Category,
    state: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    municipality: Annotated[int | None, Query(ge=1100000, le=5399999)] = None,
    offset: Offset = 0,
) -> dict[str, object]:
    # Searching is free on every plan; the limit only protects against abuse.
    limited(session, user, "search", 120)
    return opponents.search(
        session,
        user.id,
        team_id,
        modality=modality,
        category=category,
        state=state,
        municipality=municipality,
        offset=offset,
    )


@router.get("/teams/{opponent_id}")
def profile(
    team_id: UUID, opponent_id: UUID, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    limited(session, user, "profile", 120)
    return opponents.profile(session, user.id, team_id, opponent_id)


@router.get("/challenges")
def challenge_list(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    direction: Literal["received", "sent"] = "received",
    offset: Offset = 0,
) -> dict[str, object]:
    return challenges.listing(session, user.id, team_id, direction, offset)


@router.post("/challenges", status_code=201)
def challenge(
    team_id: UUID, data: challenges.ChallengeInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    limited(session, user, "challenge", 20)
    return challenges.create(session, user.id, team_id, data)


@router.post("/challenges/{challenge_id}/{decision}")
def decide(
    team_id: UUID,
    challenge_id: UUID,
    decision: Literal["accept", "reject", "cancel"],
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, object]:
    limited(session, user, "action", 60)
    return challenges.respond(session, user.id, team_id, challenge_id, decision)


@router.get("/fixtures")
def fixture_list(
    team_id: UUID, session: SessionDep, user: CurrentUser, offset: Offset = 0
) -> dict[str, object]:
    return fixtures.listing(session, user.id, team_id, offset)


@router.get("/fixtures/{fixture_id}")
def fixture(
    team_id: UUID, fixture_id: UUID, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return fixtures.detail(session, user.id, team_id, fixture_id)


@router.post("/fixtures/{fixture_id}/score")
def score(
    team_id: UUID,
    fixture_id: UUID,
    data: fixtures.ScoreInput,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, object]:
    limited(session, user, "action", 60)
    return fixtures.submit(session, user.id, team_id, fixture_id, data, confirmation=False)


@router.post("/fixtures/{fixture_id}/confirm")
def confirm(
    team_id: UUID,
    fixture_id: UUID,
    data: fixtures.ScoreInput,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, object]:
    limited(session, user, "action", 60)
    return fixtures.submit(session, user.id, team_id, fixture_id, data, confirmation=True)


@router.post("/fixtures/{fixture_id}/review")
def review(
    team_id: UUID,
    fixture_id: UUID,
    data: fixtures.ReviewInput,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, object]:
    limited(session, user, "action", 60)
    return fixtures.review(session, user.id, team_id, fixture_id, data)
