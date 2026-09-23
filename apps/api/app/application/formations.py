"""One active formation per occurrence. Writes share the event/roster team lock."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.events import authorize, find_event, require_open
from app.application.roster import roster_name
from app.application.team_profiles import membership_context
from app.domain.formations import MAX_PARTICIPANTS, Choice, random_teams
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.event_models import EventAttendance, EventGuest
from app.infrastructure.formation_models import Formation, FormationParticipant, FormationSquad
from app.infrastructure.models import Player, TeamMembership


@dataclass(frozen=True)
class Candidate:
    kind: Literal["member", "guest"]
    source_id: UUID
    name: str


def candidates(session: Session, team_id: UUID, event_id: UUID) -> list[Candidate]:
    members = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .join(EventAttendance, EventAttendance.membership_id == TeamMembership.id)
        .where(
            TeamMembership.team_id == team_id,
            TeamMembership.status == "active",
            EventAttendance.event_id == event_id,
            EventAttendance.response == "VOU",
        )
        .order_by(TeamMembership.id)
    ).all()
    guests = session.scalars(
        select(EventGuest)
        .where(EventGuest.event_id == event_id, EventGuest.removed_at.is_(None))
        .order_by(EventGuest.id)
    ).all()
    return [Candidate("member", m.id, m.nickname or roster_name(m, p)) for m, p in members] + [
        Candidate("guest", g.id, g.name) for g in guests
    ]


def fingerprint(pool: list[Candidate]) -> str:
    return sha256("\n".join(sorted(f"{p.kind}:{p.source_id}" for p in pool)).encode()).hexdigest()


def current(session: Session, event_id: UUID) -> Formation | None:
    return session.scalar(
        select(Formation)
        .where(Formation.event_id == event_id)
        .execution_options(populate_existing=True)
    )


def detail(session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    event = find_event(session, team_id, event_id)
    _, permission = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)
    pool = candidates(session, team_id, event_id)
    value = fingerprint(pool)
    formation = current(session, event_id)
    result: dict[str, object] = {
        "can_manage": permission and event.status == "open" and event.kind == "PELADA",
        "participants": pool,
        "fingerprint": value,
        "formation": None,
        "participants_changed": bool(formation and formation.roster_fingerprint != value),
    }
    if formation:
        squads = session.scalars(
            select(FormationSquad)
            .where(FormationSquad.formation_id == formation.id)
            .order_by(FormationSquad.number)
        ).all()
        people = session.scalars(
            select(FormationParticipant)
            .where(FormationParticipant.formation_id == formation.id)
            .order_by(
                FormationParticipant.goalkeeper.desc(),
                FormationParticipant.name,
                FormationParticipant.id,
            )
        ).all()
        result["formation"] = {
            "id": formation.id,
            "version": formation.version,
            "method": formation.method,
            "team_count": formation.team_count,
            "updated_at": formation.updated_at,
            "squads": [
                {
                    "id": s.id,
                    "number": s.number,
                    "name": f"Time {s.number}",
                    "participants": [p for p in people if p.squad_id == s.id],
                }
                for s in squads
            ],
            "excluded": [p for p in people if p.squad_id is None],
        }
    return result


def draw(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    choices: list[Choice],
    team_count: int,
    expected_fingerprint: str,
    expected_version: int | None,
    confirm_replace: bool,
) -> None:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    if event.kind != "PELADA":
        raise Conflict("O sorteio está disponível para peladas")
    pool = candidates(session, team_id, event_id)
    signature = fingerprint(pool)
    if len(pool) > MAX_PARTICIPANTS:
        raise Conflict("O sorteio suporta até 256 participantes por pelada")
    if signature != expected_fingerprint:
        raise Conflict("A lista de participantes mudou. Atualize antes de sortear")
    allowed = {(p.kind, p.source_id) for p in pool}
    if any((p.kind, p.source_id) not in allowed for p in choices):
        raise Conflict("Use somente confirmados ativos e convidados deste evento")
    groups = random_teams(choices, team_count)
    formation = current(session, event_id)
    if formation:
        if not confirm_replace or expected_version != formation.version:
            raise Conflict(
                "A formação já existe ou foi alterada. Atualize e confirme a substituição"
            )
        session.execute(
            delete(FormationParticipant).where(FormationParticipant.formation_id == formation.id)
        )
        session.execute(delete(FormationSquad).where(FormationSquad.formation_id == formation.id))
        formation.version += 1
        formation.team_count = team_count
        formation.roster_fingerprint = signature
    else:
        if expected_version is not None:
            raise Conflict("A formação mudou. Atualize antes de continuar")
        formation = Formation(
            team_id=team_id,
            event_id=event_id,
            version=1,
            team_count=team_count,
            method="random",
            roster_fingerprint=signature,
        )
        session.add(formation)
    session.flush()
    assignments: dict[tuple[str, UUID], tuple[UUID, bool]] = {}
    for number, group in enumerate(groups, 1):
        squad = FormationSquad(formation_id=formation.id, number=number)
        session.add(squad)
        session.flush()
        assignments.update({(p.kind, p.source_id): (squad.id, p.goalkeeper) for p in group})
    for person in pool:
        assignment = assignments.get((person.kind, person.source_id))
        session.add(
            FormationParticipant(
                team_id=team_id,
                event_id=event_id,
                formation_id=formation.id,
                membership_id=person.source_id if person.kind == "member" else None,
                guest_id=person.source_id if person.kind == "guest" else None,
                name=person.name,
                squad_id=assignment[0] if assignment else None,
                goalkeeper=assignment[1] if assignment else False,
            )
        )
    session.commit()


def move(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    event_id: UUID,
    formation_id: UUID,
    participant_id: UUID,
    squad_id: UUID,
    expected_version: int,
) -> None:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    if event.kind != "PELADA":
        raise Conflict("O sorteio está disponível para peladas")
    formation = current(session, event_id)
    if formation is None or formation.id != formation_id:
        raise NotFound("Formação não encontrada")
    if formation.version != expected_version:
        raise Conflict("A formação foi alterada. Atualize antes de mover")
    person = session.scalar(
        select(FormationParticipant).where(
            FormationParticipant.id == participant_id,
            FormationParticipant.formation_id == formation.id,
            FormationParticipant.squad_id.is_not(None),
        )
    )
    squad = session.scalar(
        select(FormationSquad).where(
            FormationSquad.id == squad_id, FormationSquad.formation_id == formation.id
        )
    )
    if person is None or squad is None:
        raise NotFound("Participante ou equipe não pertence a esta formação")
    if person.squad_id != squad.id:
        person.squad_id = squad.id
        formation.version += 1
    session.commit()
