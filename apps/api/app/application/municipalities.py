"""Official IBGE municipalities (reference table seeded by migration 0016).

A location is always one existing municipality of the chosen UF, identified by its IBGE
code; free text is never turned into a municipality.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.policies import Conflict, NotFound
from app.domain.team_identity import STATES, normalized
from app.infrastructure.models import Municipality, Team


def official(session: Session, state: str, code: int) -> Municipality:
    item = session.get(Municipality, code)
    if item is None or item.state != state:
        raise Conflict("Escolha um município da UF selecionada.")
    return item


def listing(session: Session, state: str) -> list[dict[str, object]]:
    if state not in STATES:
        raise NotFound("UF não encontrada.")
    items = session.scalars(select(Municipality).where(Municipality.state == state))
    # Accent-insensitive order: "Águia Branca" sorts with the As, as users expect.
    return [
        {"code": item.code, "name": item.name}
        for item in sorted(items, key=lambda item: normalized(item.name))
    ]


def obvious_match(session: Session, team: Team) -> Municipality | None:
    """Suggestion for an unconfirmed team: the one municipality of its UF whose name equals
    the typed city (ignoring accents, case and spaces). Never saved automatically."""
    target = normalized(team.city)
    matches = [
        item
        for item in session.scalars(select(Municipality).where(Municipality.state == team.state))
        if normalized(item.name) == target
    ]
    return matches[0] if len(matches) == 1 else None
