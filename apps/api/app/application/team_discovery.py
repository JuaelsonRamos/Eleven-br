"""Bounded public team discovery; all membership/request state belongs to the caller."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.join_requests import public_team
from app.domain.team_codes import normalize_code
from app.infrastructure.join_models import TeamJoinRequest
from app.infrastructure.models import Player, Team, TeamMembership


def search(
    session: Session, user_id: UUID, query: str, offset: int, limit: int
) -> dict[str, object]:
    query = " ".join(query.split())
    if len(query) < 2:
        return {"items": [], "has_more": False}
    name = func.regexp_replace(func.trim(Team.name), r"\s+", " ", "g")
    teams = list(
        session.scalars(
            select(Team)
            .where(
                Team.status == "active",
                or_(Team.code == normalize_code(query), name.icontains(query, autoescape=True)),
            )
            .order_by(func.lower(Team.name), Team.id)
            .offset(offset)
            .limit(limit + 1)
        )
    )
    ids = [team.id for team in teams[:limit]]
    members = {
        team_id: status
        for team_id, status in session.execute(
            select(TeamMembership.team_id, TeamMembership.status)
            .join(Player, Player.id == TeamMembership.player_id)
            .where(
                TeamMembership.team_id.in_(ids),
                Player.user_id == user_id,
                TeamMembership.status != "removed",
            )
        ).all()
    }
    latest: dict[UUID, str] = {}
    for item in session.scalars(
        select(TeamJoinRequest)
        .where(TeamJoinRequest.team_id.in_(ids), TeamJoinRequest.user_id == user_id)
        .distinct(TeamJoinRequest.team_id)
        .order_by(
            TeamJoinRequest.team_id, TeamJoinRequest.created_at.desc(), TeamJoinRequest.id.desc()
        )
    ):
        latest[item.team_id] = item.status
    return {
        "items": [
            {
                "team": public_team(team),
                "membership_status": members.get(team.id),
                "pending": latest.get(team.id) == "PENDING",
                "request_status": latest.get(team.id),
            }
            for team in teams[:limit]
        ],
        "has_more": len(teams) > limit,
    }
