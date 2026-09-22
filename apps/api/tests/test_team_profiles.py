from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.sessions import create_session
from app.application.teams import add_member
from app.domain.team_identity import CODE_ALPHABET
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session
from app.infrastructure.models import Player, Team, TeamMembership, User
from app.main import create_app
from tests.conftest import make_player

DATA = {"name": "Tabajara", "city": "Vitória", "state": "ES", "modalities": ["society"]}


def client_for(session: Session, player: Player | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    if player:
        user = session.get(User, player.user_id)
        assert user
        token = create_session(session, user, "native", get_settings()).access_token
        session.commit()
        client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_registration_identity_president_free_and_multiple_teams(session: Session) -> None:
    player = make_player(session)
    client = client_for(session, player)
    created = client.post("/v1/teams", json=DATA)
    assert created.status_code == 201
    first = created.json()
    assert UUID(first["id"]).version == 4
    assert len(first["code"]) == 8 and set(first["code"]) <= set(CODE_ALPHABET)
    assert first["my_role"] == "president" and first["can_edit"] is True
    assert first["plan"] == "free" and first["crest_url"] is None
    team = session.get(Team, UUID(first["id"]))
    assert team
    president = session.get(TeamMembership, team.president_membership_id)
    assert president and president.player_id == player.id and president.status == "active"
    assert len({player.user_id, player.id, team.id, president.id}) == 4
    assert session.scalar(select(func.count()).select_from(TeamMembership)) == 1
    second = client.post("/v1/teams", json=DATA).json()
    assert second["name"] == first["name"]
    assert first["id"] != second["id"] and first["code"] != second["code"]
    assert len(client.get("/v1/teams").json()) == 2
    updated = client.put(
        f"/v1/teams/{first['id']}", json={**DATA, "name": "Novo nome", "modalities": ["futsal"]}
    )
    assert updated.status_code == 200
    assert updated.json()["code"] == first["code"]
    assert updated.json()["id"] == first["id"]
    assert updated.json()["my_role"] == "president"
    assert client.get(f"/v1/teams/{second['id']}").json() == second
    assert client.get(f"/v1/teams/{first['id']}/administration").json()["active_player_limit"] == 24


def test_duplicate_advisory_is_public_limited_and_nonblocking(session: Session) -> None:
    first = client_for(session, make_player(session))
    created = first.post("/v1/teams", json=DATA).json()
    other = client_for(session, make_player(session))
    similar = other.post(
        "/v1/teams/similar", json={**DATA, "name": "TABAJARA FC", "city": "vitoria"}
    )
    assert similar.status_code == 200
    assert len(similar.json()) == 1
    assert set(similar.json()[0]) == {"name", "code", "city", "state", "modalities"}
    assert other.get(f"/v1/teams/{created['id']}").status_code == 404
    assert other.post("/v1/teams", json=DATA).status_code == 201
    assert other.post("/v1/teams/similar", json={**DATA, "modalities": ["futsal"]}).json() == []
    assert other.post("/v1/teams/similar", json={**DATA, "city": "Outra cidade"}).json() == []


def test_manipulated_ids_permissions_and_inactive_membership(session: Session) -> None:
    president = make_player(session)
    outsider = make_player(session)
    owner = client_for(session, president)
    other = client_for(session, outsider)
    own = owner.post("/v1/teams", json=DATA).json()
    foreign = other.post("/v1/teams", json={**DATA, "name": "Outro"}).json()
    assert [team["id"] for team in owner.get("/v1/teams").json()] == [own["id"]]
    for path in [f"/v1/teams/{foreign['id']}", f"/v1/teams/{foreign['id']}/administration"]:
        assert owner.get(path).status_code == 404
    assert owner.put(f"/v1/teams/{foreign['id']}", json=DATA).status_code == 404
    membership = add_member(session, team_id=UUID(foreign["id"]), player_id=president.id)
    session.commit()
    assert len(owner.get("/v1/teams").json()) == 2
    detail = owner.get(f"/v1/teams/{foreign['id']}")
    assert detail.json()["my_role"] == "member" and detail.json()["can_edit"] is False
    assert detail.headers["cache-control"] == "no-store"
    assert owner.put(f"/v1/teams/{foreign['id']}", json=DATA).status_code == 403
    membership.status = "inactive"
    session.commit()
    assert len(owner.get("/v1/teams").json()) == 1
    assert owner.get(f"/v1/teams/{foreign['id']}").status_code == 404
    assert owner.put(f"/v1/teams/{foreign['id']}", json=DATA).status_code == 404
    assert other.get(f"/v1/teams/{foreign['id']}").json() == foreign


def test_registration_requires_authentication_and_existing_player(session: Session) -> None:
    client = client_for(session)
    assert client.post("/v1/teams", json=DATA).status_code == 401
    assert client.post("/v1/teams/similar", json=DATA).status_code == 401
    assert client.get("/v1/teams/options").status_code == 401
    player = make_player(session)
    client = client_for(session, player)
    session.delete(player)
    session.commit()
    assert client.post("/v1/teams", json=DATA).status_code == 409
    assert session.scalar(select(func.count()).select_from(Team)) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"name": "  "},
        {"city": ""},
        {"state": "XX"},
        {"modalities": ["invalid"]},
        {"modalities": []},
        {"modalities": "campo,society"},
        {"modalities": [None]},
        {"plan": "pro"},
        {"code": "CUSTOM99"},
        {"president_membership_id": "anything"},
        {"crest_url": "data:image/png;base64,anything"},
        {"id": "anything"},
    ],
)
def test_identity_validation_and_protected_fields(
    session: Session, change: dict[str, object]
) -> None:
    client = client_for(session, make_player(session))
    created = client.post("/v1/teams", json=DATA).json()
    assert client.post("/v1/teams", json={**DATA, **change}).status_code == 422
    assert client.put(f"/v1/teams/{created['id']}", json={**DATA, **change}).status_code == 422
    assert client.get(f"/v1/teams/{created['id']}").json() == created


