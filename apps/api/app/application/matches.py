"""Independent results for saved formation squads, serialized on the team lock."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import authorize, find_event, require_open
from app.domain.policies import Conflict, NotFound
from app.infrastructure.formation_models import Formation, FormationSquad
from app.infrastructure.match_models import EventMatch


def find_match(session: Session, team_id: UUID, event_id: UUID, match_id: UUID) -> EventMatch:
    match = session.scalar(
        select(EventMatch)
        .where(
            EventMatch.id == match_id,
            EventMatch.team_id == team_id,
            EventMatch.event_id == event_id,
        )
        .execution_options(populate_existing=True)
    )
    if match is None:
        raise NotFound("Partida não encontrada")
    return match


def list_matches(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID
) -> list[EventMatch]:
    authorize(session, user_id, team_id)
    find_event(session, team_id, event_id)
    return list(
        session.scalars(
            select(EventMatch)
            .where(EventMatch.team_id == team_id, EventMatch.event_id == event_id)
            .order_by(EventMatch.created_at, EventMatch.id)
        )
    )


def create(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    formation_id: UUID,
    expected_formation_version: int,
    home_formation_team_id: UUID,
    away_formation_team_id: UUID,
) -> EventMatch:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    formation = session.scalar(
        select(Formation)
        .where(
            Formation.id == formation_id,
            Formation.team_id == team_id,
            Formation.event_id == event_id,
        )
        .execution_options(populate_existing=True)
    )
    if formation is None or event.kind != "PELADA":
        raise NotFound("Formação não encontrada nesta pelada")
    if formation.version != expected_formation_version:
        raise Conflict("A formação foi alterada. Recarregue antes de criar a partida")
    if home_formation_team_id == away_formation_team_id:
        raise Conflict("Escolha duas equipes diferentes")
    squads = set(
        session.scalars(
            select(FormationSquad.id).where(FormationSquad.formation_id == formation.id)
        )
    )
    if not {home_formation_team_id, away_formation_team_id} <= squads:
        raise NotFound("Equipe não pertence a esta formação")
    match = EventMatch(
        team_id=team_id,
        event_id=event_id,
        formation_id=formation_id,
        home_formation_team_id=home_formation_team_id,
        away_formation_team_id=away_formation_team_id,
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def change(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    action: Literal["start", "score", "finish", "cancel"],
    expected_version: int,
    confirm: bool = False,
    home_score: int | None = None,
    away_score: int | None = None,
) -> EventMatch:
    authorize(session, user_id, team_id, write=True, manage=True)
    require_open(find_event(session, team_id, event_id))
    match = find_match(session, team_id, event_id, match_id)
    if match.version != expected_version:
        raise Conflict("O placar foi atualizado em outro dispositivo. Recarregue para continuar")
    now = datetime.now(UTC)
    if action == "start":
        if match.status != "SCHEDULED":
            raise Conflict("Somente uma partida agendada pode ser iniciada")
        match.status, match.started_at = "IN_PROGRESS", now
    elif action == "score":
        if match.status not in {"IN_PROGRESS", "FINISHED"}:
            raise Conflict("O placar só pode ser alterado em partida iniciada ou finalizada")
        if (
            home_score is None
            or away_score is None
            or not (0 <= home_score <= 999 and 0 <= away_score <= 999)
        ):
            raise Conflict("Informe placares inteiros entre 0 e 999")
        if match.status == "FINISHED":
            if not confirm:
                raise Conflict("Confirme a correção do resultado")
            match.corrected_at, match.corrected_by_user_id = now, user_id
        match.home_score, match.away_score = home_score, away_score
    elif action == "finish":
        if match.status != "IN_PROGRESS" or not confirm:
            raise Conflict("Inicie a partida e confirme a finalização")
        match.status, match.finished_at = "FINISHED", now
    elif action == "cancel":
        if match.status == "CANCELLED" or not confirm:
            raise Conflict("Confirme o cancelamento de uma partida não cancelada")
        match.status = "CANCELLED"
    match.version += 1
    match.updated_at = now
    session.commit()
    session.refresh(match)
    return match
