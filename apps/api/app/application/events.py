"""Team-scoped events; all writes serialize with roster changes on the team row."""

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.application.roster import roster_name
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain.events import EventDraft
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.event_models import Event, EventAttendance, EventGuest, EventSeries
from app.infrastructure.models import Player, Team, TeamMembership


def authorize(
    session: Session, user_id: UUID, team_id: UUID, *, write: bool = False, manage: bool = False
) -> Team:
    if write:
        session.scalar(
            select(Team)
            .where(Team.id == team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return require_membership(
        session,
        user_id=user_id,
        team_id=team_id,
        permission=Permission.MANAGE_EVENTS if manage else None,
    )


def find_event(session: Session, team_id: UUID, event_id: UUID) -> Event:
    event = session.scalar(select(Event).where(Event.id == event_id, Event.team_id == team_id))
    if event is None:
        raise NotFound("Evento não encontrado")
    return event


def require_open(event: Event) -> None:
    if event.status != "open":
        raise Conflict("Este evento foi cancelado e não aceita alterações")


def validate_modality(team: Team, draft: EventDraft) -> None:
    if draft.modality not in team.modalities:
        raise Conflict("Selecione uma modalidade do time")


def create_event(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    draft: EventDraft,
    recurring_weekly: bool = False,
    recurring_until: date | None = None,
) -> Event:
    team = authorize(session, user_id, team_id, write=True, manage=True)
    validate_modality(team, draft)
    if recurring_weekly or recurring_until is not None:
        if draft.kind != "PELADA" or (
            recurring_until is not None and (recurring_until - draft.date).days < 7
        ):
            raise Conflict("Recorrência semanal inválida")
        series = EventSeries(
            team_id=team.id,
            start_date=draft.date,
            end_date=recurring_until,
            modality=draft.modality,
            title=draft.title,
            time=draft.time,
            location=draft.location,
            notes=draft.notes,
        )
        session.add(series)
        session.flush()
        materialize(session, series, today=draft.date)
        first = session.scalars(
            select(Event).where(
                Event.series_id == series.id,
                Event.recurrence_date == draft.date,
            )
        ).one()
    else:
        first = Event(**asdict(draft), team_id=team.id)
        session.add(first)
    session.commit()
    return first


def materialize(session: Session, series: EventSeries, *, today: date) -> None:
    """At most nine weekly dates per series/access, no historical backfill or worker.

    The caller holds the team lock. The unique key is an additional database guard;
    existing dates, edits, cancellations, answers and guests are never overwritten.
    """
    if series.status != "active":
        return
    anchor = max(series.start_date, today)
    horizon = anchor + timedelta(days=min(56, (date.max - anchor).days))
    if series.end_date is not None:
        horizon = min(horizon, series.end_date)
    elapsed = (anchor - series.start_date).days
    offset = (7 - elapsed % 7) % 7
    if (horizon - anchor).days < offset:
        return
    day = anchor + timedelta(days=offset)
    while day <= horizon:
        session.execute(
            insert(Event)
            .values(
                team_id=series.team_id,
                series_id=series.id,
                recurrence_date=day,
                date=day,
                time=series.time,
                kind="PELADA",
                modality=series.modality,
                title=series.title,
                location=series.location,
                notes=series.notes,
            )
            .on_conflict_do_nothing(constraint="uq_events_series_date")
        )
        if (horizon - day).days < 7:
            break
        day += timedelta(days=7)


def edit_event(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID, draft: EventDraft
) -> Event:
    team = authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    validate_modality(team, draft)
    if event.series_id is not None and draft.kind != "PELADA":
        raise Conflict("Uma ocorrência de pelada deve continuar sendo pelada")
    for key, value in asdict(draft).items():
        setattr(event, key, value)
    session.commit()
    return event


def cancel_event(session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID) -> Event:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    event.status = "cancelled"
    session.commit()
    return event


def cancel_series(session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID) -> Event:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    series = session.scalar(
        select(EventSeries).where(
            EventSeries.id == event.series_id,
            EventSeries.team_id == team_id,
        )
    )
    if series is None:
        raise Conflict("Este evento não possui recorrência")
    series.status = "cancelled"
    session.execute(
        update(Event)
        .where(
            Event.series_id == series.id,
            Event.date >= date.today(),
        )
        .values(status="cancelled")
    )
    session.commit()
    return event


def respond(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID, response: str
) -> Event:
    authorize(session, user_id, team_id, write=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    member = session.scalars(
        select(TeamMembership)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(
            TeamMembership.team_id == team_id,
            TeamMembership.status == "active",
            Player.user_id == user_id,
        )
    ).one()
    statement = insert(EventAttendance).values(
        team_id=team_id, event_id=event_id, membership_id=member.id, response=response
    )
    session.execute(
        statement.on_conflict_do_update(
            constraint="uq_event_attendance_member",
            set_={"response": response, "updated_at": func.now()},
        )
    )
    session.commit()
    return event


def add_guest(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID, name: str
) -> Event:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    session.add(EventGuest(event_id=event.id, name=name))
    session.commit()
    return event


def remove_guest(
    session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID, guest_id: UUID
) -> Event:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    guest = session.scalar(
        select(EventGuest).where(
            EventGuest.id == guest_id,
            EventGuest.event_id == event.id,
            EventGuest.removed_at.is_(None),
        )
    )
    if guest is None:
        raise NotFound("Convidado não encontrado")
    guest.removed_at = datetime.now(UTC)
    session.commit()
    return event


def snapshots(
    session: Session, team: Team, user_id: UUID, events: list[Event]
) -> tuple[bool, list[dict[str, object]]]:
    """Batch queries avoid a query per event or player; no private roster contacts."""
    _, can_manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)
    members = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(
            TeamMembership.team_id == team.id,
            TeamMembership.status == "active",
        )
        .order_by(Player.display_name, TeamMembership.id)
    ).all()
    ids = [event.id for event in events]
    series = {
        row.id: row
        for row in session.scalars(
            select(EventSeries).where(
                EventSeries.team_id == team.id,
                EventSeries.id.in_([e.series_id for e in events if e.series_id]),
            )
        )
    }
    answers = {
        (row.event_id, row.membership_id): row.response
        for row in session.scalars(select(EventAttendance).where(EventAttendance.event_id.in_(ids)))
    }
    guests = session.scalars(
        select(EventGuest)
        .where(EventGuest.event_id.in_(ids), EventGuest.removed_at.is_(None))
        .order_by(EventGuest.name, EventGuest.id)
    ).all()
    result: list[dict[str, object]] = []
    for event in events:
        participants = [
            {
                "membership_id": member.id,
                "player_id": player.id,
                "name": member.nickname or roster_name(member, player),
                "response": answers.get((event.id, member.id), "PENDENTE"),
            }
            for member, player in members
        ]
        own = next(member.id for member, player in members if player.user_id == user_id)
        result.append(
            {
                **{
                    key: getattr(event, key)
                    for key in (
                        "id",
                        "team_id",
                        "series_id",
                        "modality",
                        "kind",
                        "title",
                        "date",
                        "time",
                        "location",
                        "notes",
                        "opponent",
                        "status",
                        "created_at",
                        "updated_at",
                    )
                },
                "can_manage": can_manage,
                "recurring_until": series[event.series_id].end_date if event.series_id else None,
                "recurrence_status": series[event.series_id].status if event.series_id else None,
                "my_response": answers.get((event.id, own), "PENDENTE"),
                "going": sum(p["response"] == "VOU" for p in participants),
                "not_going": sum(p["response"] == "NAO_VOU" for p in participants),
                "pending": sum(p["response"] == "PENDENTE" for p in participants),
                "participants": participants,
                "guests": [g for g in guests if g.event_id == event.id],
            }
        )
    return can_manage, result


def list_events(session: Session, *, user_id: UUID, team_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    for series in session.scalars(
        select(EventSeries).where(
            EventSeries.team_id == team_id,
            EventSeries.status == "active",
        )
    ):
        materialize(session, series, today=date.today())
    session.flush()
    events = list(
        session.scalars(
            select(Event).where(Event.team_id == team.id).order_by(Event.date, Event.time, Event.id)
        )
    )
    can_manage, items = snapshots(session, team, user_id, events)
    session.commit()
    return {"can_manage": can_manage, "items": items}


def detail(session: Session, *, user_id: UUID, team_id: UUID, event_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    event = find_event(session, team_id, event_id)
    return snapshots(session, team, user_id, [event])[1][0]
