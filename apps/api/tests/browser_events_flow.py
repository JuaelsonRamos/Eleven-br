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
            missing_modalities = False
            event_writes = []
            events_path = f"/v1/teams/{team['id']}/events"

            def isolated(route):
                source = urlsplit(route.request.url)
                response = route.fetch(
                    url=f"http://127.0.0.1:{port}{source.path}"
                    + (f"?{source.query}" if source.query else "")
                )
                if missing_modalities and source.path == "/v1/teams/options":
                    # Exercise unavailable choices without corrupting a real team's modalities.
                    route.fulfill(response=response, json={**response.json(), "modalities": []})
                else:
                    route.fulfill(response=response)

            context.route("**/v1/**", isolated)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    event_writes.append(request)
                    if request.method in {"POST", "PUT"}
                    and urlsplit(request.url).path.startswith(events_path)
                    else None
                ),
            )
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

            def invalid_save(message):
                previous = len(event_writes)
                page.get_by_role("button", name="Salvar evento", exact=True).click()
                expect(page.get_by_role("alert")).to_have_text(message)
                assert len(event_writes) == previous, "Invalid form must not send POST/PUT"

            def create_and_check(title, modality, recurring, until=None):
                with page.expect_response(
                    lambda response: (
                        urlsplit(response.url).path == events_path
                        and response.request.method == "POST"
                    )
                ) as pending:
                    page.get_by_role("button", name="Salvar evento", exact=True).click()
                response = pending.value
                assert response.status == 201
                body = response.request.post_data_json
                assert body["modality"] == modality
                assert body["recurring_weekly"] == recurring and body["recurring_until"] == until
                created = response.json()
                assert created["id"] and created["title"] == title
                assert created["modality"] == modality
                # Real API persistence and the actual Jogos list must both contain the event.
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=owner) as api:
                    assert api.get(f"{events_path}/{created['id']}").json()["title"] == title
                    assert created["id"] in {
                        item["id"] for item in api.get(events_path).json()["items"]
                    }
                page.get_by_role("button", name="Voltar aos jogos", exact=True).click()
                label = f"Abrir {title} • {'/'.join(reversed(created['date'].split('-')))}"
                expect(page.get_by_role("button", name=label, exact=True)).to_be_visible()
                page.get_by_role("button", name=label, exact=True).click()
                return created

            login("owner-events@example.com")
            page.get_by_role("button", name="Criar evento", exact=True).click()
            expect(page.get_by_role("radio", name="Society / Fut7", exact=True)).to_be_checked()
            expect(page.get_by_role("radio", name="Campo", exact=True)).to_have_count(0)
            invalid_save("Informe o título.")
            page.get_by_label("Título do evento", exact=True).fill("Pelada simples")
            invalid_save("Informe a data.")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("31/02/2026")
            invalid_save("Informe uma data válida (DD/MM/AAAA).")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            invalid_save("Informe o horário.")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("25:00")
            invalid_save("Informe um horário válido (HH:MM).")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("08:00")
            invalid_save("Informe o local.")
            page.get_by_label("Local", exact=True).fill("Campo local")
            page.get_by_role("radio", name="Futsal", exact=True).click()
            expect(page.get_by_role("radio", name="Futsal", exact=True)).to_be_checked()
            expect(page.get_by_role("radio", name="Society / Fut7", exact=True)).not_to_be_checked()
            create_and_check("Pelada simples", "futsal", False)

            # No visible/enabled modality must never silently send a hidden default.
            missing_modalities = True
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("tab", name="Jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Sem modalidade")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("08:00")
            page.get_by_label("Local", exact=True).fill("Campo local")
            invalid_save("Selecione uma modalidade.")
            missing_modalities = False
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("tab", name="Jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Pelada de Domingo")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("08:00")
            page.get_by_label("Repetir semanalmente", exact=True).click()
            page.get_by_label("Repetir até (DD/MM/AAAA) — opcional", exact=True).fill("11/10/2026")
            page.get_by_label("Local", exact=True).fill("Arena do bairro")
            create_and_check("Pelada de Domingo", "society", True, "2026-10-11")
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
            expect(page.get_by_role("radio", name="Society / Fut7", exact=True)).to_be_checked()
            page.get_by_label("Título do evento", exact=True).fill("")
            invalid_save("Informe o título.")
            page.get_by_label("Título do evento", exact=True).fill("Pelada de Domingo")
            page.get_by_label("Local", exact=True).fill(" ")
            invalid_save("Informe o local.")
            page.get_by_label("Local", exact=True).fill("Arena nova")
            page.get_by_role("radio", name="Futsal", exact=True).click()
            with page.expect_response(
                lambda response: (
                    urlsplit(response.url).path.startswith(events_path + "/")
                    and response.request.method == "PUT"
                )
            ) as edited:
                page.get_by_role("button", name="Salvar evento", exact=True).click()
            assert edited.value.status == 200
            assert edited.value.request.post_data_json["modality"] == "futsal"
            assert edited.value.json()["modality"] == "futsal"
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
            create_and_check("Amistoso", "society", False)
            expect(visible_text("Adversário: Visitantes")).to_be_visible()
            page.get_by_role("button", name="Voltar aos jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            page.get_by_label("Título do evento", exact=True).fill("Pelada sem fim")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("27/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("10:00")
            page.get_by_label("Local", exact=True).fill("Campo")
            page.get_by_label("Repetir semanalmente", exact=True).click()
            create_and_check("Pelada sem fim", "society", True)
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
            # The same session switches team context; no form asks for a team ID.
            with httpx.Client(base_url=f"http://127.0.0.1:{port}") as api:
                second = api.post(
                    "/v1/teams",
                    headers=owner,
                    json={
                        "name": "Segundo time",
                        "city": "Serra",
                        "state": "ES",
                        "modalities": ["society"],
                    },
                ).json()
                player = api.post(
                    f"/v1/teams/{second['id']}/players",
                    headers=owner,
                    json={"name": "Jogador exclusivo do segundo"},
                )
                assert player.status_code == 201, player.text
            page.get_by_role("tab", name="Início", exact=True).click()
            expect(visible_text("Tabajara FC")).to_be_visible()
            expect(page.get_by_role("tab")).to_have_count(4)
            page.get_by_role("button", name="Elenco", exact=True).click()
            expect(visible_text("Tabajara FC")).to_be_visible()
            expect(visible_text("Jogador dos eventos")).to_be_visible()
            expect(visible_text("Jogador exclusivo do segundo")).not_to_be_visible()
            page.get_by_role("tab", name="Jogos", exact=True).click()
            page.get_by_role("button", name="Criar evento", exact=True).click()
            expect(visible_text("Tabajara FC")).to_be_visible()
            page.get_by_label("Título do evento", exact=True).fill("Rascunho do Tabajara")
            page.get_by_role("tab", name="Início", exact=True).click()
            page.get_by_role("button", name="Trocar time", exact=True).click()
            page.get_by_role("button", name="Abrir Segundo time", exact=True).click()
            expect(visible_text("Segundo time")).to_be_visible()
            expect(visible_text("Tabajara FC")).not_to_be_visible()
            page.get_by_role("tab", name="Elenco", exact=True).click()
            expect(visible_text("Jogador exclusivo do segundo")).to_be_visible()
            expect(visible_text("Jogador dos eventos")).not_to_be_visible()
            page.get_by_role("button", name="Adicionar jogador", exact=True).click()
            expect(visible_text("Segundo time")).to_be_visible()
            page.get_by_role("tab", name="Jogos", exact=True).click()
            expect(visible_text("Segundo time")).to_be_visible()
            expect(page.get_by_role("button", name="Abrir Amistoso", exact=False)).to_have_count(0)
            page.get_by_role("button", name="Criar evento", exact=True).click()
            expect(page.get_by_label("Título do evento", exact=True)).to_have_value("")
            page.get_by_label("Título do evento", exact=True).fill("Jogo do segundo")
            page.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("30/09/2026")
            page.get_by_label("Horário (HH:MM)", exact=True).fill("09:00")
            page.get_by_label("Local", exact=True).fill("Quadra do segundo")
            with page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and urlsplit(response.url).path == f"/v1/teams/{second['id']}/events"
                )
            ) as saved:
                page.get_by_role("button", name="Salvar evento", exact=True).click()
            assert saved.value.status == 201
            assert saved.value.json()["team_id"] == second["id"]
            page.reload(wait_until="domcontentloaded")
            expect(visible_text("Segundo time")).to_be_visible()
            page.get_by_role("tab", name="Jogos", exact=True).click()
            expect(
                page.get_by_role("button", name="Abrir Jogo do segundo", exact=False)
            ).to_be_visible()
            page.get_by_role("tab", name="Início", exact=True).click()
            page.get_by_role("button", name="Trocar time", exact=True).click()
            page.get_by_role("button", name="Abrir Tabajara FC", exact=True).click()
            expect(visible_text("Tabajara FC")).to_be_visible()
            page.get_by_role("tab", name="Jogos", exact=True).click()
            expect(page.get_by_role("button", name="Abrir Amistoso", exact=False)).to_be_visible()
            expect(
                page.get_by_role("button", name="Abrir Jogo do segundo", exact=False)
            ).to_have_count(0)
            page.get_by_role("tab", name="Mais", exact=True).click()
            page.get_by_role("button", name="Perfil", exact=True).click()
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
                "PASS: field validation/no invalid requests, selected modality in POST/PUT, "
                "API persistence/list, finite/endless weekly and one-off events, guests, edit, "
                "cancel event/series, reload and member permissions; isolated DB."
            )
    finally:
        server.terminate()
        server.wait(timeout=15)
