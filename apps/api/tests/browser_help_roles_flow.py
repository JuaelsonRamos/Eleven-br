"""Landing, help center and team roles in a real browser. Isolated _test schema and API."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.application.teams import add_member
from app.domain.policies import Plan
from app.infrastructure.models import Player, Team, TeamMembership, User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_foundation import make_team

WIDTHS = [320, 375, 430, 1280]


def test_browser_landing_help_and_team_roles(engine):
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner = make_player(session)
        owner.display_name = "Presidente Teste"
        team = make_team(session, owner, Plan.PRO)
        team.name = "Time dos papéis"
        heir = make_player(session)
        heir.display_name = "Novo Presidente"
        heir_membership = add_member(session, team_id=team.id, player_id=heir.id)
        user = session.get(User, owner.user_id)
        user.email, user.password_hash = "roles@example.com", hash_password("roles-password-123")
        session.commit()
        team_id, heir_id, owner_id = team.id, heir_membership.id, team.president_membership_id
        players = session.scalar(select(func.count()).select_from(Player))
    with engine.connect() as connection:
        schema = connection.scalar(text("select current_schema()"))
    assert schema.startswith("test_") and engine.url.database.endswith("_test")
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 900})

            def isolated(route):
                url = urlsplit(route.request.url)
                target = f"http://127.0.0.1:{port}{url.path}" + (
                    f"?{url.query}" if url.query else ""
                )
                route.fulfill(response=route.fetch(url=target))

            context.route("**/v1/**", isolated)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            artifacts = Path(__file__).resolve().parents[3] / ".local/prompt17-browser"
            artifacts.mkdir(exist_ok=True)

            def button(label):
                return page.get_by_role("button", name=label, exact=True)

            def visible(label):
                return page.get_by_text(label, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            def capture(name, height=900):
                for width in WIDTHS:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(150)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), (name, width)
                    page.screenshot(
                        path=str(artifacts / f"{name}-{width}.png"),
                        full_page=True,
                        animations="disabled",
                    )
                page.set_viewport_size({"width": 390, "height": 900})

            page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
            # Indicators come from the isolated database, never from constants.
            expect(visible("1 time")).to_be_visible(timeout=120000)
            expect(visible(f"{players} jogadores")).to_be_visible()
            expect(visible("já estão em campo")).to_be_visible()
            expect(page.get_by_role("heading", name="Entre em campo.", exact=True)).to_be_visible()
            for label in ["TIMES", "PELADAS", "JOGOS", "FINANCEIRO"]:
                expect(visible(label)).to_be_visible()
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 1500})
                page.wait_for_timeout(200)
                for label in ["Criar minha conta", "Já tenho conta"]:
                    box = button(label).bounding_box()
                    assert box and box["x"] >= 0 and box["x"] + box["width"] <= width, (
                        label,
                        width,
                    )
            capture("landing", 1500)
            button("Criar minha conta").click()
            expect(
                page.get_by_role("heading", name="Seu primeiro passo.", exact=True)
            ).to_be_visible()
            button("Já tenho conta").click()
            page.get_by_label("Telefone ou e-mail", exact=True).fill("roles@example.com")
            page.get_by_label("Senha", exact=True).fill("roles-password-123")
            button("Entrar").click()
            expect(page.get_by_role("heading", name="Time dos papéis", exact=True)).to_be_visible()

            button("Aprenda a usar o ELEVEN BR").first.click()
            expect(page.get_by_role("heading", name="Aprenda a usar", exact=True)).to_be_visible()
            page.get_by_label("Buscar na ajuda", exact=True).fill("sorteio")
            button("Como sortear times automaticamente").click()
            expect(visible("Passo a passo")).to_be_visible()
            capture("help-topic")
            button("Voltar aos assuntos").click()
            # The search is kept, so the reader returns to the same results.
            expect(button("Como sortear times automaticamente")).to_be_visible()
            expect(button("Como transferir a Presidência")).to_have_count(0)
            page.get_by_role("tab", name="Mais", exact=True).click()
            button("Aprenda a usar").click()
            expect(page.get_by_role("heading", name="Aprenda a usar", exact=True)).to_be_visible()
            capture("help-index")
            page.get_by_role("tab", name="Início", exact=True).click()
            button("Financeiro").click()
            button("Como funciona o Financeiro?").click()
            heading = page.get_by_role("heading", name="Como funciona o Financeiro", exact=True)
            expect(heading).to_be_visible()

            page.get_by_role("tab", name="Elenco", exact=True).click()
            button("Ver jogador Novo Presidente").click()
            expect(visible("Função no time")).to_be_visible()
            button("Tornar administrador").click()
            page.get_by_role("checkbox", name="Elenco e solicitações", exact=True).click()
            button("Salvar administração").click()
            expect(visible("Administração salva.")).to_be_visible()
            expect(visible("Administrador").first).to_be_visible()
            capture("admin")
            button("Remover administração").click()
            expect(visible("Administração removida.")).to_be_visible()
            button("Transferir Presidência").click()
            expect(visible("Transferir a Presidência para Novo Presidente?")).to_be_visible()
            expect(
                visible("Após confirmar, Novo Presidente passará a ser o Presidente deste time.")
            ).to_be_visible()
            capture("presidency")
            button("Confirmar transferência").click()
            expect(visible("Presidência transferida para Novo Presidente.")).to_be_visible()
            expect(button("Adicionar jogador")).to_have_count(0)
            button("Ver jogador Novo Presidente").click()
            expect(visible("Presidente")).to_be_visible()
            expect(button("Transferir Presidência")).to_have_count(0)
            assert not errors, errors
            context.close()
            browser.close()
        with Session(engine) as session:
            assert session.get(Team, team_id).president_membership_id == heir_id
            assert session.get(TeamMembership, owner_id).status == "active"
    finally:
        server.terminate()
        server.wait(timeout=15)
