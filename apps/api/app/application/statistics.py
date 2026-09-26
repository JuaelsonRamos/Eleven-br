"""Read-only statistics from saved participation and identified incidents. No counters."""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.selectable import CTE

from app.application.events import authorize
from app.application.roster import roster_name
from app.domain.policies import NotFound
from app.domain.statistics import Period, PersonStatistics, Totals, period_start, ranking
from app.infrastructure.event_models import Event, EventGuest
from app.infrastructure.formation_models import FormationParticipant, FormationSquad
from app.infrastructure.match_event_models import MatchEvent
from app.infrastructure.match_models import EventMatch
from app.infrastructure.models import Player, TeamMembership


def today_local() -> date:
    return date.today()


def match_scope(team_id: UUID, period: Period, modality: str | None) -> CTE:
    query = (
        select(
            EventMatch.id,
            EventMatch.event_id,
            EventMatch.formation_id,
            EventMatch.home_formation_team_id,
            EventMatch.away_formation_team_id,
            EventMatch.home_score,
            EventMatch.away_score,
            EventMatch.created_at,
            Event.date,
            Event.time,
            Event.title,
            Event.modality,
        )
        .join(Event, and_(Event.id == EventMatch.event_id, Event.team_id == team_id))
        .where(EventMatch.team_id == team_id, EventMatch.status == "FINISHED")
    )
    today = today_local()
    start = period_start(period, today)
    if start is not None:
        query = query.where(Event.date >= start, Event.date <= today)
    if modality:
        query = query.where(Event.modality == modality)
    return query.cte("finished_matches")


def appearances(team_id: UUID, scope: CTE) -> CTE:
    incidents = (
        select(MatchEvent)
        .join(scope, scope.c.id == MatchEvent.match_id)
        .where(MatchEvent.team_id == team_id, MatchEvent.removed_at.is_(None))
        .cte("valid_incidents")
    )
    authors = (
        select(
            incidents.c.match_id,
            incidents.c.participant_id,
            func.count().filter(incidents.c.type == "GOAL").label("goals"),
            func.count().filter(incidents.c.type == "YELLOW_CARD").label("yellow_cards"),
            func.count().filter(incidents.c.type == "RED_CARD").label("red_cards"),
        )
        .group_by(incidents.c.match_id, incidents.c.participant_id)
        .cte("authors")
    )
    assists = (
        select(
            incidents.c.match_id, incidents.c.assist_participant_id, func.count().label("assists")
        )
        .where(incidents.c.type == "GOAL", incidents.c.assist_participant_id.is_not(None))
        .group_by(incidents.c.match_id, incidents.c.assist_participant_id)
        .cte("assists")
    )
    person = FormationParticipant
    return (
        select(
            scope.c.id.label("match_id"),
            person.membership_id,
            person.guest_id,
            func.coalesce(authors.c.goals, 0).label("goals"),
            func.coalesce(assists.c.assists, 0).label("assists"),
            func.coalesce(authors.c.yellow_cards, 0).label("yellow_cards"),
            func.coalesce(authors.c.red_cards, 0).label("red_cards"),
        )
        .select_from(scope)
        .join(
            person,
            and_(
                person.team_id == team_id,
                person.event_id == scope.c.event_id,
                person.formation_id == scope.c.formation_id,
                or_(
                    person.squad_id == scope.c.home_formation_team_id,
                    person.squad_id == scope.c.away_formation_team_id,
                ),
            ),
        )
        .outerjoin(
            authors, and_(authors.c.match_id == scope.c.id, authors.c.participant_id == person.id)
        )
        .outerjoin(
            assists,
            and_(assists.c.match_id == scope.c.id, assists.c.assist_participant_id == person.id),
        )
        .cte("appearances")
    )


def totals_query(rows: CTE) -> Select[Any]:
    return select(
        func.count().label("matches"),
        *[
            func.coalesce(func.sum(rows.c[key]), 0).label(key)
            for key in ["goals", "assists", "yellow_cards", "red_cards"]
        ],
    )


