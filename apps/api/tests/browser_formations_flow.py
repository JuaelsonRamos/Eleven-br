"""Opt-in Chromium flow against the existing Expo and an isolated test API/database."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.application.teams import add_member


def test_browser_formations_flow(engine: Engine) -> None:
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

            owner = register("owner-events@example.com", "Presidente dos eventos")
            member = register("member-events@example.com", "Jogador dos eventos")
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
            profile = api.get("/v1/me", headers=member).json()
            with Session(engine) as session:
                add_member(session, team_id=UUID(team["id"]), player_id=UUID(profile["player_id"]))
                session.commit()
            event_response = api.post(
                f"/v1/teams/{team['id']}/events",
                headers=owner,
                json={
                    "modality": "society",
                    "kind": "PELADA",
                    "title": "Pelada do sorteio",
                    "date": "2026-09-27",
                    "time": "08:00",
                    "location": "Campo do bairro",
                },
            )
            assert event_response.status_code == 201
            event = event_response.json()
            event_path = f"/v1/teams/{team['id']}/events/{event['id']}"
            for headers in [owner, member]:
                assert (
                    api.put(
                        event_path + "/attendance", headers=headers, json={"response": "VOU"}
                    ).status_code
                    == 200
                )
            for name in ["Bruno", "Carlos", "Diego", "Eduardo", "Fabio"]:
                assert (
                    api.post(event_path + "/guests", headers=owner, json={"name": name}).status_code
                    == 201
                )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            errors = []
            writes = []

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
                "request",
                lambda request: (
                    writes.append(request.url) if request.url.endswith("/formation/draw") else None
                ),
            )
            page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
            page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)

            def login(email):
                page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
                page.get_by_label("Senha", exact=True).fill("formation-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()

            def open_formation(label="Montar times"):
                page.get_by_role("tab", name="Jogos", exact=True).click()
                page.get_by_role(
                    "button", name="Abrir Pelada do sorteio • 27/09/2026", exact=True
                ).click()
                page.get_by_role("button", name=label, exact=True).click()

            def visible_text(value):
                return page.get_by_text(value, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            def stored():
                return httpx.get(
                    f"http://127.0.0.1:{port}{event_path}/formation", headers=owner
                ).json()

            login("owner-events@example.com")
            open_formation()
            expect(visible_text("Tabajara FC")).to_be_visible()
            expect(visible_text("Participantes — 7")).to_be_visible()
            page.get_by_role("checkbox", name="Participa: Convidado: Eduardo", exact=True).click()
            for name in ["Presidente dos eventos", "Convidado: Bruno", "Convidado: Carlos"]:
                page.get_by_role("checkbox", name=f"Goleiro: {name}", exact=True).click()
            page.get_by_role("button", name="Mais times", exact=True).click()
            expect(visible_text("Número de times: 3")).to_be_visible()
            expect(visible_text("Time 1 → 2 participantes")).to_be_visible()
            with page.expect_response(
                lambda r: r.request.method == "POST" and r.url.endswith("/formation/draw")
            ) as result:
                page.get_by_role("button", name="Sortear", exact=True).click()
            assert result.value.status == 200
            first = result.value.json()["formation"]
            assert len(first["excluded"]) == 1
            assert all(
                len(s["participants"]) == 2 and sum(p["goalkeeper"] for p in s["participants"]) == 1
                for s in first["squads"]
            )
            expect(visible_text("Times da pelada")).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)
            page.screenshot(
                path=str(artifacts / "formation-mobile.png"), full_page=True, animations="disabled"
            )
            page.get_by_role("button", name="Mover Bruno", exact=True).click()
            destination = next(
                s for s in first["squads"] if all(p["name"] != "Bruno" for p in s["participants"])
            )
            page.get_by_role("button", name=f"Mover para {destination['name']}", exact=True).click()
            expect(
                page.get_by_role("button", name=f"Mover para {destination['name']}", exact=True)
            ).to_have_count(0)
            moved = stored()["formation"]
            assert moved["version"] == first["version"] + 1
            assert any(
                p["name"] == "Bruno"
                for s in moved["squads"]
                if s["id"] == destination["id"]
                for p in s["participants"]
            )
            page.reload(wait_until="domcontentloaded")
            open_formation()
            expect(visible_text("Times da pelada")).to_be_visible()
            assert stored()["formation"] == moved
            page.get_by_role("button", name="Sortear novamente", exact=True).click()
            page.get_by_role("button", name="Sortear", exact=True).click()
            expect(
                visible_text(
                    "Já existe uma formação para esta pelada. Deseja substituir o sorteio atual?"
                )
            ).to_be_visible()
            assert len(writes) == 1
            page.get_by_role("button", name="Manter sorteio atual", exact=True).click()
            assert stored()["formation"] == moved
            page.get_by_role("button", name="Sortear novamente", exact=True).click()
            page.get_by_role("button", name="Sortear", exact=True).click()
            page.get_by_role("button", name="Confirmar novo sorteio", exact=True).click()
            expect(visible_text("Times da pelada")).to_be_visible()
            assert len(writes) == 2
            stable = stored()["formation"]
            with httpx.Client(base_url=f"http://127.0.0.1:{port}") as api:
                assert (
                    api.post(
                        event_path + "/guests", headers=owner, json={"name": "Novo convidado"}
                    ).status_code
                    == 201
                )
                bruno = next(
                    p["guest_id"]
                    for s in stable["squads"]
                    for p in s["participants"]
                    if p["name"] == "Bruno"
                )
                assert (
                    api.post(event_path + f"/guests/{bruno}/remove", headers=owner).status_code
                    == 200
                )
            page.get_by_role("button", name="Atualizar participantes", exact=True).click()
            expect(
                visible_text("A lista de participantes mudou desde o último sorteio.")
            ).to_be_visible()
            expect(visible_text("Bruno • Convidado")).to_be_visible()
            assert stored()["formation"] == stable
            page.get_by_role("tab", name="Mais", exact=True).click()
            page.get_by_role("button", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            login("member-events@example.com")
            open_formation("Ver times da pelada")
            expect(visible_text("Times da pelada")).to_be_visible()
            expect(page.get_by_role("button", name="Sortear novamente", exact=True)).to_have_count(
                0
            )
            expect(page.get_by_role("button", name="Mover Bruno", exact=True)).to_have_count(0)
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
