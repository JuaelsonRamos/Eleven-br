"""Redesign regression: real next event, responsive navigation and filters beyond page 1."""

import os
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.application.teams import add_member
from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_finance import generate, pay
from tests.test_roster import setup_roster


def test_browser_redesign_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner, team, client, _ = setup_roster(session)
        player = make_player(session)
        player.display_name = (
            "João Antônio de Albuquerque e Vasconcelos dos Santos Pereira da Silva"
        )
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
        events_path = f"/v1/teams/{team.id}/events"
        future = {
            "modality": team.modalities[0],
            "kind": "PELADA",
            "title": "Próxima pelada real",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "time": "10:00",
            "location": "Arena do bairro com um nome muito longo para validar a tela pequena",
        }
        created = client.post(events_path, json=future)
        assert created.status_code == 201
        event_id = created.json()["id"]
        assert (
            client.put(
                events_path + f"/{event_id}/attendance", json={"response": "VOU"}
            ).status_code
            == 200
        )
        cancelled = client.post(
            events_path, json={**future, "title": "Cancelada não deve aparecer", "time": "09:00"}
        ).json()
        assert client.post(events_path + f"/{cancelled['id']}/cancel").status_code == 200
        assert (
            client.post(
                events_path,
                json={
                    **future,
                    "title": "Evento passado",
                    "date": (date.today() - timedelta(days=1)).isoformat(),
                },
            ).status_code
            == 201
        )
        finance_path = f"/v1/teams/{team.id}/finance"
        assert (
            client.put(
                finance_path + "/settings",
                json={"amount": "30.00", "due_day": 10, "active": True, "expected_version": 0},
            ).status_code
            == 200
        )
        oldest = generate(client, finance_path, "2024-01-01")
        paid = pay(
            client,
            finance_path,
            next(item for item in oldest if item["name"] == "Jogador de teste"),
        )
        for index in range(1, 26):
            generate(client, finance_path, f"{2024 + index // 12}-{index % 12 + 1:02}-01")
        first = client.get(finance_path + "/dues").json()
        assert first["has_more"] and paid["id"] not in {item["id"] for item in first["items"]}
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
            pending_routes = 0
            closing = False

            def login(email):
                context = browser.new_context(viewport={"width": 390, "height": 900})
                contexts.append(context)

                def isolated(route):
                    nonlocal pending_routes
                    if closing:
                        route.abort()
                        return
                    pending_routes += 1
                    try:
                        source_url = urlsplit(route.request.url)
                        route.fulfill(
                            response=route.fetch(
                                url=f"http://127.0.0.1:{port}{source_url.path}"
                                + (f"?{source_url.query}" if source_url.query else "")
                            )
                        )
                    finally:
                        pending_routes -= 1

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
                    overflow = page.evaluate("""() => [...document.querySelectorAll(
                        'input, textarea, [role="button"], [role="tab"], [dir="auto"]'
                    )].filter(el => !el.closest('[aria-hidden="true"]'))
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width && r.height && r.bottom > 0 && r.top < innerHeight
                            && (r.left < -1 || r.right > innerWidth + 1);
                    }).map(el => el.getAttribute('aria-label') || el.textContent)""")
                    assert not overflow, overflow
                    page.screenshot(path=str(artifacts / f"redesign-{name}-{width}.png"))

            page = login("owner-finance@example.com")
            expect(visible(page, "Próxima pelada real")).to_be_visible()
            expect(visible(page, "1 confirmados")).to_be_visible()
            expect(visible(page, "1 pendentes")).to_be_visible()
            expect(visible(page, "Cancelada não deve aparecer")).to_have_count(0)
            expect(visible(page, "Evento passado")).to_have_count(0)
            capture(page, "home", visible(page, "Início do time"))
            capture(page, "next-event", button(page, "Ver evento"))
            for _ in range(2):
                button(page, "Ver evento").click()
                expect(visible(page, "Sua resposta: Vou")).to_be_visible()
                capture(page, "event", visible(page, "Próxima pelada real"))
                page.get_by_role("tab", name="Início", exact=True).click()
                expect(button(page, "Ver evento")).to_be_visible()
            button(page, "Elenco").click()
            capture(page, "roster", button(page, "Ver jogador Jogador de teste"))
            button(page, "Adicionar jogador").click()
            capture(page, "player-form", page.get_by_label("Nome do jogador", exact=True))
            page.get_by_role("tab", name="Mais", exact=True).click()
            capture(page, "more", button(page, "Perfil"))
            button(page, "Perfil").click()
            capture(page, "profile", button(page, "Sair da conta"))
            page.get_by_role("tab", name="Mais", exact=True).click()
            button(page, "Meus Times / Trocar time").click()
            capture(page, "teams", button(page, "Abrir Tabajara FC"))
            button(page, "Criar time").click()
            capture(page, "team-form", page.get_by_label("Nome do time", exact=True))
            button(page, "UF").click()
            capture(page, "state-dialog", page.get_by_label("Pesquisar UF", exact=True))
            button(page, "Fechar lista de UFs").click()
            button(page, "Cancelar").click()
            button(page, "Abrir Tabajara FC").click()
            button(page, "Jogos").click()
            capture(page, "games", button(page, "Criar evento"))
            button(page, "Criar evento").click()
            capture(page, "event-form", page.get_by_label("Título do evento", exact=True))
            page.get_by_role("tab", name="Início", exact=True).click()
            button(page, "Financeiro").click()
            button(page, "Pagas").click()
            paid_row = button(page, "Abrir cobrança de Jogador de teste")
            expect(paid_row).to_have_count(1)
            expect(paid_row).to_contain_text("01/2024")
            capture(page, "dues", paid_row)
            button(page, "Pendentes").click()
            expect(visible(page, "Nenhuma mensalidade encontrada")).to_be_visible()
            button(page, "Atrasadas").click()
            expect(page.get_by_role("button", name="Abrir cobrança de", exact=False)).to_have_count(
                51
            )
            button(page, "Todas").click()
            expect(page.get_by_role("button", name="Abrir cobrança de", exact=False)).to_have_count(
                50
            )
            page.get_by_label("Competência (MM/AAAA)", exact=True).fill("01/2024")
            button(page, "Consultar competência").click()
            expect(page.get_by_role("button", name="Abrir cobrança de", exact=False)).to_have_count(
                2
            )
            button(page, "Próxima competência").click()
            expect(page.get_by_label("Competência (MM/AAAA)", exact=True)).to_have_value("02/2024")
            expect(visible(page, "Competência consultada: 02/2024")).to_be_visible()
            page.get_by_role("tab", name="Início", exact=True).click()
            button(page, "Ver evento").click()
            button(page, "Cancelar evento").click()
            button(page, "Confirmar cancelamento").click()
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(visible(page, "Agenda livre por enquanto")).to_be_visible()
            expect(page.get_by_role("tab")).to_have_count(4)
            assert bundles and all(status == 200 for status in bundles)
            assert not errors, errors
            page.wait_for_load_state("networkidle")
            # Drain proxy handlers before closing. unroute_all can race a completed
            # fulfill while hidden screens finish context revalidation requests.
            closing = True
            deadline = time.monotonic() + 10
            while pending_routes and time.monotonic() < deadline:
                page.wait_for_timeout(20)
            assert pending_routes == 0
            for context in contexts:
                context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
