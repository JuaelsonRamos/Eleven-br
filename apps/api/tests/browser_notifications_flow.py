"""Opt-in browser flow, isolated API/database; never writes development team data."""

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
from tests.test_events import setup_events
from tests.test_finance import generate, pay, payment
from tests.test_join_requests import request
from tests.test_team_profiles import client_for


def test_browser_notifications_flow(engine: Engine) -> None:
    from playwright.sync_api import expect, sync_playwright

    with Session(engine) as session:
        owner, team_a, admin_a, _ = setup_events(session)
        _, team_b, admin_b, events_b = setup_events(session)
        team_a.name, team_b.name = "Time A da conta", "Time B dos amigos"
        add_member(session, team_id=team_b.id, player_id=owner.id)
        user = session.get(User, owner.user_id)
        user.email, user.password_hash = (
            "notifications@example.com",
            hash_password("notifications-test-123"),
        )
        session.commit()
        # Capture IDs before contexts create simultaneous, separate API sessions.
        team_b_id = str(team_b.id)
        with engine.connect() as connection:
            schema = connection.scalar(text("select current_schema()"))
        assert (
            schema and schema.startswith("test_") and (engine.url.database or "").endswith("_test")
        )
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
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Isolated API did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width": 390, "height": 900})
                errors, bundles = [], []
                pending_routes, closing = 0, False

                def isolated(route):
                    nonlocal pending_routes
                    if closing:
                        route.abort()
                        return
                    pending_routes += 1
                    try:
                        url = urlsplit(route.request.url)
                        route.fulfill(
                            response=route.fetch(
                                url=f"http://127.0.0.1:{port}{url.path}"
                                + (f"?{url.query}" if url.query else "")
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

                def button(label):
                    return page.get_by_role("button", name=label, exact=True)

                def visible(label):
                    return page.get_by_text(label, exact=True).and_(
                        page.locator(':not([aria-hidden="true"] *)')
                    )

                def central():
                    page.get_by_role("tab", name="Mais", exact=True).click()
                    button("Notificações").click()
                    expect(
                        page.get_by_role("heading", name="Notificações", exact=True)
                    ).to_be_visible()

                artifacts = Path(__file__).resolve().parents[3] / ".local"

                def capture(name, locator):
                    for width in [320, 390, 768, 1280]:
                        page.set_viewport_size({"width": width, "height": 900})
                        locator.scroll_into_view_if_needed()
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        assert not page.evaluate("""() => [...document.querySelectorAll(
                            '[role="button"], [role="tab"], [dir="auto"]')]
                            .filter(el => !el.closest('[aria-hidden="true"]')).filter(el => {
                              const r = el.getBoundingClientRect();
                              return r.width && r.height && r.bottom > 0 && r.top < innerHeight
                                && (r.left < -1 || r.right > innerWidth + 1);
                            }).map(el => el.textContent)""")
                        page.screenshot(path=str(artifacts / f"notifications-{name}-{width}.png"))

                html = page.goto(
                    "http://localhost:8081", wait_until="domcontentloaded", timeout=120000
                )
                assert html and html.status == 200
                button("Já tenho conta").click(timeout=120000)
                page.get_by_label("Telefone ou e-mail", exact=True).fill(
                    "notifications@example.com"
                )
                page.get_by_label("Senha", exact=True).fill("notifications-test-123")
                button("Entrar").click()
                expect(visible("Time A da conta")).to_be_visible()
                central()
                expect(visible("Você está em dia.")).to_be_visible()
                capture("empty", visible("Você está em dia."))
                created = admin_b.post(
                    events_b,
                    json={
                        "modality": "campo",
                        "kind": "PELADA",
                        "title": "Pelada dos amigos",
                        "date": (date.today() + timedelta(days=1)).isoformat(),
                        "time": "08:00",
                        "location": "Arena do bairro",
                    },
                )
                assert created.status_code == 201
                page.get_by_role("tab", name="Mais", exact=True).click()
                expect(visible("1 não lidas")).to_be_visible()
                button("Notificações").click()
                notice = page.get_by_role("button", name="Nova pelada, não lida.", exact=False)
                expect(notice).to_be_visible()
                capture("inbox", notice)
                notice.click()
                expect(visible("Pelada dos amigos")).to_be_visible()
                expect(visible("Time B dos amigos")).to_be_visible()
                expect(visible("Sua resposta: Pendente")).to_be_visible()
                assert admin_a.get("/v1/me/notifications/unread-count").json() == {"count": 0}
                central()
                expect(page.get_by_role("button", name="Nova pelada.", exact=False)).to_be_visible()
                expect(visible("Não lida")).to_have_count(0)
                finance = f"/v1/teams/{team_b_id}/finance"
                assert (
                    admin_b.put(
                        finance + "/settings",
                        json={
                            "amount": "30.00",
                            "due_day": 10,
                            "active": True,
                            "expected_version": 0,
                        },
                    ).status_code
                    == 200
                )
                dues = generate(admin_b, finance)
                own = next(
                    row
                    for row in dues
                    if row["membership_id"]
                    == str(
                        session.scalar(
                            text(
                                "SELECT id FROM team_memberships "
                                "WHERE team_id=:team AND player_id=:player"
                            ),
                            {"team": team_b.id, "player": owner.id},
                        )
                    )
                )
                pay(admin_b, finance, own, payment(own, "15.00"))
                central()
                expect(visible("2 não lidas")).to_be_visible()
                page.get_by_role(
                    "button", name="Pagamento registrado, não lida.", exact=False
                ).click()
                expect(page.get_by_label("Saldo devedor: R$ 15,00", exact=True)).to_be_visible()
                expect(visible("Time B dos amigos")).to_be_visible()
                capture("charge", visible("Time B dos amigos"))
                central()
                button("Marcar todas como lidas").click()
                expect(button("Marcar todas como lidas")).to_have_count(0)
                assert admin_a.get("/v1/me/notifications/unread-count").json() == {"count": 0}
                # An administrative notification switches back to A and opens its requests.
                applicant = make_player(session)
                requester = client_for(session, applicant)
                request(requester, team_a)
                central()
                page.get_by_role(
                    "button", name="Nova solicitação de entrada, não lida.", exact=False
                ).click()
                expect(visible("Time A da conta")).to_be_visible()
                expect(visible("Solicitações de entrada")).to_be_visible()
                expect(page.get_by_role("tab")).to_have_count(4)
                assert bundles and all(status == 200 for status in bundles)
                assert not errors, errors
                page.wait_for_load_state("networkidle")
                closing = True
                deadline = time.monotonic() + 10
                while pending_routes and time.monotonic() < deadline:
                    page.wait_for_timeout(20)
                assert pending_routes == 0
                context.close()
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=15)
