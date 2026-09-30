"""Official team location: IBGE municipality, President confirmation and search fallback."""

import csv
import hashlib
import importlib.util
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.teams import add_member
from app.domain.policies import Permission, Plan, Role
from app.domain.team_identity import STATES
from app.infrastructure.launch_models import TeamAudit
from app.infrastructure.models import MembershipPermission, Municipality, Team
from tests.conftest import ROOT, make_player
from tests.test_events import DATA as PELADA
from tests.test_finance import generate
from tests.test_finance import setup as finance_team
from tests.test_foundation import make_team
from tests.test_opponents import base, club, names, ranked, search
from tests.test_team_profiles import DATA, VILA_VELHA, VITORIA, client_for

SAO_PAULO, BRASILIA = 3550308, 5300108
MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0016_team_locations.py"
)
DATASET = MIGRATION.parents[1] / "data" / "ibge_municipalities.csv"
# SHA-256 (LF line endings) of the list retrieved from the IBGE API on 2026-09-30.
DATASET_SHA256 = "89faee4ba0a860ebf292f8528425cc1ef155550ea4b7cbb8ca3c14aaacfa6101"
# Official IBGE UF codes: the first two digits of each municipality code.
UF_CODES = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22,
    "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32,
    "RJ": 33, "SP": 35, "PR": 41, "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}  # fmt: skip
UPDATE_APP = "Atualize o app para escolher a cidade na lista oficial."


def confirm(session: Session, team: Team, code: int) -> Team:
    """A team whose President already confirmed an official municipality."""
    place = session.get(Municipality, code)
    assert place
    team.city, team.state, team.municipality_code = place.name, place.state, place.code
    team.location_confirmed_at = datetime.now(UTC)
    session.commit()
    return team


def legacy(session: Session, city: str, state: str = "ES"):
    president = make_player(session)
    team = make_team(session, president)
    team.city, team.state = city, state
    session.commit()
    return team, client_for(session, president), president


def test_official_municipalities_come_from_the_versioned_ibge_table(session: Session) -> None:
    raw = DATASET.read_bytes().replace(b"\r\n", b"\n")  # Same content on any checkout.
    assert hashlib.sha256(raw).hexdigest() == DATASET_SHA256  # Never edited silently.
    with DATASET.open(encoding="utf-8", newline="") as handle:
        rows = {(int(row["code"]), row["state"], row["name"]) for row in csv.DictReader(handle)}
    assert len(rows) == len({code for code, _, _ in rows}) == 5571 and set(UF_CODES) == set(STATES)
    assert all(code // 100000 == UF_CODES[state] for code, state, _ in rows)  # Code ↔ UF.
    assert len({(state, name) for _, state, name in rows}) == 5571  # Names unique per UF.
    loaded = session.execute(select(Municipality.code, Municipality.state, Municipality.name))
    assert set(loaded.tuples()) == rows  # The migration seeds exactly the versioned file.
    client = client_for(session, make_player(session))
    # Distrito Federal: the official municipal structure has only Brasília.
    only_brasilia = [{"code": BRASILIA, "name": "Brasília"}]
    assert client.get("/v1/locations/states/DF/municipalities").json()["items"] == only_brasilia
    found = client.get("/v1/locations/states/ES/municipalities")
    assert found.status_code == 200 and "max-age" in found.headers["cache-control"]
    items = found.json()["items"]
    assert len(items) == 78 and {"code": VILA_VELHA, "name": "Vila Velha"} in items
    assert [item["name"] for item in items if item["name"].startswith("Vila")] == [
        "Vila Pavão",
        "Vila Valério",
        "Vila Velha",
    ]
    assert client.get("/v1/locations/states/XX/municipalities").status_code == 404
    anonymous = client_for(session)
    assert anonymous.get("/v1/locations/states/ES/municipalities").status_code == 401


def test_new_team_uses_an_official_municipality_and_is_born_confirmed(session: Session) -> None:
    client = client_for(session, make_player(session))
    created = client.post("/v1/teams", json={**DATA, "municipality_code": VILA_VELHA})
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["city"], body["state"], body["municipality_code"]) == (
        "Vila Velha",
        "ES",
        VILA_VELHA,
    )
    assert body["location_confirmed"] is True  # No second confirmation after registration.
    team = session.get(Team, UUID(body["id"]))
    assert team and team.location_confirmed_at is not None
    for invalid, status in (
        ({"state": "RJ"}, 409),  # Municipality of another UF.
        ({"municipality_code": 3299999}, 409),  # Nonexistent code.
        ({"municipality_code": str(VILA_VELHA)}, 422),  # Only an integer code.
    ):
        assert client.post("/v1/teams", json={**DATA, **invalid}).status_code == status
    free_text = {key: value for key, value in DATA.items() if key != "municipality_code"}
    assert client.post("/v1/teams", json={**free_text, "city": "Cidade Nova"}).status_code == 422
    assert session.scalar(select(func.count()).select_from(Team)) == 1  # No arbitrary city.