def overview(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    period: Period = "all",
    modality: str | None = None,
) -> dict[str, object]:
    # Existing team lock keeps the several aggregate reads consistent with corrections.
    team = authorize(session, user_id, team_id, write=True)
    scope = match_scope(team_id, period, modality)
    rows = appearances(team_id, scope)
    aggregates = (
        session.execute(
            totals_query(rows)
            .add_columns(rows.c.membership_id, rows.c.guest_id)
            .group_by(rows.c.membership_id, rows.c.guest_id)
        )
        .mappings()
        .all()
    )
    totals = {
        (r["membership_id"], r["guest_id"]): Totals(
            **{
                key: int(r[key])
                for key in ["matches", "goals", "assists", "yellow_cards", "red_cards"]
            }
        )
        for r in aggregates
    }
    people: list[PersonStatistics] = []
    for member, player in session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id)
    ):
        counts = totals.get((member.id, None), Totals())
        if member.status == "active" or counts.matches:
            people.append(
                PersonStatistics(
                    member.id,
                    "member",
                    member.nickname or roster_name(member, player),
                    counts,
                    player.id,
                    player.photo_url,
                    member.status != "active",
                )
            )
    guest_ids = [guest for _, guest in totals if guest]
    if guest_ids:
        for guest, event in session.execute(
            select(EventGuest, Event)
            .join(Event, Event.id == EventGuest.event_id)
            .where(Event.team_id == team_id, EventGuest.id.in_(guest_ids))
        ):
            people.append(
                PersonStatistics(
                    guest.id, "guest", guest.name, totals[(None, guest.id)], event_date=event.date
                )
            )
    people.sort(key=lambda p: (p.name.casefold(), p.kind, str(p.id)))
    summary = Totals(matches=session.scalar(select(func.count()).select_from(scope)) or 0)
    for counts in totals.values():
        summary.goals += counts.goals
        summary.assists += counts.assists
        summary.yellow_cards += counts.yellow_cards
        summary.red_cards += counts.red_cards
    relevant = set(team.modalities) | set(
        session.scalars(select(Event.modality).where(Event.team_id == team_id).distinct())
    )
    return {
        "summary": summary,
        "players": people,
        "scorers": ranking(people),
        "assistants": ranking(people, assists=True),
        "discipline": [p for p in people if p.totals.yellow_cards or p.totals.red_cards],
        "modalities": sorted(relevant),
        "period": period,
        "modality": modality,
    }


def profile(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    person_id: UUID,
    kind: Literal["member", "guest"],
    period: Period = "all",
    modality: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    authorize(session, user_id, team_id, write=True)
    if kind == "member":
        identity = session.execute(
            select(TeamMembership, Player)
            .join(Player, Player.id == TeamMembership.player_id)
            .where(TeamMembership.team_id == team_id, TeamMembership.id == person_id)
        ).first()
        if identity is None:
            raise NotFound("Jogador não encontrado neste time")
        member, player = identity
        person = PersonStatistics(
            member.id,
            "member",
            member.nickname or roster_name(member, player),
            Totals(),
            player.id,
            player.photo_url,
            member.status != "active",
        )
    else:
        identity_guest = session.execute(
            select(EventGuest, Event)
            .join(Event, Event.id == EventGuest.event_id)
            .where(Event.team_id == team_id, EventGuest.id == person_id)
        ).first()
        if identity_guest is None:
            raise NotFound("Convidado não encontrado neste time")
        guest, event = identity_guest
        person = PersonStatistics(guest.id, "guest", guest.name, Totals(), event_date=event.date)
    scope = match_scope(team_id, period, modality)
    all_rows = appearances(team_id, scope)
    rows = (
        select(all_rows)
        .where((all_rows.c.membership_id if kind == "member" else all_rows.c.guest_id) == person_id)
        .cte("person_matches")
    )
    counts = session.execute(totals_query(rows)).mappings().one()
    person.totals = Totals(
        **{
            key: int(counts[key])
            for key in ["matches", "goals", "assists", "yellow_cards", "red_cards"]
        }
    )
    home, away = aliased(FormationSquad), aliased(FormationSquad)
    history = (
        session.execute(
            select(
                scope.c.id.label("match_id"),
                scope.c.event_id,
                scope.c.date,
                scope.c.title,
                scope.c.modality,
                scope.c.home_score,
                scope.c.away_score,
                home.number.label("home_number"),
                away.number.label("away_number"),
                rows.c.goals,
                rows.c.assists,
                rows.c.yellow_cards,
                rows.c.red_cards,
            )
            .select_from(rows)
            .join(scope, scope.c.id == rows.c.match_id)
            .join(home, home.id == scope.c.home_formation_team_id)
            .join(away, away.id == scope.c.away_formation_team_id)
            .order_by(
                scope.c.date.desc(), scope.c.time.desc(), scope.c.created_at.desc(), scope.c.id
            )
            .offset(offset)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return {
        "person": person,
        "goals_per_match": person.totals.goals / person.totals.matches
        if person.totals.matches
        else 0,
        "assists_per_match": person.totals.assists / person.totals.matches
        if person.totals.matches
        else 0,
        "history": [dict(row) for row in history],
        "has_more": offset + len(history) < person.totals.matches,
    }
