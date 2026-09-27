"""Real two-account join/link flow; all data lives in the isolated test schema."""

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

from app.infrastructure.models import Player, TeamMembership, User
from app.infrastructure.security import hash_password
from tests.test_join_requests import history, scenario
from tests.test_team_profiles import client_for


def test_browser_join_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner, team, admin, manual, source, _ = scenario(session)
        owner_user = session.get(User, owner.user_id)
        source_user = session.get(User, source.user_id)
        assert owner_user and source_user
        owner_user.email, source_user.email = "owner-join@example.com", "player-join@example.com"
        owner_user.password_hash = source_user.password_hash = hash_password("join-test-123")
        source.display_name = "João da conta"
        long_name = "João Antônio de Albuquerque e Vasconcelos dos Santos Pereira da Silva"
        target = session.get(Player, UUID(manual["player_id"]))
        member = session.get(TeamMembership, UUID(manual["membership_id"]))
        assert target and member
        target.display_name = member.roster_name = long_name
        team.name = "Tabajara FC"
        session.commit()
        history(session, team, admin, manual)
        code, team_id, source_id = team.code, str(team.id), source.id
        stats_path = f"/v1/teams/{team_id}/statistics/players/{manual['membership_id']}"
        stats_before = admin.get(stats_path).json()
        session.commit()
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            contexts, errors, bundles = [], [], []

            def login(email):
                context = browser.new_context(viewport={"width": 390, "height": 900})
                contexts.append(context)

                def isolated(route):
                    source_url = urlsplit(route.request.url)
                    route.fulfill(
                        response=route.fetch(
                            url=f"http://127.0.0.1:{port}{source_url.path}"
                            + (f"?{source_url.query}" if source_url.query else "")
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
                page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
                page.get_by_label("Senha", exact=True).fill("join-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()
                return page

            def visible(page, label):
                return page.get_by_text(label, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            def button(page, label):
                return page.get_by_role("button", name=label, exact=True)

            artifacts = Path(__file__).resolve().parents[3] / ".local"

            def capture(page, name, locator):
                for width in [320, 390, 768, 1280]:
                    page.set_viewport_size({"width": width, "height": 900})
                    locator.scroll_into_view_if_needed()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    page.screenshot(path=str(artifacts / f"join-{name}-{width}.png"))

            player_page = login("player-join@example.com")
            player_page.get_by_role("tab", name="Meus Times", exact=True).click()
            button(player_page, "Entrar em um time").click()
            expect(
                visible(player_page, "Você ainda não solicitou entrada em nenhum time.")
            ).to_be_visible()
            player_page.get_by_label("Código do time", exact=True).fill("ZZZZZZZZ")
            button(player_page, "Buscar time").click()
            expect(visible(player_page, "Time não encontrado. Confira o código.")).to_be_visible()
            player_page.get_by_label("Código do time", exact=True).fill(f" {code.lower()} ")
            button(player_page, "Buscar time").click()
            expect(visible(player_page, "Tabajara FC")).to_be_visible()
            capture(player_page, "lookup", button(player_page, "Solicitar entrada"))
            button(player_page, "Solicitar entrada").click()
            expect(visible(player_page, "Aguardando aprovação")).to_be_visible()
            button(player_page, "Cancelar solicitação para Tabajara FC").click()
            expect(visible(player_page, "Cancelada")).to_be_visible()
            button(player_page, "Buscar time").click()
            button(player_page, "Solicitar entrada").click()
            expect(visible(player_page, "Aguardando aprovação")).to_be_visible()

            owner_page = login("owner-join@example.com")
            button(owner_page, "Perfil do time").click()
            expect(button(owner_page, "Copiar código")).to_be_visible()
            # Chromium's clipboard permission is scoped to this disposable browser context.
            owner_page.context.grant_permissions(["clipboard-read", "clipboard-write"])
            button(owner_page, "Copiar código").click()
            expect(visible(owner_page, "Código copiado.")).to_be_visible()
            assert owner_page.evaluate("navigator.clipboard.readText()") == code
            owner_page.get_by_role("tab", name="Elenco", exact=True).click()
            button(owner_page, "Solicitações de entrada").click()
            expect(visible(owner_page, "1 pendente")).to_be_visible()
            button(owner_page, "Analisar João da conta").click()
            option = owner_page.get_by_role("radio", name=f"Vincular a {long_name}", exact=True)
            capture(owner_page, "candidates", option)
            option.click()
            button(owner_page, "Aprovar").click()
            expect(visible(owner_page, f"Vincular esta conta a {long_name}?")).to_be_visible()
            capture(owner_page, "confirmation", button(owner_page, "Confirmar aprovação"))
            button(owner_page, "Confirmar aprovação").click()
            expect(
                visible(owner_page, "Solicitação aprovada. Histórico preservado.")
            ).to_be_visible()
            expect(visible(owner_page, "Nenhuma solicitação pendente.")).to_be_visible()
            button(owner_page, "Voltar ao elenco").click()
            button(owner_page, f"Ver jogador {long_name}").click()
            expect(visible(owner_page, "Conta vinculada")).to_be_visible()

            button(player_page, "Atualizar pedidos").click()
            expect(visible(player_page, "Aprovada")).to_be_visible()
            button(player_page, "Ver meus times").click()
            button(player_page, "Abrir Tabajara FC").click()
            expect(visible(player_page, "Início do time")).to_be_visible()
            expect(visible(player_page, "Jogador")).to_be_visible()
            player_page.get_by_role("tab", name="Jogos", exact=True).click()
            button(player_page, "Abrir Pelada de Domingo • 27/09/2026").click()
            expect(button(player_page, "VOU")).to_be_visible()
            expect(button(player_page, "Criar evento")).to_have_count(0)
            player_page.get_by_role("tab", name="Elenco", exact=True).click()
            expect(button(player_page, f"Ver jogador {long_name}")).to_be_visible()
            expect(button(player_page, "Solicitações de entrada")).to_have_count(0)
            expect(button(player_page, "Adicionar jogador")).to_have_count(0)
            player_page.get_by_role("tab", name="Início", exact=True).click()
            button(player_page, "Estatísticas").click()
            button(player_page, f"Ver estatísticas de {long_name}").last.click()
            expect(visible(player_page, "Histórico recente")).to_be_visible()
            expect(visible(player_page, "Gols: 1,00 · Assistências: 1,00")).to_be_visible()
            player_page.reload()
            expect(visible(player_page, "Tabajara FC")).to_be_visible()
            expect(visible(player_page, "Jogador")).to_be_visible()
            expect(player_page.get_by_role("tab")).to_have_count(4)
            with Session(engine) as session:
                target = session.get(Player, UUID(manual["player_id"]))
                assert target and target.user_id
                assert session.get(Player, source_id) is None
                api_client = client_for(session, target)
                assert api_client.get(stats_path).json() == stats_before
            assert bundles and all(status == 200 for status in bundles)
            assert not errors, errors
            for context in contexts:
                context.unroute_all(behavior="wait")
                context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