def test_older_clients_get_an_update_message_and_nothing_is_created(session: Session) -> None:
    client = client_for(session, make_player(session))
    # Payload of the app before Phase 5A (typed city): similar check, then registration.
    before_5a = {**DATA, "city": "Vitória"}
    del before_5a["municipality_code"]
    for path in ("/v1/teams/similar", "/v1/teams"):
        refused = client.post(path, json=before_5a)
        assert refused.status_code == 422  # Controlled refusal, never a 500.
        assert refused.json()["detail"] == UPDATE_APP  # The message older apps display.
    # A typed city is never accepted, not even next to an official code.
    mixed = client.post("/v1/teams", json={**before_5a, "municipality_code": VITORIA})
    assert (mixed.status_code, mixed.json()["detail"]) == (422, "Confira os campos informados.")
    assert session.scalar(select(func.count()).select_from(Team)) == 0  # Nothing partial.


def test_legacy_location_is_suggested_never_auto_confirmed(session: Session) -> None:
    team, client, _ = legacy(session, "  vila   VELHA ")
    status = client.get(f"/v1/teams/{team.id}/location").json()
    assert (status["confirmed"], status["can_change"], status["city"]) == (
        False,
        True,
        "  vila   VELHA ",
    )
    assert status["suggestion"] == {"code": VILA_VELHA, "name": "Vila Velha", "state": "ES"}
    listed = client.get("/v1/teams").json()[0]
    assert (listed["location_confirmed"], listed["municipality_code"]) == (False, None)
    session.refresh(team)
    assert team.municipality_code is None and team.city == "  vila   VELHA "  # Untouched.
    unclear, unclear_client, _ = legacy(session, "Vila")
    assert unclear_client.get(f"/v1/teams/{unclear.id}/location").json()["suggestion"] is None
    # DF administrative regions are not municipalities: no suggestion, Brasília is chosen.
    region, region_client, _ = legacy(session, "Taguatinga", "DF")
    assert region_client.get(f"/v1/teams/{region.id}/location").json()["suggestion"] is None
    brasilia = {"state": "DF", "municipality_code": BRASILIA}
    moved = region_client.put(f"/v1/teams/{region.id}/location", json=brasilia).json()
    assert (moved["city"], moved["state"], moved["location_confirmed"]) == ("Brasília", "DF", True)

    path = f"/v1/teams/{team.id}/location"
    confirmed = client.put(path, json={"state": "ES", "municipality_code": VILA_VELHA})
    assert confirmed.status_code == 200, confirmed.text
    assert (confirmed.json()["city"], confirmed.json()["location_confirmed"]) == (
        "Vila Velha",
        True,
    )
    changed = client.put(path, json={"state": "ES", "municipality_code": VITORIA}).json()
    assert (changed["city"], changed["municipality_code"]) == ("Vitória", VITORIA)
    assert client.put(path, json={"state": "RJ", "municipality_code": VITORIA}).status_code == 409
    assert client.put(path, json={"state": "ES", "municipality_code": 3299999}).status_code == 409
    audit = session.scalars(
        select(TeamAudit).where(TeamAudit.team_id == team.id).order_by(TeamAudit.created_at)
    ).all()
    assert [item.action for item in audit] == ["LOCATION_CONFIRMED", "LOCATION_CHANGED"]
    assert audit[0].before["city"] == "  vila   VELHA " and audit[0].before["confirmed"] is False
    assert audit[1].after == {
        "city": "Vitória",
        "state": "ES",
        "municipality_code": VITORIA,
        "confirmed": True,
    }


