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


def test_browser_matches_flow(engine: Engine) -> None:
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
            page.get_by_role("button", name="Sortear", exact=True).click()
            expect(visible_text("Times da pelada")).to_be_visible()
            page.get_by_role("button", name="Voltar à pelada", exact=True).click()
            page.get_by_role("button", name="Nova partida", exact=True).click()
            expect(page.get_by_role("radio", name="Time B: Time 1", exact=True)).to_be_disabled()
            page.get_by_role("button", name="Criar partida", exact=True).click()
            first = page.get_by_test_id("match-1")
            expect(first.get_by_text("AGENDADA", exact=True)).to_be_visible()
            first.get_by_role("button", name="Iniciar partida", exact=True).click()
            expect(first.get_by_label("Placar Time 1: 0", exact=True)).to_be_visible()
            first.get_by_role("button", name="Aumentar placar Time 1", exact=True).click()
            expect(first.get_by_label("Placar Time 1: 1", exact=True)).to_be_visible()
            page.set_viewport_size({"width": 320, "height": 900})
            first.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            for button in first.get_by_role("button").all():
                box = button.bounding_box()
                assert box and box["height"] >= 44
            page.screenshot(
                path=str(Path(__file__).resolve().parents[3] / ".local/matches-live-320.png")
            )
            current = httpx.get(
                f"http://127.0.0.1:{port}{event_path}/matches", headers=owner
            ).json()[0]
            changed = httpx.put(
                f"http://127.0.0.1:{port}{event_path}/matches/{current['id']}/score",
                headers=owner,
                json={"expected_version": current["version"], "home_score": 1, "away_score": 0},
            )
            assert changed.status_code == 200
            first.get_by_role("button", name="Aumentar placar Time 1", exact=True).click()
            expect(
                visible_text(
                    "O placar foi atualizado em outro dispositivo. Recarregue para continuar"
                )
            ).to_be_visible()
            page.get_by_role("button", name="Recarregar partidas", exact=True).click()
            expect(first.get_by_label("Placar Time 1: 1", exact=True)).to_be_visible()
            first.get_by_role("button", name="Finalizar partida", exact=True).click()
            first.get_by_role("button", name="Confirmar finalização", exact=True).click()
            expect(first.get_by_text("FINALIZADA", exact=True)).to_be_visible()
            first.get_by_role("button", name="Corrigir resultado", exact=True).click()
            first.get_by_role("button", name="Aumentar correção Time B", exact=True).click()
            first.get_by_role("button", name="Confirmar correção", exact=True).click()
            expect(first.get_by_label("Placar Time 2: 1", exact=True)).to_be_visible()
            expect(first.get_by_text("Resultado corrigido em", exact=False)).to_be_visible()
            page.get_by_role("button", name="Nova partida", exact=True).click()
            page.get_by_role("button", name="Criar partida", exact=True).click()
            second = page.get_by_test_id("match-2")
            second.get_by_role("button", name="Cancelar partida", exact=True).click()
            second.get_by_role(
                "button", name="Confirmar cancelamento da partida", exact=True
            ).click()
            expect(second.get_by_text("CANCELADA", exact=True)).to_be_visible()
            page.get_by_role("button", name="Nova partida", exact=True).click()
            page.get_by_role("button", name="Criar partida", exact=True).click()
            third = page.get_by_test_id("match-3")
            third.get_by_role("button", name="Iniciar partida", exact=True).click()
            third.get_by_role("button", name="Finalizar partida", exact=True).click()
            third.get_by_role("button", name="Confirmar finalização", exact=True).click()
            expect(third.get_by_text("FINALIZADA", exact=True)).to_be_visible()
            page.get_by_role("button", name="Atualizar partidas", exact=True).click()
            expect(first.get_by_label("Placar Time 1: 1", exact=True)).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            for width in [320, 390, 1280]:
                page.set_viewport_size({"width": width, "height": 900})
                first.scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(artifacts / f"matches-{width}.png"))
            page.get_by_role("button", name="Montar times", exact=True).click()
            expect(
                visible_text(
                    "Existem partidas vinculadas a esta formação. "
                    "Os times não podem mais ser alterados."
                )
            ).to_be_visible()
            expect(page.get_by_role("button", name="Refazer sorteio", exact=True)).to_have_count(0)
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
