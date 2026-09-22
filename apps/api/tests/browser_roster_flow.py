"""Opt-in real browser roster flow; all writes go to the isolated PostgreSQL test schema.

uv run --with playwright pytest tests/browser_roster_flow.py -q -s
Expo Web must already be running on localhost:8081.
"""

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

from app.application.teams import active_count, add_member
from app.infrastructure.models import Player


def test_browser_roster_flow(engine: Engine) -> None:
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
                        "password": "roster-test-123",
                        "password_confirmation": "roster-test-123",
                    },
                ).json()
                response = api.post(
                    "/v1/auth/verify",
                    json={
                        "challenge_token": ticket["challenge_token"],
                        "code": ticket["development_code"],
                    },
                )
                assert response.status_code == 200
                return response.json()["access_token"]

            owner_token = register("president-roster@example.com", "Presidente do teste")
            member_token = register("member-roster@example.com", "Membro do teste")
            owner_headers = {"Authorization": f"Bearer {owner_token}"}
            team = api.post(
                "/v1/teams",
                headers=owner_headers,
                json={
                    "name": "Tabajara FC",
                    "city": "Vitória",
                    "state": "ES",
                    "modalities": ["society", "futsal"],
                },
            ).json()
            member = api.get("/v1/me", headers={"Authorization": f"Bearer {member_token}"}).json()
            team_id = UUID(team["id"])
            with Session(engine) as session:
                add_member(session, team_id=team_id, player_id=UUID(member["player_id"]))
                session.commit()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            errors = []

            def isolated(route):
                source = urlsplit(route.request.url)
                target = f"http://127.0.0.1:{port}{source.path}" + (
                    f"?{source.query}" if source.query else ""
                )
                route.fulfill(response=route.fetch(url=target))

            context.route("**/v1/**", isolated)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
            page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)

            def login(email):
                page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
                page.get_by_label("Senha", exact=True).fill("roster-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()
                page.get_by_role("tab", name="Times", exact=True).click()
                page.get_by_role("button", name="Abrir Tabajara FC", exact=True).click()
                page.get_by_role("button", name="Elenco", exact=True).click()

            def active_text(value):
                return page.get_by_text(value, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            login("president-roster@example.com")
            expect(active_text("2 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            page.get_by_role("button", name="Ver jogador Presidente do teste", exact=True).click()
            expect(
                active_text("Transfira a presidência antes de inativar este jogador.")
            ).to_be_visible()
            expect(page.get_by_role("button", name="Inativar jogador", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Voltar ao elenco", exact=True).click()
            page.get_by_role("button", name="Adicionar jogador", exact=True).click()
            page.get_by_label("Nome do jogador", exact=True).fill("João Silva")
            page.get_by_role("button", name="Salvar jogador", exact=True).click()
            expect(active_text("Jogador adicionado.")).to_be_visible()
            expect(active_text("Ainda não possui conta")).to_be_visible()
            page.get_by_role("button", name="Voltar ao elenco", exact=True).click()
            page.get_by_role("button", name="Adicionar jogador", exact=True).click()
            page.get_by_label("Nome do jogador", exact=True).fill("Carlos Souza")
            page.get_by_label("Apelido (opcional)", exact=True).fill("Carlão")
            page.get_by_label("Telefone (opcional)", exact=True).fill("27999991234")
            page.get_by_label("E-mail (opcional)", exact=True).fill("CARLOS@EXAMPLE.COM")
            page.get_by_role("button", name="Salvar jogador", exact=True).click()
            expect(active_text("E-mail: carlos@example.com")).to_be_visible()
            page.get_by_role("button", name="Editar jogador", exact=True).click()
            page.get_by_label("Nome do jogador", exact=True).fill("Carlos Santos")
            page.get_by_role("button", name="Salvar jogador", exact=True).click()
            expect(active_text("Jogador atualizado.")).to_be_visible()
            page.get_by_role("button", name="Inativar jogador", exact=True).click()
            expect(active_text("Inativar Carlos Santos?")).to_be_visible()
            page.get_by_role("button", name="Inativar", exact=True).click()
            expect(active_text("Jogador inativado. Histórico preservado.")).to_be_visible()
            page.get_by_role("button", name="Voltar ao elenco", exact=True).click()
            page.get_by_role("button", name="Inativos", exact=True).click()
            page.get_by_role("button", name="Ver jogador Carlos Santos", exact=True).click()
            page.get_by_role("button", name="Reativar jogador", exact=True).click()
            expect(active_text("Jogador reativado.")).to_be_visible()
            expect(active_text("4 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            # A name/contact collision is an explicit confirmation, never account linking.
            page.get_by_role("button", name="Voltar ao elenco", exact=True).click()
            page.get_by_role("button", name="Adicionar jogador", exact=True).click()
            page.get_by_label("Nome do jogador", exact=True).fill("João Silva")
            page.get_by_role("button", name="Salvar jogador", exact=True).click()
            expect(active_text("Encontramos um jogador parecido neste elenco.")).to_be_visible()
            page.get_by_role("button", name="Adicionar mesmo assim", exact=True).click()
            expect(active_text("5 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(active_text("5 jogadores ativos")).to_be_visible()
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("button", name="Elenco", exact=True).click()
            expect(active_text("5 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)
            page.screenshot(path=str(artifacts / "roster-mobile.png"), animations="disabled")
            # Reach capacity only in the disposable test schema and verify the UI limit.
            with Session(engine) as session:
                while active_count(session, team_id) < 24:
                    player = Player(display_name=f"Jogador {active_count(session, team_id)}")
                    session.add(player)
                    session.flush()
                    add_member(session, team_id=team_id, player_id=player.id)
                session.commit()
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("button", name="Elenco", exact=True).click()
            expect(active_text("24 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            expect(
                page.get_by_role("button", name="Adicionar jogador", exact=True)
            ).to_be_disabled()
            page.get_by_role("tab", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            login("member-roster@example.com")
            expect(active_text("24 de 24 jogadores ativos · 0 inativos")).to_be_visible()
            expect(page.get_by_role("button", name="Adicionar jogador", exact=True)).to_have_count(
                0
            )
            page.get_by_role("button", name="Ver jogador Carlos Santos", exact=True).click()
            expect(page.get_by_role("button", name="Voltar ao elenco", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Editar jogador", exact=True)).to_have_count(0)
            expect(page.get_by_role("button", name="Inativar jogador", exact=True)).to_have_count(0)
            expect(active_text("E-mail: carlos@example.com")).to_have_count(0)
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
            print(
                "PASS: roster create/edit, contacts, status/filters, duplicate confirmation, "
                "capacity, reload, home, read-only member; isolated DB."
            )
    finally:
        server.terminate()
        server.wait(timeout=15)
