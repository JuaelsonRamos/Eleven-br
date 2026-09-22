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


def test_browser_events_flow(engine: Engine) -> None:
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
                        "password": "events-test-123",
                        "password_confirmation": "events-test-123",
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            errors = []

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
            page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
            page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)

            def login(email):
                page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
                page.get_by_label("Senha", exact=True).fill("events-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()
                page.get_by_role("tab", name="Jogos", exact=True).click()

            def visible_text(value):
                return page.get_by_text(value, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            login("owner-events@example.com")
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Pelada de Domingo")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("08:00")
            page.get_by_label("Repetir semanalmente", exact=True).click()
            page.get_by_label("Repetir até (DD/MM/AAAA) — opcional", exact=True).fill("11/10/2026")
            page.get_by_label("Local", exact=True).fill("Arena do bairro")
            page.get_by_role("button", name="Salvar evento", exact=True).click()
            expect(visible_text("Pendentes: 2")).to_be_visible()
            page.get_by_role("button", name="VOU", exact=True).click()
            expect(visible_text("Confirmados: 1")).to_be_visible()
            page.get_by_role("button", name="NÃO VOU", exact=True).click()
            expect(visible_text("Não vão: 1")).to_be_visible()
            page.get_by_role("button", name="VOU", exact=True).click()
            page.get_by_label("Nome/apelido do convidado", exact=True).fill("Zeca")
            page.get_by_role("button", name="Adicionar convidado", exact=True).click()
            expect(visible_text("Convidados: 1")).to_be_visible()
            page.get_by_role("button", name="Remover Zeca", exact=True).click()
            expect(visible_text("Convidados: 0")).to_be_visible()
            page.get_by_role("button", name="Editar evento", exact=True).click()
            page.get_by_label("Local", exact=True).fill("Arena nova")
            page.get_by_role("button", name="Salvar evento", exact=True).click()
            expect(visible_text("Arena nova")).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)
            page.screenshot(path=str(artifacts / "events-detail-mobile.png"), animations="disabled")
            page.get_by_role("button", name="Voltar aos jogos", exact=True).click()
            expect(
                page.get_by_role("button", name="Abrir Pelada de Domingo", exact=False)
            ).to_have_count(3)
            page.get_by_role(
                "button", name="Abrir Pelada de Domingo • 04/10/2026", exact=True
            ).click()
            expect(visible_text("Pendentes: 2")).to_be_visible()
            expect(visible_text("Arena do bairro")).to_be_visible()
            page.get_by_role("button", name="Cancelar evento", exact=True).click()
            page.get_by_role("button", name="Confirmar cancelamento", exact=True).click()
            expect(visible_text("CANCELADO")).to_be_visible()
            expect(page.get_by_role("button", name="VOU", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Voltar aos jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_role("radio", name="Jogo avulso", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Amistoso")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("30/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("19:30")
            page.get_by_label("Local", exact=True).fill("Quadra central")
            page.get_by_label("Adversário (opcional)", exact=True).fill("Visitantes")
            page.get_by_role("button", name="Salvar evento", exact=True).click()
            expect(visible_text("Adversário: Visitantes")).to_be_visible()
            page.get_by_role("button", name="Voltar aos jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Pelada sem fim")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("10:00")
            page.get_by_label("Local", exact=True).fill("Campo")
            page.get_by_label("Repetir semanalmente", exact=True).click()
            page.get_by_role("button", name="Salvar evento", exact=True).click()
            expect(
                visible_text("Pelada semanal • sem data final • presença por data")
            ).to_be_visible()
            page.get_by_role("button", name="Encerrar recorrência", exact=True).click()
            page.get_by_role("button", name="Confirmar fim da recorrência", exact=True).click()
            expect(
                visible_text("Pelada semanal • recorrência encerrada • presença por data")
            ).to_be_visible()
            expect(visible_text("CANCELADO")).to_be_visible()
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("tab", name="Jogos", exact=True).click()
            expect(
                page.get_by_role("button", name="Abrir Amistoso • 30/09/2026", exact=True)
            ).to_be_visible()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.screenshot(path=str(artifacts / "events-desktop.png"), animations="disabled")
            page.get_by_role("tab", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            login("member-events@example.com")
            page.get_by_role(
                "button", name="Abrir Pelada de Domingo • 27/09/2026", exact=True
            ).click()
            expect(visible_text("Sua resposta: Pendente")).to_be_visible()
            expect(page.get_by_role("button", name="Editar evento", exact=True)).to_have_count(0)
            expect(
                page.get_by_role("button", name="Adicionar convidado", exact=True)
            ).to_have_count(0)
            page.get_by_role("button", name="VOU", exact=True).click()
            expect(visible_text("Confirmados: 2")).to_be_visible()
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
            print(
                "PASS: finite/endless weekly and one-off events, attendance, guests, edit, "
                "cancel event/series, reload and member permissions; isolated DB."
            )
    finally:
        server.terminate()
        server.wait(timeout=15)
