"""Opt-in Web statistics flow with a temporary API and isolated PostgreSQL schema."""

import os
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.application.teams import add_member
from app.infrastructure.models import TeamMembership


def test_browser_statistics_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with engine.connect() as connection:
        schema = connection.scalar(text("select current_schema()"))
    assert schema and schema.startswith("test_") and (engine.url.database or "").endswith("_test")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": engine.url.update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False),
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-proxy-headers",
            "--no-access-log",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/ready").status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("Isolated API did not start")
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", headers={"X-Eleven-Client": "native"}
        ) as api:

            def register(email, name):
                ticket = api.post(
                    "/v1/auth/register",
                    json={
                        "name": name,
                        "contact": email,
                        "password": "formation-test-123",
                        "password_confirmation": "formation-test-123",
                    },
                ).json()
                result = api.post(
                    "/v1/auth/verify",
                    json={
                        "challenge_token": ticket["challenge_token"],
                        "code": ticket["development_code"],
                    },
                )
                assert result.status_code == 200
                return {"Authorization": f"Bearer {result.json()['access_token']}"}

            owner = register("owner-stats@example.com", "Presidente das estatísticas")
            inactive = register("inactive-stats@example.com", "Jogador histórico")
            zero = register("zero-stats@example.com", "Jogador sem partidas")
            team = api.post(
                "/v1/teams",
                headers=owner,
                json={
                    "name": "Tabajara FC",
                    "city": "Vitória",
                    "state": "ES",
                    "modalities": ["society", "futsal"],
                },
            ).json()
            with Session(engine) as session:
                memberships = []
                for headers in [inactive, zero]:
                    profile = api.get("/v1/me", headers=headers).json()
                    memberships.append(
                        add_member(
                            session, team_id=UUID(team["id"]), player_id=UUID(profile["player_id"])
                        ).id
                    )
                session.commit()
            event = api.post(
                f"/v1/teams/{team['id']}/events",
                headers=owner,
                json={
                    "modality": "society",
                    "kind": "PELADA",
                    "title": "Pelada das estatísticas",
                    "date": date.today().isoformat(),
                    "time": "08:00",
                    "location": "Campo do bairro",
                },
            ).json()
            event_path = f"/v1/teams/{team['id']}/events/{event['id']}"
            for headers in [owner, inactive]:
                assert (
                    api.put(
                        event_path + "/attendance", headers=headers, json={"response": "VOU"}
                    ).status_code
                    == 200
                )
            long_name = "João Antônio de Albuquerque e Vasconcelos dos Santos Pereira da Silva"
            for name in [long_name, "Convidado do jogo"]:
                assert (
                    api.post(event_path + "/guests", headers=owner, json={"name": name}).status_code
                    == 201
                )
            pool = api.get(event_path + "/formation", headers=owner).json()
            formation = api.post(
                event_path + "/formation/draw",
                headers=owner,
                json={
                    "team_count": 2,
                    "expected_fingerprint": pool["fingerprint"],
                    "participants": [
                        {"kind": p["kind"], "source_id": p["source_id"]}
                        for p in pool["participants"]
                    ],
                },
            ).json()["formation"]
            match = api.post(
                event_path + "/matches",
                headers=owner,
                json={
                    "formation_id": formation["id"],
                    "expected_formation_version": formation["version"],
                    "home_formation_team_id": formation["squads"][0]["id"],
                    "away_formation_team_id": formation["squads"][1]["id"],
                },
            ).json()
            match_path = event_path + f"/matches/{match['id']}"
            match = api.post(
                match_path + "/start", headers=owner, json={"expected_version": match["version"]}
            ).json()
            squad = next(
                s
                for s in formation["squads"]
                if any(p["name"] == long_name for p in s["participants"])
            )
            scorer = next(p for p in squad["participants"] if p["name"] == long_name)
            assistant = next(p for p in squad["participants"] if p != scorer)
            for type, assist in [
                ("GOAL", assistant["id"]),
                ("YELLOW_CARD", None),
                ("RED_CARD", None),
            ]:
                result = api.post(
                    match_path + "/events",
                    headers=owner,
                    json={
                        "expected_version": match["version"],
                        "type": type,
                        "participant_id": scorer["id"],
                        "assist_participant_id": assist,
                    },
                )
                assert result.status_code == 201, result.text
                match = result.json()["match"]
            match = api.put(
                match_path + "/score",
                headers=owner,
                json={"expected_version": match["version"], "home_score": 5, "away_score": 3},
            ).json()
            with Session(engine) as session:
                member = session.get(TeamMembership, memberships[0])
                assert member
                member.status = "inactive"
                session.commit()

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width": 390, "height": 844})
                errors = []
                bundles = []

                def isolated(route):
                    source = urlsplit(route.request.url)
                    route.fulfill(
                        response=route.fetch(
                            url=f"http://127.0.0.1:{port}{source.path}"
                            + (f"?{source.query}" if source.query else "")
                        )
                    )

                context.route("**/v1/**", isolated)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: (
                        bundles.append(response.status) if ".bundle?" in response.url else None
                    ),
                )
                html = page.goto(
                    "http://localhost:8081", wait_until="domcontentloaded", timeout=120000
                )
                assert html and html.status == 200
                page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)
                page.get_by_label("Telefone ou e-mail", exact=True).fill("owner-stats@example.com")
                page.get_by_label("Senha", exact=True).fill("formation-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()

                def visible_text(value):
                    return page.get_by_text(value, exact=True).and_(
                        page.locator(':not([aria-hidden="true"] *)')
                    )

                def button(label):
                    return page.get_by_role("button", name=label, exact=True).last

                button("Estatísticas").click()
                expect(visible_text("Ainda não há estatísticas.")).to_be_visible()
                expect(button("Ir para Jogos")).to_be_visible()
                button("Ver estatísticas de Jogador sem partidas").click()
                expect(visible_text("Nenhuma partida finalizada neste período.")).to_be_visible()
                button("Voltar para estatísticas").click()
                result = api.post(
                    match_path + "/finish",
                    headers=owner,
                    json={"expected_version": match["version"], "confirm": True},
                )
                assert result.status_code == 200, result.text
                page.get_by_role("tab", name="Início", exact=True).click()
                button("Estatísticas").click()
                expect(visible_text("Gols identificados")).to_be_visible()
                expect(visible_text("Inativo").last).to_be_visible()
                button("Artilharia").click()
                expect(visible_text(long_name)).to_be_visible()
                expect(visible_text("1 gol")).to_be_visible()
                artifacts = Path(__file__).resolve().parents[3] / ".local"
                artifacts.mkdir(exist_ok=True)
                for width in [320, 390, 1280]:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    button(f"Ver estatísticas de {long_name}").scroll_into_view_if_needed()
                    bounds = button(f"Ver estatísticas de {long_name}").bounding_box()
                    assert bounds and bounds["width"] <= width
                    page.screenshot(path=str(artifacts / f"statistics-ranking-{width}.png"))
                button("Assistências").click()
                expect(visible_text("1 assist.")).to_be_visible()
                button("Cartões").click()
                expect(visible_text("Disciplina")).to_be_visible()
                expect(visible_text(long_name)).to_be_visible()
                button("Este mês").click()
                expect(visible_text(long_name)).to_be_visible()
                button("Futsal").click()
                expect(visible_text("Ainda não há estatísticas.")).to_be_visible()
                button("Todas").click()
                button("Geral").click()
                button("Ver estatísticas de Jogador histórico").click()
                expect(visible_text("Histórico recente")).to_be_visible()
                expect(visible_text("Inativo")).to_be_visible()
                expect(visible_text("Time 1 5 × 3 Time 2")).to_be_visible()
                button("Voltar para estatísticas").click()
                button("Artilharia").click()
                button(f"Ver estatísticas de {long_name}").click()
                expect(
                    visible_text(
                        "Convidado desta pelada. Seu histórico é restrito a esta ocorrência."
                    )
                ).to_be_visible()
                expect(visible_text("Gols: 1,00 · Assistências: 0,00")).to_be_visible()
                for width in [320, 390, 1280]:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    visible_text("Perfil estatístico").scroll_into_view_if_needed()
                    page.screenshot(path=str(artifacts / f"statistics-profile-{width}.png"))
                button("Voltar para estatísticas").click()
                page.reload()
                button("Estatísticas").click()
                expect(visible_text("Tabajara FC")).to_be_visible()
                expect(visible_text("Gols identificados")).to_be_visible()
                expect(page.get_by_role("tab")).to_have_count(4)
                assert not errors, errors
                assert bundles and all(status == 200 for status in bundles)
                context.unroute_all(behavior="wait")
                context.close()
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
