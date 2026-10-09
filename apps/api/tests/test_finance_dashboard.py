from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import finance_recurring
from app.application.teams import add_member
from app.infrastructure.finance_models import CashEntry, DuesSettings, MonthlyDues
from tests.conftest import make_player
from tests.test_finance import generate, manual, pay, payment, setup
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for


def preferences(version=0, share=False):
    return {
        "opening_balance": "100.00",
        "opening_date": "2026-01-01",
        "share_summary": share,
        "expected_version": version,
        "confirm": True,
    }


def test_dashboard_period_opening_receivable_and_reversal(session):
    _, _, client, path, _ = setup(session)
    dues = generate(client, path)
    partial = pay(client, path, dues[0], payment(dues[0], "10.00"))
    assert client.put(path + "/preferences", json=preferences()).status_code == 200
    expense = client.post(path + "/cash", json=manual("EXPENSE", "20.00")).json()
    today = date.today().replace(day=1).isoformat()
    data = client.get(path + "/dashboard", params={"month": today}).json()
    assert (data["balance"], data["income"], data["expense"], data["previous_balance"]) == (
        "90.00",
        "10.00",
        "20.00",
        "100.00",
    )
    feb = client.get(path + "/dashboard", params={"month": "2026-02-01"}).json()
    assert feb["receivable"] == "50.00" and feb["debtors"] == 2
    assert (
        client.post(
            path + f"/cash/{expense['id']}/reverse", json={"reason": "Duplicado", "confirm": True}
        ).status_code
        == 200
    )
    assert client.get(path + "/dashboard", params={"month": today}).json()["balance"] == "110.00"
    assert partial["remaining"] == "20.00"
    assert client.get(path + "/dashboard", params={"month": "2026-02-10"}).status_code == 422


def test_summary_privacy_and_permissions(session):
    _, team, admin, path, _ = setup(session)
    player = make_player(session)
    add_member(session, team_id=team.id, player_id=player.id)
    client = client_for(session, player)
    dues = generate(admin, path)
    query = {"month": "2026-02-01"}
    assert client.get(path + "/dashboard", params=query).json() == {"visible": False}
    assert admin.put(path + "/preferences", json=preferences(share=True)).status_code == 200
    shared = client.get(path + "/dashboard", params=query).json()
    assert (
        shared["visible"]
        and not {"recent", "counts", "debtors", "receivable", "preferences"} & shared.keys()
    )
    assert client.put(path + "/preferences", json=preferences(1)).status_code == 403
    assert (
        client.post(path + "/categories", json={"kind": "INCOME", "name": "Teste"}).status_code
        == 403
    )
    assert client.get(path + "/cash").status_code == 403
    other = next(
        d
        for d in dues
        if d["membership_id"] != client.get(path + "/dues").json()["items"][0]["membership_id"]
    )
    assert (
        client.put(
            path + f"/dues/{other['id']}",
            json={"amount": "5.00", "expected_version": 1, "confirm": True},
        ).status_code
        == 403
    )


def test_categories_edits_search_and_audit(session):
    _, _, client, path, _ = setup(session)
    cats = client.get(path + "/categories").json()
    assert "Mensalidade" in cats["INCOME"] and "Outras despesas" not in cats["EXPENSE"]
    for _ in range(2):
        result = client.post(path + "/categories", json={"kind": "INCOME", "name": "Doação"}).json()
        assert result["INCOME"].count("Doação") == 1
    entry = client.post(path + "/cash", json={**manual(), "description": ""}).json()
    update = {
        "category": "Doação",
        "description": "Bola nova",
        "amount": "50.00",
        "entry_date": date.today().isoformat(),
        "expected_version": 1,
        "confirm": True,
    }
    edited = client.put(path + f"/cash/{entry['id']}", json=update)
    assert edited.status_code == 200, edited.text
    assert edited.json()["audit"][-1]["changes"]["before"]["amount"] == "200.00"
    assert client.put(path + f"/cash/{entry['id']}", json=update).status_code == 409
    assert len(client.get(path + "/cash", params={"search": "Bola"}).json()["items"]) == 1
    assert not client.get(path + "/cash", params={"search": "%"}).json()["items"]
    assert (
        client.post(path + "/cash", json={**manual(), "category": "Mensalidade"}).status_code == 409
    )


