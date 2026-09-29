from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import finance_writes
from app.application.finance_commands import GenerateInput, PaymentInput
from app.application.teams import add_member
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.finance_models import CashEntry, MonthlyDues
from tests.conftest import make_player
from tests.migration_snapshot import LEGACY_JSON
from tests.test_foundation import make_team
from tests.test_roster import setup_roster
from tests.test_team_profiles import client_for

MONTH = "2026-02-01"


def setup(session, plan=Plan.FREE):
    owner, team, client, roster = setup_roster(session, plan)
    manual = client.post(roster, json={"name": "João do elenco"}).json()
    path = f"/v1/teams/{team.id}/finance"
    response = client.put(
        path + "/settings",
        json={"amount": "30.00", "due_day": 31, "active": True, "expected_version": 0},
    )
    assert response.status_code == 200, response.text
    return owner, team, client, path, manual


def generate(client, path, month=MONTH):
    preview = client.post(path + "/dues/preview", json={"competence": month})
    assert preview.status_code == 200, preview.text
    result = client.post(
        path + "/dues/generate",
        json={
            "competence": month,
            "preview_token": preview.json()["preview_token"],
            "confirm": True,
        },
    )
    assert result.status_code == 200, result.text
    return client.get(path + "/dues", params={"competence": month}).json()["items"]


def payment(dues, amount="30.00", method="PIX"):
    return {
        "command_id": str(uuid4()),
        "amount": amount,
        "entry_date": date.today().isoformat(),
        "payment_method": method,
        "expected_version": dues["version"],
        "confirm": True,
    }


def pay(client, path, dues, data=None, expected=200):
    response = client.post(path + f"/dues/{dues['id']}/payments", json=data or payment(dues))
    assert response.status_code == expected, response.text
    return response.json()


def manual(kind="INCOME", amount="200.00"):
    return {
        "command_id": str(uuid4()),
        "kind": kind,
        "amount": amount,
        "category": "Patrocínio" if kind == "INCOME" else "Campo",
        "description": "Receita manual" if kind == "INCOME" else "Aluguel do campo",
        "entry_date": date.today().isoformat(),
        "confirm": True,
    }


