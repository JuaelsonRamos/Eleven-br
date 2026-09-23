"""Real Web upload flows; API, storage and database are isolated from development."""

import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Engine, text

from app.infrastructure.images import LocalImageStorage
from tests.conftest import ROOT
from tests.test_images import picture, storage  # noqa: F401


def test_browser_images_flow(engine: Engine, storage: LocalImageStorage) -> None:  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    with engine.connect() as connection:
        schema = connection.scalar(text("select current_schema()"))
    assert schema.startswith("test_") and engine.url.database.endswith("_test")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "MEDIA_ROOT": str(storage.root),
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
            raise AssertionError("Test API not ready")
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", headers={"X-Eleven-Client": "native"}
        ) as api:
            ticket = api.post(
                "/v1/auth/register",
                json={
                    "name": "Jogador Imagens",
                    "contact": "images@example.com",
                    "password": "images-test-123",
                    "password_confirmation": "images-test-123",
                },
            ).json()
            verified = api.post(
                "/v1/auth/verify",
                json={
                    "challenge_token": ticket["challenge_token"],
                    "code": ticket["development_code"],
                },
            ).json()
            api.headers["Authorization"] = f"Bearer {verified['access_token']}"
            team = api.post(
                "/v1/teams",
                json={
                    "name": "Tabajara FC",
                    "city": "Vitória",
                    "state": "ES",
                    "modalities": ["society"],
                },
            ).json()
            team_path = f"/v1/teams/{team['id']}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width": 390, "height": 844})
                errors = []
                fail_crest = False

                def isolated(route):
                    source = urlsplit(route.request.url)
                    if fail_crest and source.path.endswith("/crest"):
                        route.fulfill(
                            status=503,
                            json={"detail": "Armazenamento temporariamente indisponível."},
                        )
                        return
                    route.fulfill(
                        response=route.fetch(
                            url=f"http://127.0.0.1:{port}{source.path}"
                            + (f"?{source.query}" if source.query else "")
                        )
                    )

                context.route("**/v1/**", isolated)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
                page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)
                page.get_by_label("Telefone ou e-mail", exact=True).fill("images@example.com")
                page.get_by_label("Senha", exact=True).fill("images-test-123")
                page.get_by_role("button", name="Entrar", exact=True).click()
                page.get_by_role("tab", name="Mais", exact=True).click()
                page.get_by_role("button", name="Perfil", exact=True).click()

                def active_text(value):
                    return page.get_by_text(value, exact=True).and_(
                        page.locator(':not([aria-hidden="true"] *)')
                    )

                def choose(kind, data, mime="image/jpeg", name="image.jpg"):
                    with page.expect_file_chooser() as pending:
                        page.get_by_role("button", name=f"Alterar {kind}", exact=True).click()
                    pending.value.set_files({"name": name, "mimeType": mime, "buffer": data})

                def saved_photo():
                    with page.expect_response(
                        lambda response: (
                            urlsplit(response.url).path == "/v1/me/photo"
                            and response.request.method == "POST"
                        )
                    ) as pending:
                        page.get_by_role("button", name="Salvar foto", exact=True).click()
                    response = pending.value
                    assert response.status == 200
                    assert response.request.headers["content-type"].startswith(
                        "multipart/form-data;"
                    )
                    reference = response.json()["photo_url"]
                    assert api.get("/v1/me").json()["photo_url"] == reference
                    return reference

                def loaded_image(reference):
                    page.wait_for_function(
                        "reference => [...document.images].some(image => "
                        "image.src.endsWith(reference) && image.complete "
                        "&& image.naturalWidth > 0)",
                        arg=reference,
                    )

                choose("foto", picture())
                expect(active_text("Confira a prévia e salve para confirmar.")).to_be_visible()
                assert api.get("/v1/me").json()["photo_url"] is None
                first = saved_photo()
                loaded_image(first)
                page.reload(wait_until="domcontentloaded")
                page.get_by_role("tab", name="Mais", exact=True).click()
                page.get_by_role("button", name="Perfil", exact=True).click()
                loaded_image(first)
                choose("foto", picture("PNG", alpha=True), "image/png", "photo.png")
                second = saved_photo()
                assert second != first and api.get(first).status_code == 404
                loaded_image(second)
                choose("foto", b"<script>bad</script>", "image/png", "fake.png")
                page.get_by_role("button", name="Salvar foto", exact=True).click()
                expect(
                    active_text("Arquivo inválido. Selecione uma imagem JPEG, PNG ou WebP válida.")
                ).to_be_visible()
                assert api.get("/v1/me").json()["photo_url"] == second
                page.get_by_role("button", name="Desfazer alteração de foto", exact=True).click()
                choose("foto", picture() + b"x" * (5 * 1024 * 1024))
                expect(active_text("A imagem deve ter no máximo 5 MB.")).to_be_visible()
                assert api.get("/v1/me").json()["photo_url"] == second
                page.get_by_role("button", name="Remover foto", exact=True).click()
                page.get_by_role("button", name="Salvar foto", exact=True).click()
                expect(active_text("Foto removida.")).to_be_visible()
                assert (
                    api.get("/v1/me").json()["photo_url"] is None
                    and api.get(second).status_code == 404
                )

                def open_team():
                    page.get_by_role("tab", name="Mais", exact=True).click()
                    page.get_by_role("button", name="Meus Times / Trocar time", exact=True).click()
                    page.get_by_role("button", name="Abrir Tabajara FC", exact=True).click()
                    page.get_by_role("button", name="Perfil do time", exact=True).click()

                open_team()
                page.get_by_role("button", name="Editar time", exact=True).click()
                choose("escudo", picture("PNG", (600, 900), alpha=True), "image/png", "crest.png")
                page.get_by_role("button", name="Salvar alterações", exact=True).click()
                expect(page.get_by_role("button", name="Editar time", exact=True)).to_be_visible()
                first_crest = api.get(team_path).json()["crest_url"]
                assert first_crest
                loaded_image(first_crest)
                page.reload(wait_until="domcontentloaded")
                open_team()
                loaded_image(first_crest)
                page.get_by_role("button", name="Editar time", exact=True).click()
                choose("escudo", picture("WEBP"), "image/webp", "crest.webp")
                page.get_by_role("button", name="Salvar alterações", exact=True).click()
                expect(page.get_by_role("button", name="Editar time", exact=True)).to_be_visible()
                second_crest = api.get(team_path).json()["crest_url"]
                assert second_crest != first_crest and api.get(first_crest).status_code == 404
                loaded_image(second_crest)
                page.screenshot(
                    path=str(ROOT / ".local" / "team-crest-mobile.png"), animations="disabled"
                )
                page.get_by_role("button", name="Editar time", exact=True).click()
                page.get_by_role("button", name="Remover escudo", exact=True).click()
                page.get_by_role("button", name="Salvar alterações", exact=True).click()
                expect(page.get_by_role("button", name="Editar time", exact=True)).to_be_visible()
                assert api.get(team_path).json()["crest_url"] is None
                assert api.get(second_crest).status_code == 404

                # Optional crest during creation; retrying the upload must not duplicate a team.
                page.get_by_role("button", name="Voltar para meus times", exact=True).click()
                page.get_by_role("button", name="Criar time", exact=True).click()
                page.get_by_label("Nome do time", exact=True).fill("Time com escudo")
                page.get_by_label("Cidade", exact=True).fill("Vitória")
                page.get_by_role("button", name="UF", exact=True).click()
                page.get_by_label("Pesquisar UF", exact=True).fill("ES")
                page.get_by_role("button", name="Espírito Santo (ES)", exact=True).click()
                expect(page.get_by_label("Pesquisar UF", exact=True)).to_have_count(0)
                page.get_by_role("checkbox", name="Society / Fut7", exact=True).click()
                choose("escudo", picture())
                fail_crest = True
                page.get_by_role("button", name="Criar time", exact=True).click()
                expect(page.get_by_role("alert")).to_contain_text("Time salvo.")
                assert len(api.get("/v1/teams").json()) == 2
                fail_crest = False
                page.get_by_role("button", name="Salvar alterações", exact=True).click()
                expect(page.get_by_role("button", name="Editar time", exact=True)).to_be_visible()
                listing = api.get("/v1/teams").json()
                assert len(listing) == 2
                new = next(item for item in listing if item["name"] == "Time com escudo")
                assert new["crest_url"]
                loaded_image(new["crest_url"])
                assert not errors, errors
                context.unroute_all(behavior="wait")
                context.close()
                browser.close()
                print(
                    "PASS: real multipart photo/crest upload, preview, reload, replacement, "
                    "removal, invalid/oversize, creation retry without duplicate; "
                    "isolated DB/storage."
                )
    finally:
        server.terminate()
        server.wait(timeout=15)