def test_code_collision_retries_without_orphan_memberships(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application import team_profiles

    codes = iter(["ABCDEFGH", "ABCDEFGH", "JKLMNPQR"])
    monkeypatch.setattr(team_profiles, "generate_code", lambda: next(codes))
    client = client_for(session, make_player(session))
    assert client.post("/v1/teams", json=DATA).json()["code"] == "ABCDEFGH"
    assert client.post("/v1/teams", json=DATA).json()["code"] == "JKLMNPQR"
    assert session.scalar(select(func.count()).select_from(Team)) == 2
    assert session.scalar(select(func.count()).select_from(TeamMembership)) == 2


@pytest.mark.parametrize(
    "modalities", [["campo"], ["society", "futsal"], ["campo", "society", "futsal"]]
)
def test_free_team_modalities_persist_and_edit(session: Session, modalities: list[str]) -> None:
    client = client_for(session, make_player(session))
    response = client.post("/v1/teams", json={**DATA, "modalities": modalities})
    assert response.status_code == 201
    team = response.json()
    assert team["plan"] == "free" and team["modalities"] == modalities
    path = f"/v1/teams/{team['id']}"
    assert client.get(path).json()["modalities"] == modalities
    assert client.get("/v1/teams").json()[0]["modalities"] == modalities
    session.expire_all()
    assert session.get(Team, UUID(team["id"])).modalities == modalities
    for choices in [["campo", "society", "futsal"], ["futsal"], ["society", "futsal"]]:
        updated = client.put(path, json={**DATA, "modalities": choices})
        assert updated.status_code == 200 and updated.json()["modalities"] == choices
        assert client.get(path).json()["modalities"] == choices
        assert updated.json()["code"] == team["code"]
        assert updated.json()["my_role"] == "president" and updated.json()["plan"] == "free"
    # Selections are a set, returned in stable vocabulary order, never duplicated.
    assert client.put(path, json={**DATA, "modalities": ["futsal", "society", "futsal"]}).json()[
        "modalities"
    ] == ["society", "futsal"]


def test_uf_catalog_validation_and_normalization(session: Session) -> None:
    client = client_for(session, make_player(session))
    options = client.get("/v1/teams/options").json()
    assert len(options["states"]) == 27
    assert {item["value"] for item in options["states"]} == set(
        "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
    )
    assert {"value": "ES", "label": "Espírito Santo (ES)"} in options["states"]
    for state in ["es", " SP ", "df"]:
        response = client.post("/v1/teams", json={**DATA, "state": state})
        assert response.status_code == 201
        assert response.json()["state"] == state.strip().upper()
    for state in ["", "XX", "ZZ", "São Paulo", "E", "ESP"]:
        assert client.post("/v1/teams", json={**DATA, "state": state}).status_code == 422


def test_similar_teams_match_any_shared_modality(session: Session) -> None:
    client = client_for(session, make_player(session))
    client.post("/v1/teams", json={**DATA, "modalities": ["campo", "futsal"]})
    assert (
        len(
            client.post(
                "/v1/teams/similar", json={**DATA, "modalities": ["society", "futsal"]}
            ).json()
        )
        == 1
    )
    assert client.post("/v1/teams/similar", json=DATA).json() == []


def test_database_rejects_empty_or_null_modalities(session: Session) -> None:
    client = client_for(session, make_player(session))
    data = client.post("/v1/teams", json=DATA).json()
    team = session.get(Team, UUID(data["id"]))
    assert team
    for invalid in [[], [None], None]:
        with pytest.raises(IntegrityError), session.begin_nested():
            team.modalities = invalid
            session.flush()
