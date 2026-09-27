"""Internal finance Web flow with isolated PostgreSQL, API and two real sessions."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.application.teams import add_member
from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_roster import setup_roster


def test_browser_finance_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner, team, _, _ = setup_roster(session)
        player = make_player(session)
        player.display_name = (
            "João Antônio de Albuquerque e Vasconcelos dos Santos Pereira da Silva"
        )
        player_name = player.display_name
        add_member(session, team_id=team.id, player_id=player.id)
        for person, email in [
            (owner, "owner-finance@example.com"),
            (player, "player-finance@example.com"),
        ]:
            user = session.get(User, person.user_id)
            user.email = email
            user.password_hash = hash_password("finance-test-123")
        team.name = "Tabajara FC"
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
                page.get_by_label("Senha", exact=True).fill("finance-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()
                return page

            def visible(page, label):
                # The redesign separates labels, amounts and badges; verify the same values.
                if label.startswith(("Saldo devedor · ", "Saldo atual · ")):
                    return page.get_by_label(label.replace(" · ", ": "), exact=True)
                if label.startswith("02/2026 · "):
                    expect(page.get_by_text("Jogador · 02/2026", exact=True)).to_be_visible()
                    label = label.split(" · ")[1]
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
                    page.screenshot(path=str(artifacts / f"finance-{name}-{width}.png"))

            owner_page = login("owner-finance@example.com")
            button(owner_page, "Financeiro").click()
            expect(visible(owner_page, "Nenhuma mensalidade encontrada")).to_be_visible()
            button(owner_page, "Configurar mensalidade").click()
            owner_page.get_by_label("Valor da mensalidade (R$)", exact=True).fill("30,00")
            owner_page.get_by_label("Dia de vencimento", exact=True).fill("10")
            owner_page.get_by_role("radio", name="Ativa", exact=True).click()
            button(owner_page, "Salvar configuração").click()
            owner_page.get_by_label("Competência (MM/AAAA)", exact=True).fill("02/2026")
            button(owner_page, "Gerar mensalidades").click()
            expect(visible(owner_page, "2 cobranças · R$ 60,00")).to_be_visible()
            capture(owner_page, "generation", button(owner_page, "Confirmar geração"))
            button(owner_page, "Confirmar geração").click()
            button(owner_page, f"Abrir cobrança de {player_name}").click()
            expect(visible(owner_page, "Saldo devedor · R$ 30,00")).to_be_visible()
            button(owner_page, "Registrar pagamento").click()
            owner_page.get_by_label("Valor recebido (R$)", exact=True).fill("10,00")
            button(owner_page, "Conferir lançamento").click()
            capture(owner_page, "payment", button(owner_page, "Confirmar lançamento"))
            button(owner_page, "Confirmar lançamento").click()
            expect(visible(owner_page, "Saldo devedor · R$ 20,00")).to_be_visible()
            button(owner_page, "Registrar pagamento").click()
            owner_page.get_by_role("radio", name="Cartão", exact=True).click()
            button(owner_page, "Conferir lançamento").click()
            button(owner_page, "Confirmar lançamento").click()
            expect(visible(owner_page, "02/2026 · PAGA")).to_be_visible()
            expect(visible(owner_page, "Saldo devedor · R$ 0,00")).to_be_visible()
            button(owner_page, "Estornar lançamento").first.click()
            owner_page.get_by_label("Motivo", exact=True).fill("Recebimento lançado por engano")
            button(owner_page, "Confirmar ação").click()
            expect(visible(owner_page, "Saldo devedor · R$ 10,00")).to_be_visible()
            capture(owner_page, "detail", button(owner_page, "Registrar pagamento"))
            button(owner_page, "Caixa").click()
            button(owner_page, "Novo lançamento").click()
            owner_page.get_by_role("radio", name="Despesa", exact=True).click()
            owner_page.get_by_label("Categoria", exact=True).fill("Campo")
            owner_page.get_by_label("Descrição", exact=True).fill("Aluguel do campo")
            owner_page.get_by_label("Valor (R$)", exact=True).fill("50,00")
            button(owner_page, "Conferir lançamento").click()
            button(owner_page, "Confirmar lançamento").click()
            expect(visible(owner_page, "Saldo atual · R$ -30,00")).to_be_visible()
            capture(owner_page, "cash", button(owner_page, "Novo lançamento"))
            owner_page.get_by_role("radio", name="Despesas", exact=True).click()
            button(owner_page, "Filtrar movimentações").click()
            expect(visible(owner_page, "Aluguel do campo")).to_be_visible()
            button(owner_page, "Estornar lançamento").click()
            owner_page.get_by_label("Motivo", exact=True).fill("Correção da despesa")
            button(owner_page, "Confirmar ação").click()
            expect(visible(owner_page, "Saldo atual · R$ 20,00")).to_be_visible()
            button(owner_page, "Mensalidades").click()
            button(owner_page, "Abrir cobrança de Jogador de teste").click()
            button(owner_page, "Isentar mensalidade").click()
            owner_page.get_by_label("Motivo (opcional)", exact=True).fill("Apoio ao time")
            button(owner_page, "Confirmar ação").click()
            expect(visible(owner_page, "02/2026 · ISENTA")).to_be_visible()
            button(owner_page, "Desfazer isenção").click()
            button(owner_page, "Confirmar ação").click()
            button(owner_page, "Cancelar cobrança").click()
            owner_page.get_by_label("Motivo", exact=True).fill("Competência lançada indevidamente")
            button(owner_page, "Confirmar ação").click()
            expect(visible(owner_page, "02/2026 · CANCELADA")).to_be_visible()
            player_page = login("player-finance@example.com")
            button(player_page, "Financeiro").click()
            expect(visible(player_page, "Minhas mensalidades")).to_be_visible()
            expect(button(player_page, "Caixa")).to_have_count(0)
            expect(button(player_page, "Gerar mensalidades")).to_have_count(0)
            expect(button(player_page, "Abrir cobrança de Jogador de teste")).to_have_count(0)
            button(player_page, f"Abrir cobrança de {player_name}").click()
            expect(visible(player_page, "Saldo devedor · R$ 10,00")).to_be_visible()
            expect(button(player_page, "Estornar lançamento")).to_have_count(0)
            expect(button(player_page, "Registrar pagamento")).to_have_count(0)
            capture(player_page, "player", visible(player_page, "Saldo devedor · R$ 10,00"))
            player_page.reload()
            button(player_page, "Financeiro").click()
            button(player_page, f"Abrir cobrança de {player_name}").click()
            expect(visible(player_page, "Saldo devedor · R$ 10,00")).to_be_visible()
            expect(player_page.get_by_role("tab")).to_have_count(4)
            assert bundles and all(status == 200 for status in bundles)
            assert not errors, errors
            for context in contexts:
                context.unroute_all(behavior="wait")
                context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
