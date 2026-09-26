"""Identified match incidents; official scores remain independent."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import authorize, find_event, require_open
from app.application.matches import find_match
from app.application.team_profiles import membership_context
from app.domain.match_events import MatchEventType
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.formation_models import FormationParticipant, FormationSquad
from app.infrastructure.match_event_models import MatchEvent
from app.infrastructure.match_models import EventMatch


def participants(session: Session, match: EventMatch) -> list[FormationParticipant]:
    # Saved participation, not today's attendance or roster: history stays usable.
    return list(
        session.scalars(
            select(FormationParticipant)
            .where(
                FormationParticipant.team_id == match.team_id,
                FormationParticipant.event_id == match.event_id,
                FormationParticipant.formation_id == match.formation_id,
                FormationParticipant.squad_id.in_(
                    [match.home_formation_team_id, match.away_formation_team_id]
                ),
            )
            .order_by(FormationParticipant.name, FormationParticipant.id)
        )
    )


def detail(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID, match_id: UUID
) -> dict[str, object]:
    # Same lock as writes gives one consistent score/events/version snapshot.
    team = authorize(session, user_id, team_id, write=True)
    event = find_event(session, team_id, event_id)
    match = find_match(session, team_id, event_id, match_id)
    _, permission = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)
    people = participants(session, match)
    items = list(
        session.scalars(
            select(MatchEvent)
            .where(
                MatchEvent.match_id == match.id,
                MatchEvent.removed_at.is_(None),
            )
            .order_by(MatchEvent.created_at, MatchEvent.id)
        )
    )
    squads = {
        s.id: f"Time {s.number}"
        for s in session.scalars(
            select(FormationSquad).where(
                FormationSquad.id.in_([match.home_formation_team_id, match.away_formation_team_id])
            )
        )
    }
    goals = []
    for squad_id, score in [
        (match.home_formation_team_id, match.home_score),
        (match.away_formation_team_id, match.away_score),
    ]:
        identified = sum(item.type == "GOAL" and item.squad_id == squad_id for item in items)
        goals.append(
            {
                "squad_id": squad_id,
                "name": squads[squad_id],
                "score": score,
                "identified": identified,
                "missing": max(0, score - identified),
                "excess": max(0, identified - score),
            }
        )
    return {
        "match": match,
        "can_manage": permission
        and event.status == "open"
        and match.status in {"IN_PROGRESS", "FINISHED"},
        "participants": [
            {
                "id": p.id,
                "name": p.name,
                "is_guest": p.guest_id is not None,
                "squad_id": p.squad_id,
                "squad_name": squads[p.squad_id],
            }
            for p in people
            if p.squad_id
        ],
        "items": items,
        "goals": goals,
    }


def writable_match(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    expected_version: int,
) -> EventMatch:
    authorize(session, user_id, team_id, write=True, manage=True)
    require_open(find_event(session, team_id, event_id))
    match = find_match(session, team_id, event_id, match_id)
    if match.status not in {"IN_PROGRESS", "FINISHED"}:
        raise Conflict("Registre acontecimentos somente em partida iniciada ou finalizada")
    if match.version != expected_version:
        raise Conflict(
            "A partida foi atualizada em outro dispositivo ou este envio já foi recebido. "
            "Recarregue para continuar"
        )
    return match


def validate_participants(
    session: Session,
    match: EventMatch,
    type: MatchEventType,
    participant_id: UUID,
    assist_participant_id: UUID | None,
) -> UUID:
    people = {p.id: p for p in participants(session, match)}
    person = people.get(participant_id)
    if person is None or person.squad_id is None:
        raise NotFound("Participante não pertence às equipes desta partida")
    if assist_participant_id is not None:
        if type != "GOAL":
            raise Conflict("Assistência só pode ser informada em um gol")
        assistant = people.get(assist_participant_id)
        if assistant is None:
            raise NotFound("Participante da assistência não pertence a esta partida")
        if assistant.id == person.id or assistant.squad_id != person.squad_id:
            raise Conflict("A assistência deve ser de outro participante da mesma equipe")
    return person.squad_id


def find_incident(session: Session, match: EventMatch, match_event_id: UUID) -> MatchEvent:
    item = session.scalar(
        select(MatchEvent)
        .where(
            MatchEvent.id == match_event_id,
            MatchEvent.match_id == match.id,
            MatchEvent.team_id == match.team_id,
            MatchEvent.removed_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise NotFound("Registro não encontrado nesta partida")
    return item


def save(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    expected_version: int,
    type: MatchEventType,
    participant_id: UUID,
    assist_participant_id: UUID | None,
    match_event_id: UUID | None = None,
) -> None:
    match = writable_match(
        session,
        user_id=user_id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        expected_version=expected_version,
    )
    item = find_incident(session, match, match_event_id) if match_event_id else None
    squad_id = validate_participants(session, match, type, participant_id, assist_participant_id)
    now = datetime.now(UTC)
    if item is None:
        item = MatchEvent(
            team_id=team_id,
            event_id=event_id,
            match_id=match.id,
            formation_id=match.formation_id,
            created_by_user_id=user_id,
        )
        session.add(item)
    else:
        if (item.type == "GOAL") != (type == "GOAL"):
            raise Conflict("Edite gols e cartões separadamente")
        item.updated_by_user_id = user_id
        item.updated_at = now
    item.type, item.participant_id, item.assist_participant_id = (
        type,
        participant_id,
        assist_participant_id,
    )
    item.squad_id = squad_id
    match.version += 1
    match.updated_at = now
    session.commit()


def remove(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    match_event_id: UUID,
    expected_version: int,
    confirm: bool,
) -> None:
    match = writable_match(
        session,
        user_id=user_id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        expected_version=expected_version,
    )
    item = find_incident(session, match, match_event_id)
    if not confirm:
        raise Conflict("Confirme a remoção deste registro")
    now = datetime.now(UTC)
    item.removed_at, item.updated_at, item.updated_by_user_id = now, now, user_id
    match.version += 1
    match.updated_at = now
    session.commit()
