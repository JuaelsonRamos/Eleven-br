"""Prompt 15 real browser regression. All requests target an isolated _test schema."""

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.policies import Plan
from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_join_requests import request
from tests.test_roster import setup_roster
from tests.test_team_profiles import client_for


def test_browser_launch_flow(engine):
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner, team, admin, path = setup_roster(session, Plan.PRO)
        team.name, team.modalities, team.category = (
            "Time Pro isolado",
            ["campo", "society", "futsal"],
            "mixed",
        )
        user = session.get(User, owner.user_id)
        user.email, user.password_hash = "launch@example.com", hash_password("old-password-123")
        owner.display_name = "Presidente Teste"
        session.commit()
        person = admin.post(path, json={"name": "Goleiro Teste"}).json()
        assert (
            admin.put(
                path + f"/{person['membership_id']}/positions",
                json={"positions": ["GOL"], "primary_position": "GOL", "expected_version": 1},
            ).status_code
            == 200
        )
        team_id = team.id
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
            artifacts = Path(__file__).resolve().parents[3] / ".local/prompt15-browser"
            artifacts.mkdir(exist_ok=True)

            def button(label):
                return page.get_by_role("button", name=label, exact=True)

            def visible(label):
                return page.get_by_text(label, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            def capture(name):
                for width in [320, 390, 768, 1280]:
                    page.set_viewport_size({"width": width, "height": 900})
                    page.wait_for_timeout(120)
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
            expect(visible("1 time")).to_be_visible(timeout=120000)
            expect(visible("2 jogadores")).to_be_visible()
            button("Já tenho conta").click()
            button("Esqueci minha senha").click()
            page.get_by_label("E-mail da conta", exact=True).fill("launch@example.com")
            button("Enviar código").click()
            development = page.get_by_text(re.compile("Código de desenvolvimento:"))
            expect(development).to_be_visible()
            code = re.search(r"\d{6}", development.inner_text()).group()
            page.get_by_label("Código de recuperação", exact=True).fill(code)
            page.get_by_label("Nova senha", exact=True).fill("new-password-123")
            page.get_by_label("Confirmar nova senha", exact=True).fill("new-password-123")
            capture("recovery")
            button("Salvar nova senha").click()
            expect(page.get_by_role("heading", name="Senha atualizada", exact=True)).to_be_visible()
            button("Voltar ao login").click()
            page.get_by_label("Telefone ou e-mail", exact=True).fill("launch@example.com")
            page.get_by_label("Senha", exact=True).fill("new-password-123")
            button("Entrar").click()
            page.get_by_role("tab", name="Mais", exact=True).click()
            button("Meus Times / Trocar time").click()
            button("Abrir Time Pro isolado").click()
            button("Escalação").click()
            button("Nova escalação").click()
            page.get_by_label("Nome da escalação", exact=True).fill("Titulares de domingo")
            button("Posição 1 GOL: Selecionar").click()
            button("Goleiro Teste").click()
            button("Posição 11 ATA: Selecionar").click()
            expect(button("Goleiro Teste")).to_have_count(0)
            button("Presidente Teste").click()
            button("Salvar escalação").click()
            expect(visible("Escalação salva.")).to_be_visible()
            capture("campo")
            button("3-5-2").click()
            expect(button("Posição 1 GOL: Goleiro Teste")).to_be_visible()
            button("Society").click()
            capture("society")
            button("Futsal").click()
            expect(page.get_by_role("button", name=re.compile(r"^Posição \d"))).to_have_count(5)
            capture("futsal")
            button("Salvar escalação").click()
            expect(visible("Escalação salva.")).to_be_visible()
            button("Voltar às escalações").click()
            button("Titulares de domingo").click()
            expect(button("Posição 1 GOL: Goleiro Teste")).to_be_visible()
            page.get_by_role("tab", name="Elenco", exact=True).click()
            button("Ver jogador Goleiro Teste").click()
            button("Editar posições").click()
            button("ZAG · Zagueiro").click()
            button("Principal: ZAG").click()
            button("Salvar posições").click()
            expect(visible("Posições atualizadas.")).to_be_visible()
            capture("positions")
            button("Remover do time").click()
            capture("remove")
            button("Confirmar remoção do time").click()
            expect(visible("Jogador removido do time. Histórico preservado.")).to_be_visible()
            expect(button("Ver jogador Goleiro Teste")).to_have_count(0)
            with Session(engine) as session:
                from app.infrastructure.models import Team

                newcomer = make_player(session)
                newcomer.display_name = "Retorno Teste"
                requester = client_for(session, newcomer)
                request(requester, session.get(Team, team_id))
            button("Solicitações de entrada").click()
            button("Analisar Retorno Teste").click()
            expect(visible("Jogadores removidos · aprovar retorno")).to_be_visible()
            page.get_by_role("radio", name="Vincular a Goleiro Teste", exact=True).click()
            button("Aprovar").click()
            button("Confirmar aprovação").click()
            expect(visible("Solicitação aprovada. Histórico preservado.")).to_be_visible()
            with Session(engine) as session:
                from app.infrastructure.models import Team

                session.get(Team, team_id).plan = Plan.FREE
                session.commit()
            page.get_by_role("tab", name="Início", exact=True).click()
            button("Escalação").click()
            expect(visible("Escalação é um recurso ELEVEN BR PRO.")).to_be_visible()
            button("Conhecer o Pro").click()
            capture("free")
            assert not errors, errors
            page.wait_for_load_state("networkidle")
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