def test_only_the_president_confirms_or_changes_the_location(session: Session) -> None:
    team, president_client, _ = legacy(session, "Vila Velha")
    team.plan = Plan.PRO  # Administrators with grants exist only on PRO.
    admin = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=admin.id, role=Role.ADMIN)
    session.add(
        MembershipPermission(membership_id=membership.id, permission=Permission.MANAGE_TEAM)
    )
    member = make_player(session)
    add_member(session, team_id=team.id, player_id=member.id)
    session.commit()
    other_team, other_client, _ = legacy(session, "Vitória")
    path = f"/v1/teams/{team.id}/location"
    choice = {"state": "ES", "municipality_code": VILA_VELHA}
    admin_client, member_client = client_for(session, admin), client_for(session, member)
    assert admin_client.get(path).json()["can_change"] is False
    assert admin_client.put(path, json=choice).status_code == 403
    assert member_client.put(path, json=choice).status_code == 403
    assert other_client.put(path, json=choice).status_code == 404  # No access to another team.
    assert other_client.get(path).status_code == 404
    session.refresh(team)
    assert team.location_confirmed_at is None

    # The general profile edit keeps accepting the current location unchanged (older
    # clients), but never changes it — not even for administrators with manage_team.
    profile = {"name": "Tabajara", "modalities": ["campo"], "category": "mixed"}
    same = {**profile, "city": "Vila Velha", "state": "ES"}
    assert admin_client.put(f"/v1/teams/{team.id}", json=same).status_code == 200
    moved = {**profile, "city": "Vitória", "state": "ES"}
    assert admin_client.put(f"/v1/teams/{team.id}", json=moved).status_code == 409
    coded = {**profile, "municipality_code": VILA_VELHA}
    assert president_client.put(f"/v1/teams/{team.id}", json=coded).status_code == 409
    # Confirmation is never an input: forged fields are refused before any change.
    forged = {**choice, "location_confirmed_at": "2026-09-30T12:00:00Z"}
    assert admin_client.put(path, json=forged).status_code == 422
    flagged = {**profile, "location_confirmed": True}
    assert admin_client.put(f"/v1/teams/{team.id}", json=flagged).status_code == 422
    session.refresh(team)
    assert (team.municipality_code, team.location_confirmed_at) == (None, None)
    assert president_client.put(path, json=choice).status_code == 200
    assert other_team.location_confirmed_at is None  # Isolation between teams.


def test_database_keeps_code_uf_and_name_consistent(session: Session) -> None:
    team = confirm(session, legacy(session, "Vila Velha")[0], VILA_VELHA)
    for change in (
        {"state": "RJ"},  # Code of ES with another UF.
        {"city": "Vila Velha City"},  # Name that is not the official one.
        {"location_confirmed_at": None},  # A code must be confirmed.
        {"municipality_code": 3299999},  # Nonexistent municipality.
    ):
        with pytest.raises(IntegrityError), session.begin_nested():
            for key, value in change.items():
                setattr(team, key, value)
            session.flush()
        session.expire_all()


def test_opponent_search_uses_codes_and_keeps_legacy_teams(session: Session) -> None:
    me, client, _ = club(session, "Fut Girl", city="Vila Velha", state="ES")
    confirm(session, me, VILA_VELHA)
    confirm(session, club(session, "Aurora", city="x", state="ES")[0], VILA_VELHA)
    club(session, "Bruxas", city="vila  velha", state="ES")  # Legacy, not confirmed.
    confirm(session, club(session, "Cometas", city="x", state="ES")[0], VITORIA)
    club(session, "Dragoas", city="Vitoria", state="ES")  # Legacy, not confirmed.
    confirm(session, club(session, "Estrelas", city="x", state="SP")[0], SAO_PAULO)
    assert ranked(search(client, me)) == [
        ("Aurora", "city", True),
        ("Bruxas", "city", True),
        ("Cometas", "state", True),
        ("Dragoas", "state", True),
        ("Estrelas", "other", True),
    ]
    in_vitoria = search(client, me, state="ES", municipality=VITORIA)
    assert names(in_vitoria) == ["Cometas", "Dragoas"]
    wrong = client.get(
        base(me) + "/search",
        params={"modality": "campo", "category": "female", "state": "RJ", "municipality": VITORIA},
    )
    assert wrong.status_code == 409  # Municipality outside the chosen UF.
    # A legacy searcher still finds confirmed teams of the same typed city.
    typed, typed_client, _ = club(session, "Gaviões", city="VILA VELHA", state="ES")
    assert ranked(search(typed_client, typed))[:3] == [
        ("Aurora", "city", True),
        ("Bruxas", "city", True),
        ("Fut Girl", "city", True),
    ]
    # The fallback only ranks: searching never confirms or changes a legacy location.
    session.expire_all()
    pending = session.scalars(
        select(Team).where(Team.name.in_(["Bruxas", "Dragoas", "Gaviões"])).order_by(Team.name)
    ).all()
    assert [
        (team.city, team.municipality_code, team.location_confirmed_at) for team in pending
    ] == [
        ("vila  velha", None, None),
        ("Vitoria", None, None),
        ("VILA VELHA", None, None),
    ]


