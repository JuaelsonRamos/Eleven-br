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


def test_browser_match_events_flow(engine: Engine) -> None:
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
            for name in [
                "Bruno",
                "Carlos",
                "Diego",
                "Eduardo",
                "João Antônio de Albuquerque e Vasconcelos dos Santos Pereira da Silva",
            ]:
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
            formation = stored()["formation"]
            squad = formation["squads"][0]
            scorer = next(p for p in squad["participants"] if p["guest_id"])
            assistant = next(p for p in squad["participants"] if p["id"] != scorer["id"])

            def person_label(person):
                return ("Convidado: " if person["guest_id"] else "") + person["name"]

            page.get_by_role("button", name="Voltar à pelada", exact=True).click()
            page.get_by_role("button", name="Nova partida", exact=True).click()
            page.get_by_role("button", name="Criar partida", exact=True).click()
            first = page.get_by_test_id("match-1")
            first.get_by_role("button", name="Iniciar partida", exact=True).click()
            for side, score in [("Time 1", 3), ("Time 2", 2)]:
                for value in range(1, score + 1):
                    first.get_by_role("button", name=f"Aumentar placar {side}", exact=True).click()
                    expect(
                        first.get_by_label(f"Placar {side}: {value}", exact=True)
                    ).to_be_visible()
            first.get_by_role("button", name="Eventos da partida", exact=True).click()
            panel = page.get_by_test_id("match-events")
            expect(
                panel.get_by_text("Falta identificar 3 gols do Time 1.", exact=True)
            ).to_be_visible()
            panel.get_by_role("button", name="Registrar gol", exact=True).click()
            form = page.get_by_test_id("match-event-form")
            form.get_by_role(
                "radio", name=f"Participante: {person_label(scorer)}", exact=True
            ).click()
            expect(
                form.get_by_role("radio", name=f"Assistência: {person_label(scorer)}", exact=True)
            ).to_have_count(0)
            form.get_by_role(
                "radio", name=f"Assistência: {person_label(assistant)}", exact=True
            ).click()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)
            for width in [320, 390, 1280]:
                page.set_viewport_size({"width": width, "height": 900})
                form.scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                for option in form.get_by_role("radio").all():
                    bounds = option.bounding_box()
                    assert bounds and bounds["width"] <= width and bounds["height"] >= 48
                page.screenshot(path=str(artifacts / f"match-events-form-{width}.png"))
            form.get_by_role("button", name="Salvar registro", exact=True).click()
            goal = page.get_by_test_id("match-event-1")
            expect(
                goal.get_by_text(f"Assistência: {person_label(assistant)}", exact=True)
            ).to_be_visible()
            expect(
                panel.get_by_text("Time 1: 1 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            expect(first.get_by_label("Placar Time 1: 3", exact=True)).to_be_visible()
            panel.get_by_role("button", name="Registrar cartão", exact=True).click()
            form.get_by_role("radio", name="Cartão amarelo", exact=True).click()
            form.get_by_role(
                "radio", name=f"Participante: {person_label(scorer)}", exact=True
            ).click()
            form.get_by_role("button", name="Salvar registro", exact=True).click()
            card = page.get_by_test_id("match-event-2")
            expect(
                card.get_by_text(f"🟨 Cartão amarelo · {person_label(scorer)}", exact=True)
            ).to_be_visible()
            card.get_by_role("button", name="Editar registro", exact=True).click()
            form.get_by_role("radio", name="Cartão vermelho", exact=True).click()
            form.get_by_role("button", name="Salvar registro", exact=True).click()
            expect(
                card.get_by_text(f"🟥 Cartão vermelho · {person_label(scorer)}", exact=True)
            ).to_be_visible()
            goal.get_by_role("button", name="Editar registro", exact=True).click()
            form.get_by_role(
                "radio", name=f"Participante: {person_label(assistant)}", exact=True
            ).click()
            form.get_by_role("button", name="Salvar registro", exact=True).click()
            expect(goal.get_by_text("Assistência:", exact=False)).to_have_count(0)
            goal.get_by_role("button", name="Remover registro", exact=True).click()
            goal.get_by_role("button", name="Confirmar remoção do registro", exact=True).click()
            expect(
                panel.get_by_text("Time 1: 0 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            expect(first.get_by_label("Placar Time 1: 3", exact=True)).to_be_visible()
            first.get_by_role("button", name="Finalizar partida", exact=True).click()
            first.get_by_role("button", name="Confirmar finalização", exact=True).click()
            expect(first.get_by_text("FINALIZADA", exact=True)).to_be_visible()
            panel.get_by_role("button", name="Registrar gol", exact=True).click()
            form.get_by_role(
                "radio", name=f"Participante: {person_label(scorer)}", exact=True
            ).click()
            form.get_by_role("button", name="Salvar registro", exact=True).click()
            expect(
                panel.get_by_text("Time 1: 1 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            for width in [320, 390, 1280]:
                page.set_viewport_size({"width": width, "height": 900})
                panel.scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(artifacts / f"match-events-{width}.png"))
            panel.get_by_role("button", name="Fechar eventos da partida", exact=True).click()
            first.get_by_role("button", name="Eventos da partida", exact=True).click()
            expect(
                panel.get_by_text("Time 1: 1 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            page.reload()
            page.get_by_role("tab", name="Jogos", exact=True).click()
            page.get_by_role(
                "button", name="Abrir Pelada do sorteio • 27/09/2026", exact=True
            ).click()
            first.get_by_role("button", name="Eventos da partida", exact=True).click()
            expect(
                panel.get_by_text("Time 1: 1 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            expect(
                panel.get_by_text(f"🟥 Cartão vermelho · {person_label(scorer)}", exact=True)
            ).to_be_visible()
            # Read-only member uses a separate browser session.
            member_context = browser.new_context(viewport={"width": 390, "height": 844})
            member_context.route("**/v1/**", isolated)
            member_page = member_context.new_page()
            member_page.goto("http://localhost:8081", wait_until="domcontentloaded")
            member_page.get_by_role("button", name="Já tenho conta", exact=True).click()
            member_page.get_by_label("Telefone ou e-mail", exact=True).fill(
                "member-events@example.com"
            )
            member_page.get_by_label("Senha", exact=True).fill("formation-test-123")
            member_page.get_by_role("button", name="Entrar", exact=True).click()
            member_page.get_by_role("tab", name="Jogos", exact=True).click()
            member_page.get_by_role(
                "button", name="Abrir Pelada do sorteio • 27/09/2026", exact=True
            ).click()
            member_page.get_by_role("button", name="Eventos da partida", exact=True).click()
            expect(
                member_page.get_by_text("Time 1: 1 de 3 gols identificados.", exact=True)
            ).to_be_visible()
            for label in [
                "Registrar gol",
                "Registrar cartão",
                "Editar registro",
                "Remover registro",
            ]:
                expect(member_page.get_by_role("button", name=label, exact=True)).to_have_count(0)
            member_context.unroute_all(behavior="wait")
            member_context.close()
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
