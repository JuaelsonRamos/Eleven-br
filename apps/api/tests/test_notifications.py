"""Notification integration with real PostgreSQL, authorization and concurrent commands."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.application import events, finance_writes
from app.application.notification_delivery import emit
from app.application.teams import add_member
from app.domain.events import EventDraft
from app.domain.notifications import NotificationType as Kind
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.event_models import Event
from app.infrastructure.models import MembershipPermission
from app.infrastructure.notification_models import Notification
from app.presentation.event_schemas import EventInput
from tests.conftest import make_player
from tests.test_events import DATA, setup_events
from tests.test_finance import MONTH, generate, pay, payment, setup
from tests.test_join_requests import approve, request, scenario
from tests.test_team_profiles import client_for

BASE = "/v1/me/notifications"


def rows(session, kind=None):
    query = select(Notification)
    if kind:
        query = query.where(Notification.type == kind)
    return list(session.scalars(query))


def notice(session, uid, key):
    return emit(
        session,
        users=[uid],
        team_id=None,
        kind=Kind.EVENT_CREATED,
        title="Aviso",
        message="Mensagem",
        key=key,
    )


def test_own_inbox_idor_read_count_and_read_all(session):
    owner, _, admin, _ = setup_events(session)
    other = make_player(session)
    outsider = client_for(session, other)
    for uid in [owner.user_id, other.user_id]:
        for key in ["one", "two"]:
            notice(session, uid, key)
    session.commit()
    own = admin.get(BASE).json()["items"]
    foreign = outsider.get(BASE).json()["items"][0]
    assert len(own) == 2 and foreign["id"] not in {item["id"] for item in own}
    assert admin.get(BASE + "/unread-count").json() == {"count": 2}
    assert admin.get(BASE + f"/{foreign['id']}").status_code == 404
    assert admin.post(BASE + f"/{foreign['id']}/read").status_code == 404
    assert admin.get(BASE, params={"cursor": foreign["id"]}).status_code == 404
    target = BASE + f"/{own[0]['id']}/read"
    first = admin.post(target).json()
    assert first["read_at"] and admin.post(target).json()["read_at"] == first["read_at"]
    assert admin.get(BASE + "/unread-count").json() == {"count": 1}
    assert admin.post(BASE + "/read-all").json() == {"count": 0}
    assert outsider.get(BASE + "/unread-count").json() == {"count": 2}
    assert client_for(session).get(BASE).status_code == 401


def test_keyset_pagination_ties_and_limits(session):
    owner, _, client, _ = setup_events(session)
    for index in range(7):
        notice(session, owner.user_id, str(index))
    session.commit()
    first = client.get(BASE, params={"limit": 3}).json()
    second = client.get(BASE, params={"limit": 3, "cursor": first["next_cursor"]}).json()
    last = client.get(BASE, params={"limit": 3, "cursor": second["next_cursor"]}).json()
    items = first["items"] + second["items"] + last["items"]
    assert len({item["id"] for item in items}) == 7 and last["next_cursor"] is None
    keys = [(item["created_at"], item["id"]) for item in items]
    assert keys == sorted(keys, reverse=True)
    assert client.get(BASE, params={"limit": 51}).status_code == 422
    assert client.get(BASE, params={"limit": 0}).status_code == 422


@pytest.mark.parametrize("plan", [Plan.FREE, Plan.PRO])
def test_join_request_notifies_only_current_authorized_managers(session, plan):
    owner, team, admin, _, _, client = scenario(session, Plan.PRO)
    manager = make_player(session)
    member = add_member(session, team_id=team.id, player_id=manager.id, role=Role.ADMIN)
    session.add(MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_MEMBERS))
    ordinary = make_player(session)
    add_member(session, team_id=team.id, player_id=ordinary.id)
    team.plan = plan
    session.commit()
    item = request(client, team)
    expected = {owner.user_id, manager.user_id} if plan == Plan.PRO else {owner.user_id}
    assert {row.user_id for row in rows(session, Kind.TEAM_JOIN_REQUEST)} == expected
    assert (
        client.post(f"/v1/teams/{team.id}/join-requests", json={"code": team.code}).status_code
        == 409
    )
    assert len(rows(session)) == len(expected)
    approve(admin, team, item)
    own = client.get(BASE).json()["items"]
    assert len(own) == 1 and own[0]["type"] == Kind.TEAM_JOIN_APPROVED
    assert own[0]["action"] == "OPEN_TEAM" and own[0]["available"]
    approve(admin, team, item, status=409)
    assert len(rows(session, Kind.TEAM_JOIN_APPROVED)) == 1


def test_rejection_remains_readable_without_membership(session):
    _, team, admin, _, _, client = scenario(session)
    item = request(client, team)
    assert (
        admin.post(
            f"/v1/teams/{team.id}/join-requests/{item['id']}/reject", json={"confirm": True}
        ).status_code
        == 200
    )
    notice = client.get(BASE).json()["items"][0]
    assert notice["type"] == Kind.TEAM_JOIN_REJECTED and notice["available"]
    assert "não foi aprovada" in notice["message"] and notice["action"] is None


def test_event_recipients_exclude_author_inactive_manual_and_guest(session):
    owner, team, client, path = setup_events(session)
    active = make_player(session)
    add_member(session, team_id=team.id, player_id=active.id)
    inactive = add_member(session, team_id=team.id, player_id=make_player(session).id)
    inactive.status = "inactive"
    session.commit()
    assert (
        client.post(f"/v1/teams/{team.id}/players", json={"name": "Sem conta"}).status_code == 201
    )
    item = client.post(path, json=DATA).json()
    assert (
        client.post(path + f"/{item['id']}/guests", json={"name": "Convidado"}).status_code == 201
    )
    assert [(n.user_id, n.type) for n in rows(session)] == [(active.user_id, Kind.EVENT_CREATED)]
    assert rows(session)[0].user_id != owner.user_id


@pytest.mark.parametrize(
    "change,relevant",
    [
        ("date", True),
        ("time", True),
        ("location", True),
        ("modality", True),
        ("title", False),
        ("notes", False),
    ],
)
def test_only_relevant_event_edits_notify_and_retry_is_quiet(session, change, relevant):
    _, team, client, path = setup_events(session)
    team.modalities = ["campo", "society"]
    add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    item = client.post(path, json=DATA).json()
    values = {
        "date": "2026-10-04",
        "time": "09:00",
        "location": "Outra arena",
        "modality": "society",
        "title": "Novo nome",
        "notes": "Observação",
    }
    payload = {**DATA, change: values[change]}
    for _ in range(2):
        assert client.put(path + f"/{item['id']}", json=payload).status_code == 200
    assert len(rows(session, Kind.EVENT_UPDATED)) == int(relevant)


@pytest.mark.parametrize("series", [False, True])
def test_cancellation_and_series_have_one_notice_per_recipient(session, series):
    _, team, client, path = setup_events(session)
    add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    item = client.post(path, json={**DATA, "recurring_weekly": series}).json()
    assert len(rows(session, Kind.EVENT_CREATED)) == 1
    for _ in range(3):
        client.get(path)  # automatic occurrence materialization must never emit
    assert len(rows(session)) == 1
    suffix = "/cancel-series" if series else "/cancel"
    for _ in range(2):
        assert client.post(path + f"/{item['id']}" + suffix).status_code == 200
    assert len(rows(session, Kind.EVENT_CANCELLED)) == 1


def test_reminders_only_pending_idempotent_permissions_and_team_idor(session):
    _, team, client, path = setup_events(session)
    players = [make_player(session) for _ in range(3)]
    for player in players:
        add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    item = client.post(path, json=DATA).json()
    detail = path + f"/{item['id']}"
    for player, answer in zip(players, ["VOU", "NAO_VOU"], strict=False):
        assert (
            client_for(session, player)
            .put(detail + "/attendance", json={"response": answer})
            .status_code
            == 200
        )
    assert client.put(detail + "/attendance", json={"response": "VOU"}).status_code == 200
    url = detail + "/attendance-reminders"
    assert client_for(session, players[2]).post(url).status_code == 403
    _, _, other_client, other_path = setup_events(session)
    assert other_client.post(url).status_code == 404
    assert client.post(other_path + f"/{item['id']}/attendance-reminders").status_code == 404
    assert client.post(url).json() == {"count": 1}
    assert client.post(url).json() == {"count": 0}
    assert [n.user_id for n in rows(session, Kind.ATTENDANCE_REMINDER)] == [players[2].user_id]
    client.post(detail + "/cancel")
    assert client.post(url).status_code == 409


def test_finance_preview_generation_partial_paid_retry_and_reversal(session):
    owner, _, client, path, _ = setup(session)
    assert client.post(path + "/dues/preview", json={"competence": MONTH}).status_code == 200
    assert not rows(session)
    dues = next(item for item in generate(client, path) if item["name"] == "Jogador de teste")
    assert len(rows(session)) == 1 and rows(session)[0].user_id == owner.user_id
    generate(client, path)
    assert len(rows(session)) == 1
    payload = payment(dues, "15.00")
    partial = pay(client, path, dues, payload)
    pay(client, path, dues, payload)
    assert partial["remaining"] == "15.00" and partial["status"] == "PENDING"
    notices = rows(session, Kind.FINANCE_PAYMENT_REGISTERED)
    assert len(notices) == 1 and "Saldo restante: R$ 15,00" in notices[0].message
    paid = pay(client, path, partial, payment(partial, "15.00"))
    assert paid["status"] == "PAID"
    assert any(n.title == "Mensalidade paga" and "quitada" in n.message for n in rows(session))
    entry = paid["payments"][0]
    assert (
        client.post(
            path + f"/cash/{entry['id']}/reverse",
            json={"confirm": True, "reason": "Correção", "expected_dues_version": paid["version"]},
        ).status_code
        == 200
    )
    assert len(rows(session, Kind.FINANCE_PAYMENT_REVERSED)) == 1
    assert len(rows(session, Kind.FINANCE_PAYMENT_REGISTERED)) == 2
    assert "R$ 15,00" in rows(session, Kind.FINANCE_PAYMENT_REVERSED)[0].message


def test_revoked_team_or_manager_access_redacts_destination(session):
    _, team, client, path = setup_events(session, Plan.PRO)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    client.post(path, json=DATA)
    own = client_for(session, player)
    notification = own.get(BASE).json()["items"][0]
    member.status = "inactive"
    session.commit()
    result = own.post(BASE + f"/{notification['id']}/read").json()
    assert not result["available"] and result["read_at"]
    assert result["team_id"] is None and result["entity_id"] is None
    assert result["action"] is None and DATA["title"] not in result["message"]


def test_revoked_manager_grant_hides_administrative_notice(session):
    _, team, _, _, _, applicant = scenario(session, Plan.PRO)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id, role=Role.ADMIN)
    grant = MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_MEMBERS)
    session.add(grant)
    manager = client_for(session, player)
    request(applicant, team)
    item = manager.get(BASE).json()["items"][0]
    assert item["available"] and item["action"] == "OPEN_JOIN_REQUESTS"
    session.delete(grant)
    session.commit()
    item = manager.get(BASE + f"/{item['id']}").json()
    assert not item["available"] and item["team_name"] is None and item["action"] is None


def test_finance_batch_notifies_each_account_only_about_own_charge(session):
    _, team, admin, path, _ = setup(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    member_id = str(member.id)
    client = client_for(session, player)
    dues = generate(admin, path)
    own = next(item for item in dues if item["membership_id"] == member_id)
    inbox = client.get(BASE).json()["items"]
    assert len(inbox) == 1 and inbox[0]["entity_id"] == own["id"]
    assert len(rows(session, Kind.FINANCE_CHARGE_CREATED)) == 2
    other = next(item for item in dues if item["membership_id"] != member_id)
    assert client.get(path + f"/dues/{other['id']}").status_code == 404


@pytest.mark.parametrize("operation", ["delivery", "event"])
def test_concurrent_retries_create_one_notification(engine, session, operation):
    owner, team, _, _ = setup_events(session)
    recipient = make_player(session)
    add_member(session, team_id=team.id, player_id=recipient.id)
    session.commit()
    uid, author, team_id, key = recipient.user_id, owner.user_id, team.id, uuid4()
    session.commit()
    barrier = Barrier(2)

    def worker():
        with Session(engine) as transaction:
            barrier.wait(timeout=10)
            if operation == "delivery":
                count = notice(transaction, uid, "shared")
                transaction.commit()
                return count
            event = events.create_event(
                transaction,
                user_id=author,
                team_id=team_id,
                draft=EventDraft(**EventInput.model_validate(DATA).model_dump()),
                creation_key=key,
            )
            return event.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert len(rows(session)) == 1
    if operation == "delivery":
        assert sorted(results) == [0, 1]
    else:
        assert results[0] == results[1]
        assert session.scalar(select(func.count()).select_from(Event)) == 1


def test_event_http_creation_retry_and_mismatched_payload(session):
    _, team, client, path = setup_events(session)
    add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    key = client.get(path).json()["creation_key"]
    payload = {**DATA, "creation_key": key}
    first = client.post(path, json=payload)
    assert first.status_code == 201
    assert client.post(path, json=payload).json()["id"] == first.json()["id"]
    assert client.post(path, json={**payload, "title": "Diferente"}).status_code == 409
    assert len(rows(session)) == 1


def test_financial_rollback_removes_inserted_notice_and_business_write(session, monkeypatch):
    _, _, client, path, _ = setup(session)
    dues = next(item for item in generate(client, path) if item["name"] == "Jogador de teste")

    def fail(*args, **kwargs):
        raise RuntimeError("forced audit failure after notification")

    monkeypatch.setattr(finance_writes, "audit", fail)
    with pytest.raises(RuntimeError, match="forced audit"):
        pay(client, path, dues)
    session.expire_all()
    assert not rows(session, Kind.FINANCE_PAYMENT_REGISTERED)
    assert client.get(path + f"/dues/{dues['id']}").json()["received"] == "0.00"


def test_notification_failure_rolls_back_event(engine, session, monkeypatch):
    owner, team, _, _ = setup_events(session)
    uid, tid = owner.user_id, team.id
    session.commit()

    def fail(*args, **kwargs):
        raise RuntimeError("forced notification failure")

    monkeypatch.setattr(events, "event_notice", fail)
    with pytest.raises(RuntimeError), Session(engine) as transaction:
        events.create_event(
            transaction,
            user_id=uid,
            team_id=tid,
            draft=EventDraft(**EventInput.model_validate(DATA).model_dump()),
        )
    assert session.scalar(select(func.count()).select_from(Event)) == 0
    assert not rows(session)


def test_incremental_migration_preserves_rows_and_guards_history(engine, session):
    owner, _, _, path = setup_events(session)
    uid = owner.user_id
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010")
        before = connection.execute(text("SELECT to_jsonb(t) FROM users t")).all()
        command.upgrade(config, "head")
        assert connection.execute(text("SELECT to_jsonb(t) FROM users t")).all() == before
        command.check(config)
    notice(session, uid, "persisted")
    session.commit()
    with pytest.raises(RuntimeError, match="histórico"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0017"
