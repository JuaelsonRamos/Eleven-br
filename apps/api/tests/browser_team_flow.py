"""Opt-in Chromium integration against Expo :8081 and an isolated PostgreSQL schema.

Run from apps/api: uv run --with playwright pytest tests/browser_team_flow.py -q -s
Requires the Playwright Chromium installation and an existing Expo Web server.
Browser API requests are forwarded to a temporary test server, NEVER the dev DB.
"""

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.infrastructure.models import Team, TeamMembership


def test_browser_team_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with engine.connect() as connection:
        schema = connection.scalar(text("select current_schema()"))
    assert schema and schema.startswith("test_")
    assert (engine.url.database or "").endswith("_test")
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
            errors: list[str] = []
            bundles: list[int] = []

            def context_for(state=None):
                context = browser.new_context(
                    storage_state=state, viewport={"width": 390, "height": 844}
                )

                def isolated(route):
                    source = urlsplit(route.request.url)
                    target = f"http://127.0.0.1:{port}{source.path}"
                    if source.query:
                        target += f"?{source.query}"
                    response = route.fetch(url=target)
                    route.fulfill(response=response)

                # Intercept all application API calls, even if its configured host changes.
                context.route("**/v1/**", isolated)
                return context

            def open_page(context):
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: (
                        bundles.append(response.status) if ".bundle?" in response.url else None
                    ),
                )
                page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
                return page

            context = context_for()
            page = open_page(context)

            def active_text(value):
                return page.get_by_text(value, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            page.get_by_role("button", name="Criar minha conta", exact=True).click(timeout=120000)
            page.get_by_label("Nome", exact=True).fill("Jogador teste isolado")
            page.get_by_label("E-mail", exact=True).fill("team-browser@example.com")
            page.get_by_label("Senha", exact=True).fill("futebol-teste-123")
            page.get_by_label("Confirmar senha", exact=True).fill("futebol-teste-123")
            page.get_by_role("button", name="Criar minha conta", exact=True).click()
            code_text = page.get_by_text(re.compile("Código de desenvolvimento:")).inner_text()
            code = re.search(r"\d{6}", code_text)
            assert code
            page.get_by_label("Código de 6 dígitos").fill(code.group())
            page.get_by_role("button", name="Confirmar", exact=True).click()
            page.get_by_role("tab", name="Times", exact=True).click()
            expect(active_text("Seu time começa aqui")).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)

            def fill_team(name):
                page.get_by_role("button", name="Criar time", exact=True).click()
                page.get_by_label("Nome do time", exact=True).fill(name)
                page.get_by_label("Cidade", exact=True).fill("Vitória")
                page.get_by_role("button", name="UF", exact=True).click()
                if name == "Tabajara":
                    page.screenshot(
                        path=str(artifacts / "uf-selector-mobile.png"),
                        full_page=True,
                        animations="disabled",
                    )
                search = page.get_by_label("Pesquisar UF", exact=True)
                search.fill("XX")
                expect(page.get_by_text("Nenhum estado encontrado.", exact=True)).to_be_visible()
                search.fill("São")
                expect(
                    page.get_by_role("button", name="São Paulo (SP)", exact=True)
                ).to_be_visible()
                search.fill("sp")
                page.get_by_role("button", name="São Paulo (SP)", exact=True).click()
                page.get_by_role("button", name="UF", exact=True).click()
                search.fill("Esp")
                expect(
                    page.get_by_role("button", name="Espírito Santo (ES)", exact=True)
                ).to_be_visible()
                search.fill("ES")
                page.get_by_role("button", name="Espírito Santo (ES)", exact=True).click()
                expect(search).to_have_count(0)
                # Empty selection must be rejected before any creation request.
                page.get_by_role("button", name="Criar time", exact=True).click()
                expect(
                    active_text("Preencha nome, cidade, UF válida e ao menos uma modalidade.")
                ).to_be_visible()
                page.get_by_role("checkbox", name="Society / Fut7", exact=True).click()
                page.get_by_role("checkbox", name="Futsal", exact=True).click()
                if name == "Tabajara":
                    page.screenshot(
                        path=str(artifacts / "modalities-form-mobile.png"), full_page=True
                    )
                page.get_by_role("button", name="Criar time", exact=True).click()

            fill_team("Tabajara")
            expect(active_text("Time criado. Você é o Presidente!")).to_be_visible()
            expect(active_text("Presidente")).to_be_visible()
            expect(active_text("Society / Fut7 • Futsal")).to_be_visible()
            original_code = page.get_by_text(re.compile("Código do time:")).inner_text()
            page.get_by_role("button", name="Editar time", exact=True).click()
            page.get_by_label("Nome do time", exact=True).fill("Tabajara FC")
            expect(page.get_by_role("checkbox", name="Society / Fut7", exact=True)).to_be_checked()
            expect(page.get_by_role("checkbox", name="Futsal", exact=True)).to_be_checked()
            page.get_by_role("checkbox", name="Campo", exact=True).click()
            page.get_by_role("button", name="Salvar alterações", exact=True).click()
            expect(active_text("Time atualizado.")).to_be_visible()
            expect(active_text("Campo • Society / Fut7 • Futsal")).to_be_visible()
            page.get_by_role("button", name="Editar time", exact=True).click()
            page.get_by_role("checkbox", name="Campo", exact=True).click()
            page.get_by_role("button", name="Salvar alterações", exact=True).click()
            expect(active_text("Society / Fut7 • Futsal")).to_be_visible()
            expect(page.get_by_text(original_code, exact=True).filter(visible=True)).to_be_visible()
            page.get_by_role("button", name="Voltar para meus times", exact=True).click()
            fill_team("Tabajara FC")
            expect(active_text("Encontramos um time parecido.")).to_be_visible()
            page.get_by_role("button", name="Criar mesmo assim", exact=True).click()
            expect(active_text("Time criado. Você é o Presidente!")).to_be_visible()
            assert page.get_by_text(re.compile("Código do time:")).inner_text() != original_code
            page.get_by_role("button", name="Editar time", exact=True).click()
            page.get_by_label("Nome do time", exact=True).fill("Segundo time")
            page.get_by_role("button", name="Salvar alterações", exact=True).click()
            page.get_by_role("button", name="Voltar para meus times", exact=True).click()
            expect(
                page.get_by_role("button", name="Abrir Segundo time", exact=True).filter(
                    visible=True
                )
            ).to_be_visible()
            page.get_by_role("button", name="Abrir Tabajara FC", exact=True).click()
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(active_text("Tabajara FC")).to_be_visible()
            expect(active_text("Segundo time")).not_to_be_visible()
            assert page.get_by_role("tab").count() == 5
            page.screenshot(
                path=str(artifacts / "teams-home-mobile.png"), full_page=True, animations="disabled"
            )

            state = context.storage_state()
            assert len(state["origins"][0]["localStorage"]) == 1
            context.close()
            context = context_for(state)
            page = open_page(context)
            expect(active_text("Tabajara FC")).to_be_visible(timeout=30000)
            page.set_viewport_size({"width": 1280, "height": 900})
            page.get_by_role("tab", name="Times", exact=True).click()
            expect(
                page.get_by_role("button", name="Abrir Segundo time", exact=True).filter(
                    visible=True
                )
            ).to_be_visible()
            page.screenshot(
                path=str(artifacts / "teams-list-desktop.png"),
                full_page=True,
                animations="disabled",
            )
            page.get_by_role("button", name="Abrir Segundo time", exact=True).click()
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(active_text("Segundo time")).to_be_visible()
            page.get_by_role("tab", name="Times", exact=True).click()
            page.get_by_role("button", name="Editar time", exact=True).click()
            page.get_by_label("Nome do time", exact=True).fill("Não aplicar em outro time")
            # Revoke selected membership only in the isolated test schema.
            with Session(engine) as session:
                team = session.scalars(select(Team).where(Team.name == "Segundo time")).one()
                foreign_id = str(team.id)
                membership = session.get(TeamMembership, team.president_membership_id)
                assert membership
                membership.status = "inactive"
                session.commit()
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(active_text("Tabajara FC")).to_be_visible()
            page.get_by_role("tab", name="Times", exact=True).click()
            expect(
                active_text(
                    "O acesso ao time mudou. Confira o time selecionado antes de continuar."
                )
            ).to_be_visible()
            expect(page.get_by_label("Nome do time", exact=True)).to_have_count(0)
            page.get_by_role("tab", name="Início", exact=True).click()
            page.reload(wait_until="domcontentloaded")
            expect(active_text("Tabajara FC")).to_be_visible(timeout=30000)
            expect(active_text("Segundo time")).not_to_be_visible()
            page.get_by_role("tab", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            page.get_by_label("Telefone ou e-mail", exact=True).fill("team-browser@example.com")
            page.get_by_label("Senha", exact=True).fill("futebol-teste-123")
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(active_text("Tabajara FC")).to_be_visible()
            # Another user on the same browser must not inherit the previous team's context.
            page.get_by_role("tab", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", headers={"X-Eleven-Client": "native"}
            ) as api:
                ticket = api.post(
                    "/v1/auth/register",
                    json={
                        "name": "Outro jogador",
                        "contact": "other-browser@example.com",
                        "password": "futebol-teste-123",
                        "password_confirmation": "futebol-teste-123",
                    },
                ).json()
                verified = api.post(
                    "/v1/auth/verify",
                    json={
                        "challenge_token": ticket["challenge_token"],
                        "code": ticket["development_code"],
                    },
                )
                assert verified.status_code == 200
                profile = api.get(
                    "/v1/me", headers={"Authorization": f"Bearer {verified.json()['access_token']}"}
                ).json()
            page.get_by_label("Telefone ou e-mail", exact=True).fill("other-browser@example.com")
            page.get_by_label("Senha", exact=True).fill("futebol-teste-123")
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(active_text("Seu futebol começa aqui.")).to_be_visible()
            expect(active_text("Tabajara FC")).not_to_be_visible()
            # Even a forged local preference grants no access.
            page.evaluate(
                "([key, value]) => localStorage.setItem(key, value)",
                [f"eleven.team.{profile['user_id']}", foreign_id],
            )
            page.reload(wait_until="domcontentloaded")
            expect(active_text("Seu futebol começa aqui.")).to_be_visible()
            assert (
                page.evaluate(
                    "key => localStorage.getItem(key)", f"eleven.team.{profile['user_id']}"
                )
                is None
            )
            assert bundles and all(status == 200 for status in bundles)
            assert not errors, errors
            context.close()
            browser.close()
            print(
                "PASS: Web bundle, create, duplicates, President, edit, two teams, switch, "
                "browser restart, revoked/forged selection, account isolation, logout/login; "
                "isolated DB only."
            )
    finally:
        server.terminate()
        server.wait(timeout=15)
