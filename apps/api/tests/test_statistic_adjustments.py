from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.application.statistic_adjustments import AdjustInput, adjust
from app.application.teams import add_member
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.models import MembershipPermission
from app.infrastructure.statistic_models import StatisticAdjustment
from tests.conftest import make_player
from tests.test_join_requests import history, scenario
from tests.test_match_events import post, remove
from tests.test_team_profiles import client_for


def setup(session):
    owner, team, admin, manual, _, client = scenario(session)
    root = f"/v1/teams/{team.id}/statistics"
    person = root + f"/players/{manual['membership_id']}"
    return owner, team, admin, manual, client, root, person


def payload(admin, path, **values):
    snapshot = admin.get(path).json()
    return dict(
        command_id=snapshot["command_id"],
        expected_state=snapshot["expected_state"],
        confirm=True,
        **(snapshot["totals"] | values),
    )


def test_adjustments_historical_only_preserve_matches_and_audit(session):
    owner, team, admin, manual, _, root, person = setup(session)
    event = history(session, team, admin, manual)
    path = person + "/adjustments"
    before = admin.get(person).json()
    assert before["person"]["totals"]["goals"] == 1
    data = payload(admin, path, goals=3, yellow_cards=0, red_cards=2)
    assert admin.post(path, json=data).status_code == 200
    assert admin.post(path, json=data).status_code == 200
    profile = admin.get(person).json()
    assert profile["person"]["totals"]["goals"] == 3
    assert profile["person"]["manual_adjustments"] == dict(goals=2, yellow_cards=-1, red_cards=1)
    assert profile["history"] == before["history"]
    assert profile["goals_per_match"] == 1
    assert admin.get(person, params={"modality": "campo"}).json()["person"]["totals"]["goals"] == 1
    assert admin.get(person, params={"period": "year"}).json()["person"]["manual_adjustments"] == {}
    assert admin.get(root).json()["summary"]["goals"] == 4
    record = session.scalars(select(StatisticAdjustment)).one()
    assert record.actor_id == owner.user_id and record.membership_id == UUID(
        manual["membership_id"]
    )
    assert record.previous_totals == dict(goals=1, yellow_cards=1, red_cards=1)
    assert record.new_totals == dict(goals=3, yellow_cards=0, red_cards=2)
    assert record.created_at and record.goals_delta == 2 and record.yellow_cards_delta == -1
    match = profile["history"][0]["match_id"]
    incidents = event + f"/matches/{match}/events"
    page = admin.get(incidents).json()
    participant = next(p for p in page["participants"] if p["name"] == manual["name"])
    post(admin, incidents, page, participant["id"])
    assert admin.get(person).json()["person"]["totals"]["goals"] == 4
    history(session, team, admin, manual)
    assert admin.get(person).json()["person"]["totals"]["goals"] == 5
    assert admin.post(path, json={**data, "command_id": str(uuid4())}).status_code == 409
    assert session.scalar(select(func.count()).select_from(StatisticAdjustment)) == 1


@pytest.mark.parametrize("value", [-1, 1.5, True, "1", 1000000])
def test_invalid_totals_are_rejected(session, value):
    _, _, admin, _, _, _, person = setup(session)
    path = person + "/adjustments"
    assert admin.post(path, json=payload(admin, path, goals=value)).status_code == 422
    assert session.scalar(select(func.count()).select_from(StatisticAdjustment)) == 0


def test_permission_ids_confirmation_and_conflicting_retry(session):
    _, _, admin, _, outsider, _, person = setup(session)
    path = person + "/adjustments"
    data = payload(admin, path, goals=2)
    assert outsider.get(path).status_code == 404
    assert outsider.post(path, json=data).status_code == 404
    assert admin.post(path, json={**data, "confirm": False}).status_code == 409
    assert (
        admin.post(path.replace(person.split("/")[-1], str(uuid4())), json=data).status_code == 404
    )
    assert admin.post(path, json=data).status_code == 200
    assert admin.post(path, json={**data, "goals": 5}).status_code == 409
    assert session.scalar(select(func.count()).select_from(StatisticAdjustment)) == 1