def test_generation_snapshots_active_members_idempotency_and_preview(session):
    _, team, client, path, _ = setup(session)
    inactive = add_member(session, team_id=team.id, player_id=make_player(session).id)
    inactive.status = "inactive"
    session.commit()
    preview = client.post(path + "/dues/preview", json={"competence": MONTH}).json()
    assert (preview["count"], preview["total"], preview["due_date"]) == (2, "60.00", "2026-02-28")
    assert (
        client.post(
            path + "/dues/generate",
            json={"competence": MONTH, "preview_token": preview["preview_token"]},
        ).status_code
        == 409
    )
    dues = generate(client, path)
    assert len(dues) == 2 and all(d["overdue"] for d in dues)
    assert len(generate(client, path)) == 2
    assert client.post(path + "/dues/preview", json={"competence": MONTH}).json()["count"] == 0
    assert (
        client.put(
            path + "/settings",
            json={"amount": "45.00", "due_day": 10, "active": False, "expected_version": 1},
        ).status_code
        == 200
    )
    assert client.post(path + "/dues/preview", json={"competence": "2026-03-01"}).status_code == 409
    assert client.get(path + "/dues").json()["items"][0]["amount"] == "30.00"
    assert (
        client.put(
            path + "/settings",
            json={"amount": "50.00", "due_day": 10, "active": True, "expected_version": 1},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("method", ["PIX", "CASH", "CARD", "OTHER"])
def test_partial_payment_exact_receipts_settlement_and_replay(session, method):
    _, _, client, path, _ = setup(session)
    dues = generate(client, path)[0]
    data = payment(dues, "10.01", method)
    partial = pay(client, path, dues, data)
    assert (partial["status"], partial["received"], partial["remaining"]) == (
        "PENDING",
        "10.01",
        "19.99",
    )
    assert len(pay(client, path, dues, data)["payments"]) == 1
    pay(client, path, partial, {**data, "amount": "10.02"}, 409)
    pay(client, path, partial, payment(partial, "20.00"), 409)
    paid = pay(client, path, partial, payment(partial, "19.99", method))
    assert paid["status"] == "PAID" and paid["remaining"] == "0.00"
    assert len(paid["payments"]) == 2
    pay(client, path, paid, payment(paid, "0.01"), 409)
    assert client.get(path + "/cash").json()["totals"] == {
        "income": "30.00",
        "expense": "0.00",
        "balance": "30.00",
    }


def test_reversal_reopens_paid_dues_and_preserves_history(session):
    _, _, client, path, _ = setup(session)
    dues = pay(client, path, generate(client, path)[0])
    entry = dues["payments"][0]
    reverse = path + f"/cash/{entry['id']}/reverse"
    payload = {
        "reason": "Pagamento informado por engano",
        "confirm": True,
        "expected_dues_version": dues["version"],
    }
    assert client.post(reverse, json={**payload, "expected_dues_version": 1}).status_code == 409
    assert client.post(reverse, json=payload).status_code == 200
    assert client.post(reverse, json=payload).status_code == 409
    reopened = client.get(path + f"/dues/{dues['id']}").json()
    assert (reopened["status"], reopened["remaining"], reopened["received"]) == (
        "PENDING",
        "30.00",
        "0.00",
    )
    assert reopened["payments"][0]["cancelled_at"]
    assert reopened["audit"][-1]["action"] == "REVERSAL"
    assert client.get(path).json()["totals"]["balance"] == "0.00"
    repaid = pay(client, path, reopened)
    assert len(repaid["payments"]) == 2 and repaid["status"] == "PAID"


def test_exemption_undo_cancel_and_partial_guard(session):
    _, _, client, path, _ = setup(session)
    dues = generate(client, path)[0]
    url = path + f"/dues/{dues['id']}/actions"
    exempt = client.post(
        url,
        json={
            "action": "exempt",
            "expected_version": 1,
            "confirm": True,
            "reason": "Apoio ao time",
        },
    ).json()
    assert exempt["status"] == "EXEMPT" and not exempt["overdue"]
    assert client.get(path).json()["totals"]["income"] == "0.00"
    pay(client, path, exempt, expected=409)
    reopened = client.post(
        url, json={"action": "undo_exemption", "expected_version": 2, "confirm": True}
    ).json()
    partial = pay(client, path, reopened, payment(reopened, "10.00"))
    for action in ["exempt", "cancel"]:
        assert (
            client.post(
                url,
                json={
                    "action": action,
                    "expected_version": partial["version"],
                    "confirm": True,
                    "reason": "Teste",
                },
            ).status_code
            == 409
        )
    entry = partial["payments"][0]
    assert (
        client.post(
            path + f"/cash/{entry['id']}/reverse",
            json={
                "reason": "Correção",
                "confirm": True,
                "expected_dues_version": partial["version"],
            },
        ).status_code
        == 200
    )
    current = client.get(path + f"/dues/{dues['id']}").json()
    cancelled = client.post(
        url,
        json={
            "action": "cancel",
            "expected_version": current["version"],
            "confirm": True,
            "reason": "Cobrança indevida",
        },
    ).json()
    assert cancelled["status"] == "CANCELLED"
    assert len(generate(client, path)) == 2


def test_cash_manual_balance_filters_cancellation_and_replay(session):
    _, _, client, path, _ = setup(session)
    income = manual()
    first = client.post(path + "/cash", json=income).json()
    assert client.post(path + "/cash", json=income).json()["id"] == first["id"]
    assert client.post(path + "/cash", json={**income, "amount": "201.00"}).status_code == 409
    expense = client.post(path + "/cash", json=manual("EXPENSE", "250.00")).json()
    page = client.get(path + "/cash").json()
    assert page["totals"] == {"income": "200.00", "expense": "250.00", "balance": "-50.00"}
    assert (
        len(
            client.get(
                path + "/cash",
                params={
                    "kind": "EXPENSE",
                    "category": "Campo",
                    "start": date.today().isoformat(),
                    "end": date.today().isoformat(),
                },
            ).json()["items"]
        )
        == 1
    )
    assert (
        client.post(
            path + f"/cash/{expense['id']}/reverse",
            json={"reason": "Duplicado externamente", "confirm": True},
        ).status_code
        == 200
    )
    assert client.get(path).json()["totals"]["balance"] == "200.00"
    assert len(client.get(path + "/cash").json()["items"]) == 2


def test_player_scope_no_cash_and_cross_team_ids(session):
    _, team, admin, path, _ = setup(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    client = client_for(session, player)
    dues = generate(admin, path)
    own = next(d for d in dues if d["membership_id"] == str(member.id))
    other = next(d for d in dues if d != own)
    assert client.get(path).json() == {"can_manage": False, "currency": "BRL"}
    assert client.get(path + "/dues").json()["items"] == [own]
    assert client.get(path + f"/dues/{other['id']}").status_code == 404
    assert client.get(path + f"/dues/{own['id']}").status_code == 200
    assert client.get(path + "/cash").status_code == 403
    pay(client, path, own, expected=403)
    assert client.post(path + "/cash", json=manual()).status_code == 403
    assert (
        client.post(
            path + f"/dues/{own['id']}/actions",
            json={"action": "exempt", "expected_version": 1, "confirm": True},
        ).status_code
        == 403
    )
    foreign = make_team(session, make_player(session))
    session.commit()
    foreign_path = f"/v1/teams/{foreign.id}/finance"
    for suffix in ["", "/dues", "/cash", f"/dues/{own['id']}"]:
        assert admin.get(foreign_path + suffix).status_code == 404
    assert admin.post(foreign_path + "/cash", json=manual("EXPENSE")).status_code == 404
    pay(admin, foreign_path, own, expected=404)
    pay(admin, path, {**own, "id": str(uuid4())}, expected=404)
    assert (
        admin.post(
            path + f"/dues/{own['id']}/payments",
            json={**payment(own), "membership_id": str(uuid4())},
        ).status_code
        == 422
    )


def test_finance_permission_is_granular_and_free_president_only(session):
    _, team, admin, path, _ = setup(session, Plan.PRO)
    player = make_player(session)
    add_member(
        session,
        team_id=team.id,
        player_id=player.id,
        role=Role.ADMIN,
        permissions=frozenset({Permission.MANAGE_FINANCE}),
    )
    client = client_for(session, player)
    assert client.get(path).json()["can_manage"]
    assert client.post(path + "/cash", json=manual()).status_code == 200
    team.plan = "free"
    session.commit()
    assert not client.get(path).json()["can_manage"]
    assert client.get(path + "/cash").status_code == 403
    assert admin.get(path + "/cash").status_code == 200


def test_ids_from_another_authorized_team_are_rejected(session):
    owner, team, client, path, _ = setup(session, Plan.PRO)
    dues = generate(client, path)[0]
    second = make_team(session, owner)
    session.commit()
    second_path = f"/v1/teams/{second.id}/finance"
    assert client.get(second_path).status_code == 200
    assert client.get(second_path + f"/dues/{dues['id']}").status_code == 404
    pay(client, second_path, dues, expected=404)
    paid = pay(client, path, dues)
    assert (
        client.post(
            second_path + f"/cash/{paid['payments'][0]['id']}/reverse",
            json={
                "reason": "ID manipulado",
                "confirm": True,
                "expected_dues_version": paid["version"],
            },
        ).status_code
        == 404
    )
    manager = make_player(session)
    add_member(
        session,
        team_id=team.id,
        player_id=manager.id,
        role=Role.ADMIN,
        permissions=frozenset({Permission.MANAGE_MEMBERS, Permission.MANAGE_EVENTS}),
    )
    other_client = client_for(session, manager)
    assert other_client.get(path + "/cash").status_code == 403
    assert other_client.get(path + f"/dues/{dues['id']}").status_code == 404
    assert client.get(path).json()["totals"]["income"] == "30.00"


@pytest.mark.parametrize(
    "amount", ["0", "-1", "0.001", "NaN", "Infinity", 30.5, True, "100000000.00"]
)
def test_money_validation(session, amount):
    _, _, client, path, _ = setup(session)
    assert client.post(path + "/cash", json={**manual(), "amount": amount}).status_code == 422


@pytest.mark.parametrize(
    "operation", ["payment", "generation", "payment_reverse", "same_payment", "same_manual"]
)
def test_concurrent_financial_operations(engine, session, operation):
    owner, team, client, path, _ = setup(session)
    if operation == "generation":
        preview = client.post(path + "/dues/preview", json={"competence": MONTH}).json()
        data = GenerateInput(competence=MONTH, preview_token=preview["preview_token"], confirm=True)
        dues = None
    else:
        dues = generate(client, path)[0]
        if operation == "payment_reverse":
            dues = pay(client, path, dues, payment(dues, "10.00"))
    user_id, team_id = owner.user_id, team.id
    shared_payment = payment(dues, "20.00") if dues else None
    shared_manual = manual()
    session.commit()
    barrier = Barrier(2)

    def run(index):
        with Session(engine) as worker:
            barrier.wait()
            try:
                if operation == "same_manual":
                    from app.application.finance_commands import EntryInput

                    finance_writes.manual_entry(
                        worker, user_id, team_id, EntryInput(**shared_manual)
                    )
                elif operation == "generation":
                    finance_writes.generate(worker, user_id, team_id, data)
                elif operation == "payment_reverse" and index:
                    from app.application.finance_commands import CancelEntryInput

                    finance_writes.cancel_entry(
                        worker,
                        user_id,
                        team_id,
                        UUID(dues["payments"][0]["id"]),
                        CancelEntryInput(
                            reason="Correção", confirm=True, expected_dues_version=dues["version"]
                        ),
                    )
                else:
                    finance_writes.pay(
                        worker,
                        user_id,
                        team_id,
                        UUID(dues["id"]),
                        PaymentInput(
                            **(
                                shared_payment
                                if operation == "same_payment"
                                else payment(dues, "20.00")
                            )
                        ),
                    )
                worker.commit()
                return "ok"
            except Conflict:
                worker.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(results) == (
        ["ok", "ok"] if operation.startswith("same_") else ["conflict", "ok"]
    )
    assert session.scalar(select(func.count()).select_from(MonthlyDues)) == 2
    assert session.scalar(select(func.count()).select_from(CashEntry)) in (0, 1, 2)
    if operation.startswith("same_"):
        assert session.scalar(select(func.count()).select_from(CashEntry)) == 1


def test_constraint_cross_team_and_transaction_rollback(session, monkeypatch):
    owner, team, client, path, _ = setup(session)
    dues = generate(client, path)[0]
    other = make_team(session, make_player(session))
    session.commit()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                CashEntry(
                    team_id=other.id,
                    dues_id=UUID(dues["id"]),
                    command_id=uuid4(),
                    kind="INCOME",
                    category="Mensalidade",
                    description="Invalid",
                    amount=Decimal("1.00"),
                    entry_date=date.today(),
                    payment_method="PIX",
                    created_by=owner.user_id,
                )
            )
            session.flush()

    def fail(*args, **kwargs):
        raise RuntimeError("forced audit failure")

    monkeypatch.setattr(finance_writes, "audit", fail)
    with pytest.raises(RuntimeError, match="forced audit"):
        pay(client, path, dues)
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(CashEntry)) == 0
    assert session.get(MonthlyDues, UUID(dues["id"])).version == 1


def test_migration_preservation_and_downgrade_guard(engine, session):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    owner = make_player(session)
    make_team(session, owner)
    session.commit()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009")
        tables = [t for t in inspect(connection).get_table_names() if t != "alembic_version"]
        before = {
            t: connection.execute(
                text(f'SELECT {LEGACY_JSON}::text FROM "{t}" t ORDER BY {LEGACY_JSON}::text')
            ).all()
            for t in tables
        }
        command.upgrade(config, "head")
        assert all(
            connection.execute(
                text(f'SELECT {LEGACY_JSON}::text FROM "{t}" t ORDER BY {LEGACY_JSON}::text')
            ).all()
            == rows
            for t, rows in before.items()
        )
        command.check(config)
    setup(session)
    with pytest.raises(RuntimeError, match="financial records"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014"
