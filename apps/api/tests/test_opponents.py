"""Opponents center: compatible search, challenge credit, fixture, bilateral score, reviews."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import challenges, fixtures
from app.application.teams import add_member
from app.domain import opponents as rules
from app.domain.policies import Conflict, Forbidden, Plan
from app.infrastructure.event_models import Event
from app.infrastructure.launch_models import TeamAudit
from app.infrastructure.models import User
from app.infrastructure.notification_models import Notification
from app.infrastructure.opponent_models import (
    FixtureReview,
    FixtureScore,
    TeamChallenge,
    TeamFixture,
)
from tests.conftest import make_player
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for

NOW = datetime(2026, 10, 5, 12, 0)  # São Paulo wall clock; the proposals below are for 10/10.
AFTER_KICKOFF = datetime(2026, 10, 10, 18, 0)
PUBLIC = {"id", "name", "code", "city", "state", "modalities", "crest_url", "category"}
YES = {"attended": True, "punctual": True, "kept_agreement": True}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    moment = {"now": NOW}
    monkeypatch.setattr(rules, "local_now", lambda: moment["now"])
    return moment


def club(
    session,
    name,
    *,
    city="São Paulo",
    state="SP",
    modalities=("campo",),
    category="female",
    plan=Plan.FREE,
):
    president = make_player(session)
    team = make_team(session, president, plan)
    team.name, team.city, team.state = name, city, state
    team.modalities, team.category = list(modalities), category
    session.commit()
    return team, client_for(session, president), president


def base(team):
    return f"/v1/teams/{team.id}/opponents"


def proposal(opponent, **changes):
    return {
        "command_id": str(uuid4()),
        "opponent_team_id": str(opponent.id),
        "modality": "campo",
        "date": "2026-10-10",
        "time": "16:00",
        "location": "Arena Central",
        "venue": "HOME",
        **changes,
    }


def search(client, team, modality="campo", category="female", **filters):
    found = client.get(
        base(team) + "/search",
        params={"modality": modality, "category": category, **filters},
    )
    assert found.status_code == 200, found.text
    return found.json()


def ranked(page):
    return [(item["team"]["name"], item["tier"], item["category_known"]) for item in page["items"]]


def names(page):
    return [item["team"]["name"] for item in page["items"]]


def member_client(session, team):
    player = make_player(session)
    add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    return client_for(session, player)


def count(session, model, *conditions):
    return session.scalar(select(func.count()).select_from(model).where(*conditions))


def accepted_fixture(session, **changes):
    home, home_client, home_president = club(session, "Mandantes")
    away, away_client, away_president = club(session, "Visitantes")
    sent = home_client.post(base(home) + "/challenges", json=proposal(away, **changes)).json()
    accepted = away_client.post(f"{base(away)}/challenges/{sent['id']}/accept").json()
    fixture = accepted["fixture_id"]
    return (
        fixture,
        (home, home_client, f"{base(home)}/fixtures/{fixture}", home_president),
        (away, away_client, f"{base(away)}/fixtures/{fixture}", away_president),
    )


def concurrently(engine, calls):
    """Runs the calls at the same time, each in its own session; domain errors are returned."""
    barrier = Barrier(len(calls))

    def run(call):
        with Session(engine) as own:
            barrier.wait()
            try:
                return call(own)
            except (Conflict, Forbidden) as error:
                return error

    with ThreadPoolExecutor(len(calls)) as pool:
        return list(pool.map(run, calls))


def test_main_flow_from_search_to_reliability_and_history(session, clock) -> None:
    girls, girls_client, _ = club(session, "Fut Girl")
    lionesses, lionesses_client, lionesses_president = club(session, "Leoas FC")
    free = {"limit": 1, "used": 0, "remaining": 1, "competence": "2026-10-01"}
    central = girls_client.get(base(girls)).json()
    assert central["credits"] == free and central["can_manage"]
    page = search(girls_client, girls)
    assert ranked(page) == [("Leoas FC", "city", True)]
    assert set(page["items"][0]["team"]) == PUBLIC  # Public identity only.
    assert page["items"][0]["reliability"]["label"] == "Sem histórico suficiente"
    profile = girls_client.get(f"{base(girls)}/teams/{lionesses.id}")
    assert profile.json()["can_challenge"] and profile.json()["compatible_modalities"] == ["campo"]
    assert profile.json()["history"] == {"challenges": [], "fixtures": []}
    private = session.get(User, lionesses_president.user_id)
    for response in (
        profile,
        girls_client.get(base(girls) + "/search?modality=campo&category=all"),
    ):
        assert private.email not in response.text and "@" not in response.text
    assert girls_client.get(base(girls)).json()["credits"] == free  # Search/profile: free.

    sent = girls_client.post(base(girls) + "/challenges", json=proposal(lionesses))
    assert sent.status_code == 201, sent.text
    challenge = sent.json()
    assert (challenge["status"], challenge["direction"], challenge["venue"]) == (
        "PENDING",
        "sent",
        "HOME",
    )
    assert girls_client.get(base(girls)).json()["credits"]["remaining"] == 0
    notice = session.scalar(select(Notification).where(Notification.type == "CHALLENGE_RECEIVED"))
    assert (notice.team_id, str(notice.entity_id), notice.action) == (
        lionesses.id,
        challenge["id"],
        "OPEN_CHALLENGE",
    )
    received = lionesses_client.get(base(lionesses) + "/challenges").json()["items"]
    assert [(item["id"], item["venue"], item["can_respond"]) for item in received] == [
        (challenge["id"], "AWAY", True)
    ]
    accepted = lionesses_client.post(f"{base(lionesses)}/challenges/{challenge['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    fixture_id = accepted.json()["fixture_id"]
    assert count(session, TeamFixture) == 1
    assert lionesses_client.get(base(lionesses)).json()["credits"]["used"] == 0  # Receiving.

    for team, client in ((girls, girls_client), (lionesses, lionesses_client)):
        listed = client.get(base(team) + "/fixtures").json()["items"]
        assert [item["id"] for item in listed] == [fixture_id]
        games = client.get(f"/v1/teams/{team.id}/events").json()["items"]
        assert [(game["kind"], game["fixture_id"], game["date"]) for game in games] == [
            ("JOGO", fixture_id, "2026-10-10")
        ]
    detail = girls_client.get(f"{base(girls)}/fixtures/{fixture_id}").json()
    assert (detail["side"], detail["result_status"], detail["can_report"]) == (
        "HOME",
        "NONE",
        False,
    )

    clock["now"] = AFTER_KICKOFF
    reported = girls_client.post(
        f"{base(girls)}/fixtures/{fixture_id}/score", json={"home_score": 4, "away_score": 2}
    ).json()
    assert (reported["result_status"], reported["home_score"]) == ("PENDING", None)
    confirmed = lionesses_client.post(
        f"{base(lionesses)}/fixtures/{fixture_id}/confirm", json={"home_score": 4, "away_score": 2}
    ).json()
    assert (confirmed["result_status"], confirmed["home_score"], confirmed["away_score"]) == (
        "VALIDATED",
        4,
        2,
    )
    for team, client, punctual in (
        (girls, girls_client, True),
        (lionesses, lionesses_client, False),
    ):
        reviewed = client.post(
            f"{base(team)}/fixtures/{fixture_id}/review", json={**YES, "punctual": punctual}
        )
        assert reviewed.status_code == 200 and not reviewed.json()["can_review"]
    after = girls_client.get(f"{base(girls)}/teams/{lionesses.id}").json()
    assert after["reliability"] == {
        "validated_fixtures": 1,
        "reviews": 1,
        "attended": 1,
        "punctual": 1,
        "kept_agreement": 1,
        "label": None,
    }
    assert [item["status"] for item in after["history"]["challenges"]] == ["ACCEPTED"]
    history = after["history"]["fixtures"][0]
    assert history["result_status"] == "VALIDATED"
    assert history["reviews"]["theirs"]["punctual"] is False
    assert {
        "CHALLENGE_RECEIVED",
        "CHALLENGE_ACCEPTED",
        "EVENT_CREATED",
        "FIXTURE_SCORE_REPORTED",
        "FIXTURE_SCORE_CONFIRMED",
        "FIXTURE_REVIEW_AVAILABLE",
    } <= set(session.scalars(select(Notification.type)))


def test_search_puts_compatibility_first_then_city_state_and_other_states(session) -> None:
    me, client, _ = club(session, "Fut Girl", modalities=("campo", "society", "futsal"))
    club(session, "Aurora", city="  sao   PAULO ")  # Same city despite accents/spaces/case.
    club(session, "Bruxas", city="Campinas")
    club(session, "Cometas", city="Rio de Janeiro", state="RJ")
    club(session, "Dragões", category="male")
    club(session, "Estrelas", modalities=("futsal",))
    club(session, "Faíscas", modalities=("society",))
    club(session, "Gaviões", category=None)  # Legacy teams without category.
    club(session, "Garças", city="Niterói", state="RJ", category=None)
    closed = club(session, "Hienas")[0]
    inactive = club(session, "Íris")[0]
    club(session, "Juntas", category="mixed")
    wolves, wolves_client, _ = club(session, "Lobos", city="Niterói", state="RJ", category="male")
    closed.accepts_challenges, inactive.status = False, "inactive"
    session.commit()

    # Compatible teams by proximity, then unknown categories (never taken as compatible).
    assert ranked(search(client, me)) == [
        ("Aurora", "city", True),
        ("Bruxas", "state", True),
        ("Cometas", "other", True),
        ("Gaviões", "city", False),
        ("Garças", "other", False),
    ]
    assert names(search(client, me, category="male")) == ["Dragões", "Lobos", "Gaviões", "Garças"]
    assert names(search(client, me, category="mixed")) == ["Juntas", "Gaviões", "Garças"]
    assert names(search(client, me, modality="futsal")) == ["Estrelas"]
    assert names(search(client, me, modality="society")) == ["Faíscas"]
    assert ranked(search(client, me, category="all")) == [
        ("Aurora", "city", True),
        ("Dragões", "city", True),
        ("Gaviões", "city", False),
        ("Juntas", "city", True),
        ("Bruxas", "state", True),
        ("Cometas", "other", True),
        ("Garças", "other", False),
        ("Lobos", "other", True),
    ]
    # Explicit location filter: UF, and a normalized city inside it.
    assert names(search(client, me, state="RJ")) == ["Cometas", "Garças"]
    # Official municipality filter; the legacy typed "Rio de Janeiro" matches it (fallback).
    assert names(search(client, me, state="RJ", municipality=3304557)) == ["Cometas"]
    no_state = client.get(base(me) + "/search?modality=campo&category=female&municipality=3304557")
    assert no_state.status_code == 409
    # No compatible team nearby: the search expands and keeps modality and category.
    assert ranked(search(wolves_client, wolves, category="male"))[0] == ("Dragões", "other", True)
    wrong = wolves_client.get(base(wolves) + "/search?modality=futsal&category=male")
    assert wrong.status_code == 409  # Only a modality of the searching team.
    member = member_client(session, me)
    assert member.get(base(me) + "/search?modality=campo&category=female").status_code == 403


def test_free_credit_is_spent_only_by_a_valid_challenge(engine, session, clock, monkeypatch):
    free, client, president = club(session, "Fut Girl")
    first = club(session, "Leoas FC")[0]
    second, second_client, _ = club(session, "Panteras")
    for _ in range(3):
        search(client, free)
        client.get(f"{base(free)}/teams/{first.id}")
    assert client.get(base(free)).json()["credits"]["used"] == 0  # Search and profiles: free.
    past = proposal(first, date="2026-10-01")
    assert client.post(base(free) + "/challenges", json=past).status_code == 409
    assert client.get(base(free)).json()["credits"]["used"] == 0  # Invalid request: not spent.

    def failing(*args, **kwargs):
        raise RuntimeError("forced failure after the insert")

    data = challenges.ChallengeInput.model_validate(proposal(first))
    # The shared test session outlives requests: end its transaction (locks) like a request.
    session.rollback()
    with monkeypatch.context() as patch, Session(engine) as own:
        patch.setattr(challenges, "challenge_notice", failing)
        with pytest.raises(RuntimeError):
            challenges.create(own, president.user_id, free.id, data)
    assert count(session, TeamChallenge) == 0  # Rolled back: the credit is still available.

    command = proposal(first)
    assert client.post(base(free) + "/challenges", json=command).status_code == 201
    retry = client.post(base(free) + "/challenges", json=command)
    assert retry.status_code == 201 and count(session, TeamChallenge) == 1  # Same operation.
    blocked = client.post(base(free) + "/challenges", json=proposal(second))
    assert blocked.status_code == 403 and "ELEVEN BR PRO" in blocked.json()["detail"]
    assert client.get(base(free)).json()["credits"] == {
        "limit": 1,
        "used": 1,
        "remaining": 0,
        "competence": "2026-10-01",
    }
    # Receiving, viewing and answering never spend the credit.
    incoming = second_client.post(base(second) + "/challenges", json=proposal(free)).json()
    assert client.get(base(free) + "/challenges").json()["items"][0]["id"] == incoming["id"]
    assert client.post(f"{base(free)}/challenges/{incoming['id']}/accept").status_code == 200
    assert client.get(base(free)).json()["credits"]["used"] == 1

    clock["now"] = datetime(2026, 11, 1, 0, 5)  # New São Paulo month: a new credit.
    renewed = client.post(base(free) + "/challenges", json=proposal(second, date="2026-11-07"))
    assert renewed.status_code == 201
    pro, pro_client, _ = club(session, "Pro FC", plan=Plan.PRO)
    for day in ("2026-11-07", "2026-11-08", "2026-11-09"):
        sent = pro_client.post(base(pro) + "/challenges", json=proposal(first, date=day))
        assert sent.status_code == 201
    assert pro_client.get(base(pro)).json()["credits"]["limit"] is None
    charged = (TeamChallenge.charged, TeamChallenge.challenger_team_id == pro.id)
    assert count(session, TeamChallenge, *charged) == 0


def test_concurrent_sends_never_duplicate_or_exceed_the_free_credit(engine, session) -> None:
    free, _, free_president = club(session, "Fut Girl")
    pro, _, pro_president = club(session, "Pro FC", plan=Plan.PRO)
    targets = [club(session, f"Alvo {index}")[0] for index in range(3)]

    def send(president, team, payload):
        data = challenges.ChallengeInput.model_validate(payload)
        return lambda own: challenges.create(own, president.user_id, team.id, data)

    same = proposal(targets[0])  # The same command twice: one challenge.
    results = concurrently(engine, [send(pro_president, pro, same)] * 2)
    assert results[0]["id"] == results[1]["id"]
    equivalent = [proposal(targets[1]), proposal(targets[1])]
    results = concurrently(engine, [send(pro_president, pro, item) for item in equivalent])
    assert sum(isinstance(result, Conflict) for result in results) == 1
    spend = [proposal(targets[2]), proposal(targets[0])]
    results = concurrently(engine, [send(free_president, free, item) for item in spend])
    assert sum(isinstance(result, Forbidden) for result in results) == 1
    assert count(session, TeamChallenge, TeamChallenge.challenger_team_id == pro.id) == 2
    assert count(session, TeamChallenge, TeamChallenge.challenger_team_id == free.id) == 1


def test_database_guards_back_the_credit_and_pending_proposals(session) -> None:
    alpha, alpha_client, _ = club(session, "Alfa")
    beta = club(session, "Beta")[0]
    sent = alpha_client.post(base(alpha) + "/challenges", json=proposal(beta)).json()
    original = session.get(TeamChallenge, UUID(sent["id"]))
    columns = ("competence", "modality", "date", "time", "location", "venue", "created_by")
    copy = {key: getattr(original, key) for key in columns}
    for row in (
        # A second Free credit in the same month, for another proposal.
        {
            **copy,
            "challenger_team_id": alpha.id,
            "challenged_team_id": beta.id,
            "charged": True,
            "date": date(2026, 10, 11),
        },
        # The equivalent pending proposal in the other direction.
        {**copy, "challenger_team_id": beta.id, "challenged_team_id": alpha.id, "charged": False},
    ):
        with pytest.raises(IntegrityError):
            session.add(TeamChallenge(**row, command_id=uuid4()))
            session.flush()
        session.rollback()


def test_challenge_rules_permissions_and_notifications(session, clock) -> None:
    alpha, alpha_client, _ = club(session, "Alfa", plan=Plan.PRO)
    beta, beta_client, _ = club(session, "Beta", plan=Plan.PRO)
    futsal = club(session, "Gama", modalities=("futsal",))[0]
    outsider, outsider_client, _ = club(session, "Delta")
    path = base(alpha) + "/challenges"
    assert alpha_client.post(path, json=proposal(alpha)).status_code == 409  # Itself.
    assert alpha_client.post(path, json=proposal(futsal)).status_code == 409  # Modality.
    assert alpha_client.post(path, json=proposal(beta, modality="volei")).status_code == 422
    missing = proposal(beta, opponent_team_id=str(uuid4()))
    assert alpha_client.post(path, json=missing).status_code == 404
    command = proposal(beta)
    first = alpha_client.post(path, json=command)
    assert first.status_code == 201, first.text
    challenge_id = first.json()["id"]
    assert alpha_client.post(path, json=command).json()["id"] == challenge_id  # Retry.
    assert alpha_client.post(path, json={**command, "location": "Outro"}).status_code == 409
    assert alpha_client.post(path, json=proposal(beta, location="Outro")).status_code == 409
    reverse = beta_client.post(base(beta) + "/challenges", json=proposal(alpha))
    assert reverse.status_code == 409  # The equivalent proposal in the other direction.
    other_day = alpha_client.post(path, json=proposal(beta, date="2026-10-11"))
    assert other_day.status_code == 201  # A different proposal is not a duplicate.
    assert count(session, Notification, Notification.type == "CHALLENGE_RECEIVED") == 2

    beta_path = f"{base(beta)}/challenges/{challenge_id}"
    assert alpha_client.post(f"{base(alpha)}/challenges/{challenge_id}/accept").status_code == 403
    assert beta_client.post(beta_path + "/cancel").status_code == 403
    assert outsider_client.post(beta_path + "/accept").status_code == 404  # IDOR: not a member.
    other = f"{base(outsider)}/challenges/{challenge_id}/accept"
    assert outsider_client.post(other).status_code == 404  # Not involved.
    assert member_client(session, beta).post(beta_path + "/accept").status_code == 403

    assert beta_client.post(beta_path + "/reject").json()["status"] == "REJECTED"
    assert beta_client.post(beta_path + "/reject").json()["status"] == "REJECTED"  # Idempotent.
    assert beta_client.post(beta_path + "/accept").status_code == 409
    assert count(session, Notification, Notification.type == "CHALLENGE_REJECTED") == 1
    assert count(session, TeamFixture) == 0

    cancel = f"{base(alpha)}/challenges/{other_day.json()['id']}/cancel"
    assert alpha_client.post(cancel).json()["status"] == "CANCELLED"
    assert alpha_client.post(cancel).status_code == 200
    accept_cancelled = f"{base(beta)}/challenges/{other_day.json()['id']}/accept"
    assert beta_client.post(accept_cancelled).status_code == 409
    assert count(session, Notification, Notification.type == "CHALLENGE_CANCELLED") == 1
    assert count(session, TeamFixture) == 0

    third = alpha_client.post(path, json=proposal(beta)).json()
    clock["now"] = datetime(2026, 10, 10, 16, 0)  # Kickoff: an unanswered proposal expires.
    received = beta_client.get(base(beta) + "/challenges").json()["items"][0]
    assert (received["id"], received["status"], received["can_respond"]) == (
        third["id"],
        "EXPIRED",
        False,
    )
    assert beta_client.post(f"{base(beta)}/challenges/{third['id']}/accept").status_code == 409

    fourth = alpha_client.post(path, json=proposal(beta, date="2026-10-17")).json()
    settings = beta_client.put(base(beta) + "/settings", json={"accepts_challenges": False})
    assert settings.json()["accepts_challenges"] is False
    assert count(session, TeamAudit, TeamAudit.action == "OPPONENT_SETTINGS_UPDATED") == 1
    closed = outsider_client.post(base(outsider) + "/challenges", json=proposal(beta))
    assert closed.status_code == 409 and "não está aceitando" in closed.json()["detail"]
    assert "Beta" not in names(search(outsider_client, outsider))
    accepted = beta_client.post(f"{base(beta)}/challenges/{fourth['id']}/accept")
    assert accepted.json()["status"] == "ACCEPTED"  # Existing challenges stay answerable.
    member = member_client(session, beta)
    assert (
        member.put(base(beta) + "/settings", json={"accepts_challenges": True}).status_code == 403
    )


def test_acceptance_creates_one_shared_fixture_despite_concurrent_retries(
    engine: Engine, session: Session
) -> None:
    visitor, visitor_client, _ = club(session, "Visitantes")
    host, host_client, host_president = club(session, "Mandantes")
    challenge = visitor_client.post(
        base(visitor) + "/challenges",
        json=proposal(host, venue="AWAY", notes="Levar coletes"),
    ).json()

    def accept(own):
        return challenges.respond(
            own, host_president.user_id, host.id, UUID(challenge["id"]), "accept"
        )

    results = concurrently(engine, [accept] * 3)
    assert len({str(result["fixture_id"]) for result in results}) == 1
    retry = host_client.post(f"{base(host)}/challenges/{challenge['id']}/accept").json()
    assert retry["fixture_id"] == str(results[0]["fixture_id"])
    session.expire_all()
    fixture = session.scalars(select(TeamFixture)).one()
    assert (
        fixture.challenge_id,
        fixture.home_team_id,
        fixture.away_team_id,
        fixture.modality,
        fixture.date,
        fixture.time,
        fixture.location,
        fixture.notes,
    ) == (
        UUID(challenge["id"]),
        host.id,
        visitor.id,
        "campo",
        date(2026, 10, 10),
        time(16),
        "Arena Central",
        "Levar coletes",
    )
    games = session.scalars(select(Event).where(Event.fixture_id == fixture.id)).all()
    assert sorted((game.team_id, game.opponent) for game in games) == sorted(
        [(host.id, "Visitantes"), (visitor.id, "Mandantes")]
    )
    assert count(session, Notification, Notification.type == "CHALLENGE_ACCEPTED") == 1

    game = f"/v1/teams/{visitor.id}/events/{next(g.id for g in games if g.team_id == visitor.id)}"
    edit = visitor_client.put(
        game,
        json={
            "modality": "campo",
            "kind": "JOGO",
            "title": "Outro horário",
            "date": "2026-10-11",
            "time": "18:00",
            "location": "Outro campo",
        },
    )
    assert edit.status_code == 409 and "dois times" in edit.json()["detail"]
    assert visitor_client.post(game + "/cancel").status_code == 409
    attendance = visitor_client.put(game + "/attendance", json={"response": "VOU"})
    assert attendance.json()["my_response"] == "VOU"  # Presence keeps working.


@pytest.mark.parametrize("first", ["home", "away"])
def test_score_is_official_only_when_both_sides_agree(session, clock, first) -> None:
    _, home, away = accepted_fixture(session)
    reporter, confirmer = (home, away) if first == "home" else (away, home)
    score = {"home_score": 4, "away_score": 2}
    assert reporter[1].post(reporter[2] + "/score", json=score).status_code == 409  # Early.
    clock["now"] = AFTER_KICKOFF
    reported = reporter[1].post(reporter[2] + "/score", json=score).json()
    assert (reported["result_status"], reported["home_score"]) == ("PENDING", None)
    clock["now"] += timedelta(days=30)  # Silence never confirms.
    waiting = confirmer[1].get(confirmer[2]).json()
    assert (waiting["result_status"], waiting["home_score"], waiting["can_confirm"]) == (
        "PENDING",
        None,
        True,
    )
    outsider, outsider_client, _ = club(session, "Estranhos")
    stranger = f"{base(outsider)}/fixtures/{waiting['id']}"
    assert outsider_client.post(stranger + "/confirm", json=score).status_code == 404
    assert outsider_client.post(confirmer[2] + "/confirm", json=score).status_code == 404
    assert outsider_client.get(confirmer[2]).status_code == 404  # IDOR: no third-party read.
    helper = member_client(session, confirmer[0])
    assert helper.post(confirmer[2] + "/confirm", json=score).status_code == 403
    stale = confirmer[1].post(confirmer[2] + "/confirm", json={"home_score": 3, "away_score": 2})
    assert stale.status_code == 409
    confirmed = confirmer[1].post(confirmer[2] + "/confirm", json=score).json()
    assert (confirmed["result_status"], confirmed["home_score"], confirmed["away_score"]) == (
        "VALIDATED",
        4,
        2,
    )
    notices = count(session, Notification)
    again = confirmer[1].post(confirmer[2] + "/confirm", json=score)
    assert again.json()["result_status"] == "VALIDATED" and count(session, Notification) == notices
    changed = {"home_score": 5, "away_score": 2}
    assert reporter[1].post(reporter[2] + "/score", json=changed).status_code == 409
    assert confirmer[1].post(confirmer[2] + "/score", json=changed).status_code == 409
    assert count(session, FixtureScore) == 2


def test_concurrent_confirmations_and_reviews_keep_one_result(engine, session, clock) -> None:
    fixture_id, home, away = accepted_fixture(session)
    clock["now"] = AFTER_KICKOFF
    home[1].post(home[2] + "/score", json={"home_score": 1, "away_score": 1})
    user, team, fixture = away[3].user_id, away[0].id, UUID(fixture_id)
    score = fixtures.ScoreInput(home_score=1, away_score=1)

    def confirm(own):
        return fixtures.submit(own, user, team, fixture, score, confirmation=True)

    results = concurrently(engine, [confirm, confirm])
    assert {result["result_status"] for result in results} == {"VALIDATED"}
    assert count(session, FixtureScore) == 2
    assert count(session, Notification, Notification.type == "FIXTURE_SCORE_CONFIRMED") == 1
    answers = fixtures.ReviewInput(**YES)

    def review(own):
        return fixtures.review(own, user, team, fixture, answers)

    concurrently(engine, [review, review])
    assert count(session, FixtureReview) == 1


def test_independent_reports_validate_when_equal_and_dispute_when_different(session, clock) -> None:
    _, home, away = accepted_fixture(session)
    _, other_home, other_away = accepted_fixture(session, date="2026-10-11")
    clock["now"] = datetime(2026, 10, 12, 9, 0)
    home[1].post(home[2] + "/score", json={"home_score": 1, "away_score": 0})
    agreed = away[1].post(away[2] + "/score", json={"home_score": 1, "away_score": 0}).json()
    assert (agreed["result_status"], agreed["home_score"]) == ("VALIDATED", 1)

    other_home[1].post(other_home[2] + "/score", json={"home_score": 4, "away_score": 2})
    disputed = (
        other_away[1].post(other_away[2] + "/score", json={"home_score": 3, "away_score": 2}).json()
    )
    assert (disputed["result_status"], disputed["home_score"], disputed["away_score"]) == (
        "DISPUTED",
        None,
        None,
    )
    assert not disputed["can_confirm"] and not disputed["can_review"]
    confirm = {"home_score": 4, "away_score": 2}
    assert other_away[1].post(other_away[2] + "/confirm", json=confirm).status_code == 409
    fix = {"home_score": 3, "away_score": 2}
    assert other_home[1].post(other_home[2] + "/score", json=fix).status_code == 409
    assert other_home[1].post(other_home[2] + "/review", json=YES).status_code == 409
    assert count(session, Notification, Notification.type == "FIXTURE_SCORE_DISPUTED") == 1
    # In the history, the dispute is identified and has no official score.
    profile = other_home[1].get(f"{base(other_home[0])}/teams/{other_away[0].id}").json()
    listed = [
        (item["result_status"], item["home_score"]) for item in profile["history"]["fixtures"]
    ]
    assert listed == [("DISPUTED", None)]


def test_reviews_need_a_validated_result_and_happen_once_per_side(session, clock) -> None:
    _, home, away = accepted_fixture(session)
    review = {**YES, "punctual": False}
    assert home[1].post(home[2] + "/review", json=review).status_code == 409  # No result.
    clock["now"] = AFTER_KICKOFF
    home[1].post(home[2] + "/score", json={"home_score": 0, "away_score": 0})
    assert home[1].post(home[2] + "/review", json=review).status_code == 409  # Pending.
    away[1].post(away[2] + "/confirm", json={"home_score": 0, "away_score": 0})
    assert member_client(session, home[0]).post(home[2] + "/review", json=review).status_code == 403
    outsider, outsider_client, _ = club(session, "Estranhos")
    stranger = home[2].replace(str(home[0].id), str(outsider.id))
    assert outsider_client.post(stranger + "/review", json=review).status_code == 404
    with_comment = home[1].post(home[2] + "/review", json={**review, "comment": "Atrasaram"})
    assert with_comment.status_code == 422  # No free-text comments in this phase.
    first = home[1].post(home[2] + "/review", json=review)
    assert first.status_code == 200 and first.json()["reviews"]["mine"]["punctual"] is False
    assert home[1].post(home[2] + "/review", json=review).status_code == 200  # Retry.
    assert home[1].post(home[2] + "/review", json=YES).status_code == 409  # Duplicate.
    assert away[1].post(away[2] + "/review", json=YES).status_code == 200
    assert count(session, FixtureReview) == 2
    # Each review counts for the other side, never for the reviewer.
    seen_by_home = home[1].get(f"{base(home[0])}/teams/{away[0].id}").json()["reliability"]
    seen_by_away = away[1].get(f"{base(away[0])}/teams/{home[0].id}").json()["reliability"]
    assert (seen_by_home["punctual"], seen_by_away["punctual"]) == (0, 1)