def test_concurrent_retry_is_one_audited_adjustment(session, engine):
    owner, team, admin, manual, _, _, person = setup(session)
    data = AdjustInput(**payload(admin, person + "/adjustments", goals=7))
    user_id, team_id, member_id = owner.user_id, team.id, UUID(manual["membership_id"])
    session.commit()
    barrier = Barrier(2)

    def run():
        with Session(engine) as worker:
            barrier.wait()
            result = adjust(worker, user_id, team_id, member_id, data)
            return result["totals"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert all(r["goals"] == 7 for r in results)
    assert session.scalar(select(func.count()).select_from(StatisticAdjustment)) == 1


def test_match_removal_cannot_make_negative_totals(session):
    _, team, admin, manual, _, _, person = setup(session)
    event = history(session, team, admin, manual)
    path = person + "/adjustments"
    assert admin.post(path, json=payload(admin, path, goals=0)).status_code == 200
    match = admin.get(person).json()["history"][0]["match_id"]
    incidents = event + f"/matches/{match}/events"
    page = admin.get(incidents).json()
    participant = next(p for p in page["participants"] if p["name"] == manual["name"])
    goal = next(
        item
        for item in page["items"]
        if item["type"] == "GOAL" and item["participant_id"] == participant["id"]
    )
    remove(admin, incidents, page, goal)
    assert admin.get(person).json()["person"]["totals"]["goals"] == 0
    assert admin.get(path).json()["floor_applied"]


def test_granular_permissions_and_team_isolation(session):
    _, team, admin, manual, _, root, person = setup(session)
    member = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=member.id)
    session.commit()
    client = client_for(session, member)
    path = person + "/adjustments"
    data = payload(admin, path, goals=2)
    assert client.get(root).json()["can_manage_statistics"] is False
    assert client.post(path, json=data).status_code == 403
    team.plan = Plan.PRO
    membership.role = Role.ADMIN
    grant = MembershipPermission(membership_id=membership.id, permission=Permission.MANAGE_MEMBERS)
    session.add(grant)
    session.commit()
    assert client.post(path, json=data).status_code == 403
    grant.permission = Permission.MANAGE_EVENTS
    session.commit()
    assert client.get(root).json()["can_manage_statistics"] is True
    assert client.post(path, json=data).status_code == 200
    team.plan = Plan.FREE
    session.commit()
    assert client.post(path, json=payload(admin, path, goals=3)).status_code == 403
    _, other, other_admin, _, _, _ = scenario(session)
    assert other_admin.get(path).status_code == 404
    wrong = f"/v1/teams/{other.id}/statistics/players/{manual['membership_id']}/adjustments"
    assert other_admin.post(wrong, json=data).status_code == 404


def test_transaction_rollback_and_migration_guard(session, engine, monkeypatch):
    owner, team, admin, manual, _, _, person = setup(session)
    data = AdjustInput(**payload(admin, person + "/adjustments", goals=4))
    user_id, team_id, member_id = owner.user_id, team.id, UUID(manual["membership_id"])
    session.commit()
    with Session(engine) as worker:

        def fail():
            raise RuntimeError("commit failure")

        monkeypatch.setattr(worker, "commit", fail)
        with pytest.raises(RuntimeError, match="commit failure"):
            adjust(worker, user_id, team_id, member_id, data)
    assert session.scalar(select(func.count()).select_from(StatisticAdjustment)) == 0
    session.commit()
    assert admin.post(person + "/adjustments", json=data.model_dump(mode="json")).status_code == 200
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    session.close()
    with pytest.raises(RuntimeError, match="histórico"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0011")
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0013"
        config.attributes["connection"] = connection
        command.check(config)