def test_unconfirmed_legacy_teams_keep_working_during_the_beta(session: Session) -> None:
    # Decision: the President is asked to confirm, but nothing is blocked meanwhile.
    _, team, client, finance, _ = finance_team(session)  # Roster and finance settings (PRO).
    assert (team.municipality_code, team.location_confirmed_at) == (None, None)
    assert generate(client, finance)  # Monthly dues.
    assert client.post(f"/v1/teams/{team.id}/events", json=PELADA).status_code == 201
    profile = {"name": "Legado FC", "modalities": ["campo"], "category": "female"}
    assert client.put(f"/v1/teams/{team.id}", json=profile).status_code == 200
    rival, rival_client, _ = club(session, "Rival")  # Legacy typed "São Paulo"/SP too.
    assert ranked(search(rival_client, rival)) == [("Legado FC", "city", True)]
    assert names(search(client, team)) == ["Rival"]
    session.refresh(team)
    assert (team.municipality_code, team.location_confirmed_at) == (None, None)  # Pending.


def test_0016_keeps_legacy_text_and_protects_confirmed_locations(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    places = (("Cariacica ", "ES"), ("Vitória", "ES"), ("Taguatinga", "DF"))
    with Session(engine) as session:
        old_ids = [legacy(session, city, state)[0].id for city, state in places]
        client_for(session, make_player(session)).post("/v1/teams", json=DATA)  # Confirmed.
    blocked = re.escape("Downgrade bloqueado: 1 time(s) com localização oficial confirmada")
    with pytest.raises(RuntimeError, match=blocked), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0015")
    with engine.begin() as connection:  # The refusal changed nothing.
        version = connection.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "0016"
        confirmed = "SELECT count(*) FROM teams WHERE location_confirmed_at IS NOT NULL"
        assert connection.execute(text(confirmed)).scalar_one() == 1
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        connection.execute(
            text("UPDATE teams SET municipality_code = NULL, location_confirmed_at = NULL")
        )
        command.downgrade(config, "0015")
        command.upgrade(config, "head")  # Existing database with legacy teams.
        rows = connection.execute(
            text(
                "SELECT city, state, municipality_code, location_confirmed_at FROM teams "
                "WHERE id = ANY(:ids) ORDER BY city"
            ),
            {"ids": old_ids},
        ).all()
        seeded = connection.execute(text("SELECT count(*) FROM municipalities")).scalar_one()
    assert seeded == 5571
    # Typed text is kept and nothing is confirmed, not even an exact official name.
    assert [tuple(row) for row in rows] == [
        ("Cariacica ", "ES", None, None),
        ("Taguatinga", "DF", None, None),
        ("Vitória", "ES", None, None),
    ]


def test_0016_refuses_a_missing_or_incomplete_dataset() -> None:
    spec = importlib.util.spec_from_file_location("team_locations_0016", MIGRATION)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    local = (ROOT / ".local").resolve()
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="test-locations-", dir=local) as temporary:
        migration.DATA = Path(temporary) / "ibge_municipalities.csv"
        with pytest.raises(RuntimeError, match="ausente"):
            migration.official_rows()  # Checked before any schema change.
        migration.DATA.write_text("code,state,name\n5300108,DF,Brasília\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="tem 1 municípios; esperados 5571"):
            migration.official_rows()
