"""Team location confirmation and changes, by the current President only.

New teams are created with a confirmed official location. Legacy teams keep the typed
city/UF, unconfirmed, until the President confirms; an unconfirmed location is only a
search fallback and never an official location for geographic features.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.events import authorize
from app.application.municipalities import obvious_match, official
from app.application.team_audit import record
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain.policies import Forbidden
from app.infrastructure.models import Team


def snapshot(team: Team) -> dict[str, object]:
    return {
        "city": team.city,
        "state": team.state,
        "municipality_code": team.municipality_code,
        "confirmed": team.location_confirmed_at is not None,
    }


def location(session: Session, user_id: UUID, team_id: UUID) -> dict[str, object]:
    team = require_membership(session, user_id=user_id, team_id=team_id)
    match = None if team.location_confirmed_at else obvious_match(session, team)
    return {
        "city": team.city,
        "state": team.state,
        "municipality_code": team.municipality_code,
        "confirmed": team.location_confirmed_at is not None,
        "confirmed_at": team.location_confirmed_at,
        "suggestion": {"code": match.code, "name": match.name, "state": match.state}
        if match
        else None,
        "can_change": membership_context(session, team, user_id)[0] == "president",
    }


def change(
    session: Session, user_id: UUID, team_id: UUID, *, state: str, municipality_code: int
) -> Team:
    """Confirms (legacy) or changes the official location; the previous one stays audited."""
    team = authorize(session, user_id, team_id, write=True)
    if membership_context(session, team, user_id)[0] != "president":
        raise Forbidden("Somente o Presidente pode confirmar ou alterar a localização do time.")
    item = official(session, state, municipality_code)
    before = snapshot(team)
    action = "LOCATION_CHANGED" if team.location_confirmed_at else "LOCATION_CONFIRMED"
    team.state, team.city, team.municipality_code = item.state, item.name, item.code
    team.location_confirmed_at = datetime.now(UTC)
    record(session, team.id, user_id, team.id, action, before, snapshot(team))
    session.commit()
    return team
