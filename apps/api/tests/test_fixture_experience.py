"""Callups and bilateral changes use the existing isolated PostgreSQL fixture."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.application import callups, fixture_changes
from app.application.teams import add_member
from app.domain.policies import Plan
from app.infrastructure.event_models import Event, EventGuest
from app.infrastructure.launch_models import TeamAudit
from app.infrastructure.models import TeamMembership
from app.infrastructure.notification_models import Notification
from app.infrastructure.opponent_models import FixtureProposal, TeamFixture
from tests.conftest import make_player
from tests.test_opponents import (  # noqa: F401
    accepted_fixture,
    clock,
    club,
    concurrently,
    count,
    member_client,
)
from tests.test_team_profiles import client_for


def event_path(client, team, path):
    return f"/v1/teams/{team.id}/events/{client.get(path).json()['event_id']}"


def test_callup_presence_reminders_and_guests(session):
    fid, (team, admin, path, _), (other, opponent, opath, _) = accepted_fixture(session)
    players = [make_player(session) for _ in range(3)]
    for player in players:
        add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    mids = [
        str(
            session.scalar(
                select(TeamMembership.id).where(
                    TeamMembership.team_id == team.id, TeamMembership.player_id == p.id
                )
            )
        )
        for p in players
    ]
    clients = [client_for(session, p) for p in players]
    ep = event_path(admin, team, path)
    original = admin.get(ep).json()
    assert original["pending"] == 0 and original["participants"] == []
    assert not clients[0].get(ep).json()["can_respond"]
    assert clients[0].put(ep + "/attendance", json={"response": "VOU"}).status_code == 409
    selection = {"membership_ids": mids[:2], "expected_version": 1}
    assert clients[0].put(ep + "/callup", json=selection).status_code == 403
    selected = admin.put(ep + "/callup", json=selection)
    assert selected.status_code == 200, selected.text
    assert selected.json()["pending"] == 2
    assert admin.put(ep + "/callup", json=selection).status_code == 200
    assert count(session, Notification, Notification.type == "FIXTURE_CALLED_UP") == 2
    assert clients[0].put(ep + "/attendance", json={"response": "VOU"}).status_code == 200
    assert admin.post(ep + "/attendance-reminders").json()["count"] == 1
    assert admin.post(ep + "/attendance-reminders").json()["count"] == 0
    assert clients[1].put(ep + "/attendance", json={"response": "NAO_VOU"}).status_code == 200
    assert admin.post(ep + "/attendance-reminders").json()["count"] == 0
    removed = admin.put(
        ep + "/callup", json={"membership_ids": [mids[1]], "expected_version": 2}
    ).json()
    assert removed["going"] == 0 and removed["not_going"] == 1
    later = admin.put(ep + "/callup", json={"membership_ids": mids, "expected_version": 3}).json()
    assert later["pending"] == 2 and later["not_going"] == 1
    assert count(session, TeamAudit, TeamAudit.action == "CALLUP_CHANGED") == 3
    body = {"name": "Convidado", "response": "PENDENTE", "command_id": str(uuid4())}
    membership_count = count(session, TeamMembership)
    for _ in range(2):
        response = admin.post(ep + "/guests", json=body)
        assert response.status_code == 201, response.text
    guest = response.json()["guests"][0]
    assert count(session, EventGuest) == 1 and count(session, TeamMembership) == membership_count
    assert (
        admin.put(ep + f"/guests/{guest['id']}/attendance", json={"response": "VOU"}).json()[
            "guests"
        ][0]["response"]
        == "VOU"
    )
    other_ep = event_path(opponent, other, opath)
    assert (
        opponent.put(
            other_ep + f"/guests/{guest['id']}/attendance", json={"response": "VOU"}
        ).status_code
        == 404
    )
    assert opponent.get(ep).status_code == 404
    assert admin.post(ep + f"/guests/{guest['id']}/remove").json()["guests"] == []
    assert session.get(EventGuest, UUID(guest["id"])).removed_at is not None


@pytest.mark.parametrize(
    "kind,decision",
    [
        ("CHANGE", "ACCEPTED"),
        ("CHANGE", "REJECTED"),
        ("CANCEL", "ACCEPTED"),
        ("CANCEL", "REJECTED"),
        ("WITHDRAW", "ACCEPTED"),
    ],
)
def test_bilateral_history_and_terminal_rules(session, kind, decision):
    fid, (team, admin, path, _), (other, opponent, opath, _) = accepted_fixture(session)
    ep = event_path(admin, team, path)
    before = admin.get(path).json()
    body = {
        "command_id": str(uuid4()),
        "expected_version": 1,
        "kind": kind,
        "reason": "Agenda",
        "confirm": True,
    }
    if kind == "CHANGE":
        body.update(date="2026-10-11", time="17:00", location="Arena Nova")
    sent = admin.post(path + "/proposals", json=body)
    assert sent.status_code == 200, sent.text
    assert admin.post(path + "/proposals", json=body).status_code == 200
    proposal = sent.json()["proposals"][0]
    if kind != "WITHDRAW":
        assert sent.json()["date"] == before["date"] and sent.json()["status"] == "SCHEDULED"
        assert (
            admin.post(
                path + f"/proposals/{proposal['id']}/decision", json={"decision": decision}
            ).status_code
            == 409
        )
        conflict = {**body, "command_id": str(uuid4()), "expected_version": 2}
        assert opponent.post(opath + "/proposals", json=conflict).status_code == 409
        url = opath + f"/proposals/{proposal['id']}/decision"
        for _ in range(2):
            result = opponent.post(url, json={"decision": decision})
            assert result.status_code == 200, result.text
    current = admin.get(path).json()
    assert count(session, FixtureProposal) == 1 and count(session, TeamFixture) == 1
    assert count(session, Event) == 2
    if kind == "CHANGE" and decision == "ACCEPTED":
        assert current["date"] == "2026-10-11"
        assert all(e.location == "Arena Nova" for e in session.scalars(select(Event)))
    elif kind in ("CANCEL", "WITHDRAW") and decision == "ACCEPTED":
        assert current["status"] == ("CANCELLED" if kind == "CANCEL" else "WITHDRAWN")
        assert all(e.status == "cancelled" for e in session.scalars(select(Event)))
        assert not current["can_report"] and not current["can_review"]
        assert (
            admin.post(path + "/score", json={"home_score": 1, "away_score": 0}).status_code == 409
        )
        assert (
            admin.put(
                ep + "/callup", json={"membership_ids": [], "expected_version": 1}
            ).status_code
            == 409
        )
    else:
        assert current["date"] == before["date"] and current["status"] == "SCHEDULED"
    assert (
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "FIXTURE_CHANGED")
        )
        == 2
    )


def test_large_roster_selection_security_and_inactive_reminders(session):
    _, (team, admin, path, _), (away, _, _, _) = accepted_fixture(session)
    team.plan = Plan.PRO
    for _ in range(32):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    ep = event_path(admin, team, path)
    data = admin.get(ep).json()
    assert len(data["callup_candidates"]) == 33 and data["pending"] == 0
    foreign = str(away.president_membership_id)
    assert (
        admin.put(
            ep + "/callup", json={"membership_ids": [foreign], "expected_version": 1}
        ).status_code
        == 409
    )
    member = session.scalars(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id, TeamMembership.id != team.president_membership_id
        )
    ).first()
    assert member
    admin.put(ep + "/callup", json={"membership_ids": [str(member.id)], "expected_version": 1})
    member.status = "inactive"
    session.commit()
    assert admin.get(ep).json()["pending"] == 0
    assert admin.post(ep + "/attendance-reminders").json()["count"] == 0
    assert (
        admin.put(
            ep + "/callup", json={"membership_ids": [str(member.id)], "expected_version": 2}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("kind", ["CHANGE", "CANCEL", "WITHDRAW"])
def test_notices_only_managers_and_called_users(session, kind):
    _, (team, admin, path, _), (away, other, opath, _) = accepted_fixture(session)
    member = make_player(session)
    add_member(session, team_id=team.id, player_id=member.id)
    not_called = make_player(session)
    add_member(session, team_id=team.id, player_id=not_called.id)
    session.commit()
    mid = session.scalar(select(TeamMembership.id).where(TeamMembership.player_id == member.id))
    ep = event_path(admin, team, path)
    admin.put(ep + "/callup", json={"membership_ids": [str(mid)], "expected_version": 1})
    body = {"kind": kind, "command_id": str(uuid4()), "expected_version": 1, "confirm": True}
    if kind == "CHANGE":
        body.update(date="2026-10-12", time="18:00", location="Arena")
    result = admin.post(path + "/proposals", json=body)
    assert result.status_code == 200
    if kind != "WITHDRAW":
        pid = result.json()["proposals"][0]["id"]
        assert not count(
            session,
            Notification,
            Notification.user_id == member.user_id,
            Notification.type == "FIXTURE_PROPOSAL",
        )
        other.post(opath + f"/proposals/{pid}/decision", json={"decision": "ACCEPTED"})
        other.post(opath + f"/proposals/{pid}/decision", json={"decision": "ACCEPTED"})
    assert (
        count(
            session,
            Notification,
            Notification.user_id == member.user_id,
            Notification.type == "FIXTURE_CHANGED",
        )
        == 1
    )
    assert not count(session, Notification, Notification.user_id == not_called.user_id)


def test_proposal_permissions_conflicting_concurrency_and_rollback(engine, session, monkeypatch):
    fid, (team, admin, path, president), (away, other, opath, _) = accepted_fixture(session)
    member = member_client(session, team)
    outsider, stranger, _ = club(session, "Outro")
    body = {"kind": "CANCEL", "command_id": str(uuid4()), "expected_version": 1}
    assert member.post(path + "/proposals", json=body).status_code == 403
    assert stranger.post(path + "/proposals", json=body).status_code == 404

    def submit(own):
        return fixture_changes.create(
            own,
            president.user_id,
            team.id,
            UUID(fid),
            fixture_changes.ProposalInput.model_validate(body),
        )

    session.rollback()
    results = concurrently(engine, [submit] * 3)
    assert all(isinstance(r, dict) for r in results)
    assert count(session, FixtureProposal) == 1
    pid = admin.get(path).json()["proposals"][0]["id"]
    assert (
        stranger.post(
            opath + f"/proposals/{pid}/decision", json={"decision": "ACCEPTED"}
        ).status_code
        == 404
    )
    other.post(opath + f"/proposals/{pid}/decision", json={"decision": "REJECTED"})
    body.update(command_id=str(uuid4()), expected_version=3)

    def failure(*args, **kwargs):
        raise RuntimeError("rollback")

    session.rollback()
    with monkeypatch.context() as patch:
        patch.setattr(fixture_changes, "notify", failure)
        from sqlalchemy.orm import Session

        with Session(engine) as own, pytest.raises(RuntimeError):
            submit(own)
    assert count(session, FixtureProposal) == 1
    assert session.get(TeamFixture, UUID(fid)).version == 3


def test_concurrent_callups_and_guest_retry(engine, session):
    _, (team, admin, path, president), _ = accepted_fixture(session)
    event_id = UUID(admin.get(path).json()["event_id"])
    member_id = team.president_membership_id
    session.rollback()
    results = concurrently(
        engine,
        [
            lambda own: callups.save(
                own,
                president.user_id,
                team.id,
                event_id,
                callups.CallupInput(membership_ids=[member_id], expected_version=1),
            )
        ]
        * 3,
    )
    assert results == [None] * 3
    assert count(session, TeamAudit, TeamAudit.action == "CALLUP_CHANGED") == 1
    assert count(session, Notification, Notification.type == "FIXTURE_CALLED_UP") == 1


def test_migration_preserves_existing_fixture_response_and_schema(engine, session):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    fid, (team, admin, path, _), _ = accepted_fixture(session)
    eid = admin.get(path).json()["event_id"]
    tid, mid = team.id, team.president_membership_id
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0016")
        connection.execute(
            text(
                "INSERT INTO event_attendance (id,team_id,event_id,membership_id,response) "
                "VALUES (:id,:tid,:eid,:mid,'VOU')"
            ),
            {"id": uuid4(), "tid": tid, "eid": UUID(eid), "mid": mid},
        )
        before = connection.execute(
            text(
                "SELECT id, team_id, event_id, membership_id, response, created_at, updated_at "
                "FROM event_attendance"
            )
        ).all()
        fixture_before = connection.execute(
            text("SELECT id, date, time, location FROM team_fixtures")
        ).all()
        command.upgrade(config, "head")
        assert (
            connection.execute(
                text(
                    "SELECT id, team_id, event_id, membership_id, response, created_at, updated_at "
                    "FROM event_attendance"
                )
            ).all()
            == before
        )
        assert (
            connection.execute(text("SELECT id, date, time, location FROM team_fixtures")).all()
            == fixture_before
        )
        assert connection.scalar(text("SELECT called_up FROM event_attendance")) is True
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0017"
        command.check(config)
    with pytest.raises(RuntimeError, match="histórico"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0016")
