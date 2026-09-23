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


def test_browser_formations_flow(engine: Engine) -> None:
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
                        "password": "formation-test-123",
                        "password_confirmation": "formation-test-123",
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
            event_response = api.post(
                f"/v1/teams/{team['id']}/events",
                headers=owner,
                json={
                    "modality": "society",
                    "kind": "PELADA",
                    "title": "Pelada do sorteio",
                    "date": "2026-09-27",
                    "time": "08:00",
                    "location": "Campo do bairro",
                },
            )
            assert event_response.status_code == 201
            event = event_response.json()
            event_path = f"/v1/teams/{team['id']}/events/{event['id']}"
            for headers in [owner, member]:
                assert (
                    api.put(
                        event_path + "/attendance", headers=headers, json={"response": "VOU"}
                    ).status_code
                    == 200
                )
            for name in ["Bruno", "Carlos", "Diego", "Eduardo", "Fabio"]:
                assert (
                    api.post(event_path + "/guests", headers=owner, json={"name": name}).status_code
                    == 201
                )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            errors = []
            writes = []

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
            page.on(
                "request",
                lambda request: (
                    writes.append(request.url) if request.url.endswith("/formation/draw") else None
                ),
            )
            page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
            page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)

            def login(email):
                page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
                page.get_by_label("Senha", exact=True).fill("formation-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()

            def open_formation(label="Montar times"):
                page.get_by_role("tab", name="Jogos", exact=True).click()
                page.get_by_role(
                    "button", name="Abrir Pelada do sorteio • 27/09/2026", exact=True
                ).click()
                page.get_by_role("button", name=label, exact=True).click()

            def visible_text(value):
                return page.get_by_text(value, exact=True).and_(
                    page.locator(':not([aria-hidden="true"] *)')
                )

            def stored():
                return httpx.get(
                    f"http://127.0.0.1:{port}{event_path}/formation", headers=owner
                ).json()

            login("owner-events@example.com")
            open_formation()
            expect(visible_text("Tabajara FC")).to_be_visible()
            expect(visible_text("Participantes — 7")).to_be_visible()
            page.get_by_role("checkbox", name="Participa: Convidado: Eduardo", exact=True).click()
            for name in ["Presidente dos eventos", "Convidado: Bruno", "Convidado: Carlos"]:
                page.get_by_role("checkbox", name=f"Goleiro: {name}", exact=True).click()
            page.get_by_role("button", name="Mais times", exact=True).click()
            expect(visible_text("Número de times: 3")).to_be_visible()
            expect(visible_text("Time 1 — 2 jogadores")).to_be_visible()
            with page.expect_response(
                lambda r: r.request.method == "POST" and r.url.endswith("/formation/draw")
            ) as result:
                page.get_by_role("button", name="Sortear", exact=True).click()
            assert result.value.status == 200
            first = result.value.json()["formation"]
            assert len(first["excluded"]) == 1
            assert all(
                len(s["participants"]) == 2 and sum(p["goalkeeper"] for p in s["participants"]) == 1
                for s in first["squads"]
            )
            expect(visible_text("Times da pelada")).to_be_visible()
            artifacts = Path(__file__).resolve().parents[3] / ".local"
            artifacts.mkdir(exist_ok=True)
            page.screenshot(
                path=str(artifacts / "formation-mobile.png"), full_page=True, animations="disabled"
            )
            page.get_by_role("button", name="Mover Bruno", exact=True).click()
            destination = next(
                s for s in first["squads"] if all(p["name"] != "Bruno" for p in s["participants"])
            )
            page.get_by_role("button", name=f"Mover para {destination['name']}", exact=True).click()
            expect(
                page.get_by_role("button", name=f"Mover para {destination['name']}", exact=True)
            ).to_have_count(0)
            moved = stored()["formation"]
            assert moved["version"] == first["version"] + 1
            assert any(
                p["name"] == "Bruno"
                for s in moved["squads"]
                if s["id"] == destination["id"]
                for p in s["participants"]
            )
            page.reload(wait_until="domcontentloaded")
            open_formation()
            expect(visible_text("Times da pelada")).to_be_visible()
            assert stored()["formation"] == moved
            page.get_by_role("button", name="Refazer sorteio", exact=True).click()
            page.get_by_role("button", name="Sortear", exact=True).click()
            expect(
                visible_text(
                    "Já existe uma formação para esta pelada. Deseja substituir o sorteio atual?"
                )
            ).to_be_visible()
            assert len(writes) == 1
            page.get_by_role("button", name="Manter sorteio atual", exact=True).click()
            assert stored()["formation"] == moved
            page.get_by_role("button", name="Refazer sorteio", exact=True).click()
            page.get_by_role("button", name="Sortear", exact=True).click()
            page.get_by_role("button", name="Confirmar novo sorteio", exact=True).click()
            expect(visible_text("Times da pelada")).to_be_visible()
            assert len(writes) == 2
            stable = stored()["formation"]
            with httpx.Client(base_url=f"http://127.0.0.1:{port}") as api:
                assert (
                    api.post(
                        event_path + "/guests", headers=owner, json={"name": "Novo convidado"}
                    ).status_code
                    == 201
                )
                bruno = next(
                    p["guest_id"]
                    for s in stable["squads"]
                    for p in s["participants"]
                    if p["name"] == "Bruno"
                )
                assert (
                    api.post(event_path + f"/guests/{bruno}/remove", headers=owner).status_code
                    == 200
                )
            page.get_by_role("button", name="Atualizar participantes", exact=True).click()
            expect(
                visible_text("A lista de participantes mudou desde o último sorteio.")
            ).to_be_visible()
            expect(page.get_by_role("button", name="Mover Bruno", exact=True)).to_be_visible()
            assert stored()["formation"] == stable
            # Exercise compact controls and actual API results at mobile/desktop widths.
            for total, teams_count, goalkeeper_count in [
                (2, 2, 0),
                (12, 2, 2),
                (13, 3, 1),
                (13, 4, 0),
            ]:
                title = f"Visual {total} participantes {teams_count} times"
                with httpx.Client(base_url=f"http://127.0.0.1:{port}") as api:
                    scenario = api.post(
                        f"/v1/teams/{team['id']}/events",
                        headers=owner,
                        json={
                            "modality": "society",
                            "kind": "PELADA",
                            "title": title,
                            "date": "2026-09-27",
                            "time": "08:00",
                            "location": "Campo do teste visual",
                        },
                    ).json()
                    scenario_path = f"/v1/teams/{team['id']}/events/{scenario['id']}"
                    for headers in [owner, member]:
                        assert (
                            api.put(
                                scenario_path + "/attendance",
                                headers=headers,
                                json={"response": "VOU"},
                            ).status_code
                            == 200
                        )
                    for index in range(total - 2):
                        assert (
                            api.post(
                                scenario_path + "/guests",
                                headers=owner,
                                json={"name": f"Convidado visual {index + 1}"},
                            ).status_code
                            == 201
                        )
                page.get_by_role("tab", name="Início", exact=True).click()
                page.get_by_role("tab", name="Jogos", exact=True).click()
                page.get_by_role("button", name=f"Abrir {title} • 27/09/2026", exact=True).click()
                page.get_by_role("button", name="Montar times", exact=True).click()
                expect(visible_text(f"Participantes — {total}")).to_be_visible()
                page.set_viewport_size({"width": 320, "height": 844})
                rows = page.get_by_test_id("formation-candidate")
                expect(rows).to_have_count(total)
                for row in rows.all():
                    boxes = [row.get_by_role("checkbox").nth(i).bounding_box() for i in range(2)]
                    assert all(
                        b
                        and b["width"] >= 48
                        and b["height"] >= 48
                        and b["x"] >= 0
                        and b["x"] + b["width"] <= 320
                        for b in boxes
                    )
                    assert abs(boxes[0]["y"] - boxes[1]["y"]) < 1
                for name in ["Presidente dos eventos", "Jogador dos eventos"][:goalkeeper_count]:
                    page.get_by_role("checkbox", name=f"Goleiro: {name}", exact=True).click()
                keeper_text = "goleiro" if goalkeeper_count == 1 else "goleiros"
                expect(
                    visible_text(
                        f"{goalkeeper_count} {keeper_text} • "
                        f"{total - goalkeeper_count} jogadores de linha"
                    )
                ).to_be_visible()
                if total == 12:
                    # Removing a goalkeeper updates counters, without losing the saved choice.
                    toggle = page.get_by_role(
                        "checkbox", name="Participa: Presidente dos eventos", exact=True
                    )
                    toggle.click()
                    expect(visible_text("1 goleiro • 10 jogadores de linha")).to_be_visible()
                    toggle.click()
                    expect(visible_text("2 goleiros • 10 jogadores de linha")).to_be_visible()
                    page.screenshot(
                        path=str(artifacts / "formation-preparation-320.png"), animations="disabled"
                    )
                for _ in range(teams_count - 2):
                    page.get_by_role("button", name="Mais times", exact=True).click()
                for index in range(teams_count):
                    size = total // teams_count + (index < total % teams_count)
                    expect(
                        visible_text(
                            f"Time {index + 1} — {size} "
                            + ("jogador" if size == 1 else "jogadores")
                        )
                    ).to_be_visible()
                with page.expect_response(
                    lambda r: r.request.method == "POST" and r.url.endswith("/formation/draw")
                ) as drawn:
                    page.get_by_role("button", name="Sortear", exact=True).click()
                assert drawn.value.status == 200
                squads = drawn.value.json()["formation"]["squads"]
                assert [len(s["participants"]) for s in squads] == [
                    total // teams_count + (i < total % teams_count) for i in range(teams_count)
                ]
                assert (
                    sum(p["goalkeeper"] for s in squads for p in s["participants"])
                    == goalkeeper_count
                )
                expect(visible_text("Times da pelada")).to_be_visible()
                first_card = page.get_by_test_id("formation-squad-1")
                second_card = page.get_by_test_id("formation-squad-2")
                a, b = first_card.bounding_box(), second_card.bounding_box()
                assert b["y"] >= a["y"] + a["height"]
                assert a["x"] >= 0 and a["x"] + a["width"] <= 320
                if total == 12:
                    page.screenshot(
                        path=str(artifacts / "formation-result-320.png"), animations="disabled"
                    )
                    page.set_viewport_size({"width": 1280, "height": 900})
                    page.wait_for_function("""() => {
                        const a=document.querySelector('[data-testid="formation-squad-1"]')
                            ?.getBoundingClientRect();
                        const b=document.querySelector('[data-testid="formation-squad-2"]')
                            ?.getBoundingClientRect();
                        return a && b && Math.abs(a.y-b.y)<1 && b.x>a.x;
                    }""")
                    page.screenshot(
                        path=str(artifacts / "formation-result-desktop.png"), animations="disabled"
                    )
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.wait_for_function("""() => {
                        const a=document.querySelector('[data-testid="formation-squad-1"]')
                            ?.getBoundingClientRect();
                        const b=document.querySelector('[data-testid="formation-squad-2"]')
                            ?.getBoundingClientRect();
                        return a && b && b.y>=a.bottom;
                    }""")
                current_squad = next(
                    s
                    for s in squads
                    if any(p["name"] == "Presidente dos eventos" for p in s["participants"])
                )
                page.get_by_role("button", name="Mover Presidente dos eventos", exact=True).click()
                expect(
                    page.get_by_role(
                        "button", name=f"Mover para {current_squad['name']}", exact=True
                    )
                ).to_have_count(0)
                expect(
                    page.get_by_role("button", name="Mover para Time", exact=False)
                ).to_have_count(teams_count - 1)
            page.get_by_role("tab", name="Mais", exact=True).click()
            page.get_by_role("button", name="Perfil", exact=True).click()
            page.get_by_role("button", name="Sair da conta", exact=True).click()
            login("member-events@example.com")
            open_formation("Ver times da pelada")
            expect(visible_text("Times da pelada")).to_be_visible()
            expect(page.get_by_role("button", name="Refazer sorteio", exact=True)).to_have_count(0)
            expect(page.get_by_role("button", name="Mover Bruno", exact=True)).to_have_count(0)
            assert not errors, errors
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