def test_individual_dues_edit_preserves_others_and_partial_payment(session):
    _, _, client, path, _ = setup(session)
    dues = generate(client, path)
    partial = pay(client, path, dues[0], payment(dues[0], "10.00"))
    url = path + f"/dues/{partial['id']}"
    body = {"amount": "5.00", "expected_version": partial["version"], "confirm": True}
    assert client.put(url, json=body).status_code == 409
    paid = client.put(url, json={**body, "amount": "10.00"}).json()
    assert paid["status"] == "PAID"
    assert client.get(path + f"/dues/{dues[1]['id']}").json()["amount"] == "30.00"
    assert client.get(path).json()["settings"]["amount"] == "30.00"
    assert (
        client.put(
            path + f"/cash/{paid['payments'][0]['id']}",
            json={
                "category": "Teste",
                "description": "",
                "amount": "10.00",
                "entry_date": date.today().isoformat(),
                "expected_version": 1,
                "confirm": True,
            },
        ).status_code
        == 409
    )


def recurring_setup(session):
    owner, team, client, path, _ = setup(session)
    assert (
        client.put(
            path + "/settings",
            json={
                "amount": "30.00",
                "due_day": 31,
                "active": True,
                "repeat_monthly": True,
                "expected_version": 1,
            },
        ).status_code
        == 200
    )
    return owner, team, client, path


def test_recurring_current_members_once_and_next_month(session, monkeypatch):
    _, team, client, path = recurring_setup(session)
    inactive = add_member(session, team_id=team.id, player_id=make_player(session).id)
    inactive.status = "inactive"
    session.commit()
    assert finance_recurring.generate_current(session, team.id) == 2
    session.commit()
    assert finance_recurring.generate_current(session, team.id) == 0
    # New active members only enter the next generation.
    new = add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    assert finance_recurring.generate_current(session, team.id) == 0
    config = session.scalar(select(DuesSettings).where(DuesSettings.team_id == team.id))
    next_date = config.next_competence

    class NextMonth:
        @staticmethod
        def now(tz):
            return datetime(next_date.year, next_date.month, 1, tzinfo=tz)

    monkeypatch.setattr(finance_recurring, "datetime", NextMonth)
    assert finance_recurring.generate_current(session, team.id) == 3
    session.commit()
    assert session.scalar(select(func.count()).select_from(MonthlyDues)) == 5
    assert (
        session.scalar(
            select(func.count()).select_from(MonthlyDues).where(MonthlyDues.membership_id == new.id)
        )
        == 1
    )
    assert session.scalar(select(func.count()).select_from(CashEntry)) == 0


def test_recurring_concurrency_and_rollback(engine, session, monkeypatch):
    _, team, _, _ = recurring_setup(session)
    team_id = team.id
    session.commit()

    def fail(*args, **kwargs):
        raise RuntimeError("audit failure")

    original = finance_recurring.audit
    monkeypatch.setattr(finance_recurring, "audit", fail)
    with pytest.raises(RuntimeError), Session(engine) as worker, worker.begin():
        finance_recurring.generate_current(worker, team_id)
    assert session.scalar(select(func.count()).select_from(MonthlyDues)) == 0
    monkeypatch.setattr(finance_recurring, "audit", original)
    barrier = Barrier(2)

    def run(_):
        with Session(engine) as worker, worker.begin():
            barrier.wait()
            return finance_recurring.generate_current(worker, team_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == [0, 2]


def test_free_and_cross_team_new_writes_blocked(session):
    owner, team, client, path, _ = setup(session)
    entry = client.post(path + "/cash", json=manual()).json()
    other = make_team(session, owner)
    session.commit()
    assert client.get(f"/v1/teams/{other.id}/finance/cash/{entry['id']}").status_code == 404
    team.plan = "free"
    session.commit()
    assert client.put(path + "/preferences", json=preferences()).status_code == 403
    assert (
        client.post(path + "/categories", json={"kind": "EXPENSE", "name": "Teste"}).status_code
        == 403
    )
    assert finance_recurring.generate_current(session, team.id) == 0


def test_migration_upgrade_preserves_financial_rows(engine, session):
    _, team, client, path, _ = setup(session)
    dues = generate(client, path)
    pay(client, path, dues[0])
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    session.commit()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0017")
        tables = ["dues_settings", "monthly_dues", "cash_entries", "finance_audit"]

        def snapshot(table):
            return connection.execute(
                text(
                    "SELECT (to_jsonb(t) - ARRAY['repeat_monthly','next_competence',"
                    f"'changes','version'])::text FROM {table} t ORDER BY id"
                )
            ).all()

        before = {table: snapshot(table) for table in tables}
        command.upgrade(config, "head")
        assert all(snapshot(table) == rows for table, rows in before.items())
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0018"
        command.check(config)
