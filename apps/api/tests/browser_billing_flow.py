"""Real Expo browser, API and PostgreSQL isolated; provider simulated, no dev data writes."""

from pathlib import Path

from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.test_billing import payload, provider, setup, webhook  # noqa: F401


def test_browser_billing_flow(session, provider):  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    owner, team, client, path = setup(session)
    user = session.get(User, owner.user_id)
    user.email, user.password_hash = "billing@example.com", hash_password("browser-password-123")
    team.name = "Time comercial isolado"
    session.commit()
    client.headers.pop("Authorization", None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 900})

        def api(route):
            from urllib.parse import urlsplit

            url = urlsplit(route.request.url)
            response = client.request(
                route.request.method,
                url.path + ("?" + url.query if url.query else ""),
                content=route.request.post_data,
                headers={
                    k: v
                    for k, v in route.request.headers.items()
                    if k not in {"host", "content-length"}
                },
            )
            route.fulfill(
                status=response.status_code, body=response.content, headers=dict(response.headers)
            )

        context.route("**/v1/**", api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)

        def button(label):
            return page.get_by_role("button", name=label, exact=True)

        button("Já tenho conta").click(timeout=120000)
        page.get_by_label("Telefone ou e-mail", exact=True).fill("billing@example.com")
        page.get_by_label("Senha", exact=True).fill("browser-password-123")
        button("Entrar").click()
        page.get_by_role("tab", name="Mais", exact=True).click()
        button("ELEVEN PRO").click()
        expect(page.get_by_text("Plano gratuito", exact=True)).to_be_visible()
        button("ASSINAR ELEVEN PRO").click()
        page.get_by_label("CPF ou CNPJ do pagador", exact=True).fill("12345678909")
        artifacts = Path(__file__).resolve().parents[3] / ".local/prompt16-browser"
        artifacts.mkdir(exist_ok=True)
        for width in (320, 390, 768, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / f"checkout-{width}.png"), full_page=True)
        button("Confirmar assinatura e gerar Pix").click()
        expect(page.get_by_text("Aguardando pagamento", exact=True).first).to_be_visible()
        assert len(provider["subscriptions"]) == 1
        provider["status"] = "CONFIRMED"
        assert webhook(client, payload()).status_code == 200
        button("Atualizar assinatura").click()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        button("Cancelar assinatura").click()
        button("Confirmar cancelamento").click()
        expect(page.get_by_text("Assinatura cancelada", exact=True)).to_be_visible()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        assert not errors, errors
        context.close()
        browser.close()
