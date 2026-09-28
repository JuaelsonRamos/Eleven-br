from tests.conftest import make_player
from tests.test_foundation import make_team
from tests.test_join_requests import approve, request, scenario
from tests.test_team_profiles import client_for


def test_shared_code_remains_usable_after_first_approval_and_accepts_link(session):
    _, team, admin, _, _, first = scenario(session)
    approve(admin, team, request(first, team))
    second = client_for(session, make_player(session))
    path = "/v1/teams/join/lookup"
    assert second.post(path, json={"code": f"  {team.code.lower()}  "}).status_code == 200
    linked = second.post(path, json={"code": f"https://example.com/?team_code={team.code}"})
    assert linked.status_code == 200, linked.text
    approve(admin, team, request(second, team))


def test_search_public_identity_normalization_pagination_and_own_state(session):
    owner, team, admin, _, _, client = scenario(session)
    team.name = "Tabajara   Futebol Clube"
    other = make_team(session, owner)
    other.name = "Tabajara Futebol Amigos"
    session.commit()
    path = "/v1/teams/join/search"
    data = client.get(path, params={"q": "  tAbAjArA   futebol  ", "limit": 1}).json()
    assert len(data["items"]) == 1 and data["has_more"]
    second = client.get(path, params={"q": "tabajara futebol", "limit": 1, "offset": 1}).json()
    assert len(second["items"]) == 1 and not second["has_more"]
    assert second["items"][0]["team"]["id"] != data["items"][0]["team"]["id"]
    item = client.get(path, params={"q": team.code.lower()}).json()["items"][0]
    assert set(item["team"]) == {"id", "name", "code", "city", "state", "modalities", "crest_url"}
    assert not item["pending"] and item["membership_status"] is None
    request(client, team)
    assert client.get(path, params={"q": team.code}).json()["items"][0]["pending"]
    assert not admin.get(path, params={"q": team.code}).json()["items"][0]["pending"]
    assert (
        admin.get(path, params={"q": team.code}).json()["items"][0]["membership_status"] == "active"
    )
    team.name = "Nome alterado"
    session.commit()
    assert client.get(path, params={"q": team.code}).json()["items"][0]["team"]["name"] == team.name
    assert client.get(path, params={"q": "%%"}).json()["items"] == []
    assert client.get(path, params={"q": "__"}).json()["items"] == []
    assert client.get(path, params={"q": "a"}).status_code == 422
    assert client.get(path, params={"q": "aa", "limit": 51}).status_code == 422
    assert client_for(session).get(path, params={"q": team.code}).status_code == 401
