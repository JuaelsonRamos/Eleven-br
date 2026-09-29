"""Real Expo browser, API and PostgreSQL isolated; provider simulated, no dev data writes."""

from pathlib import Path

import pytest

from app.application.teams import add_member
from app.domain.policies import Plan, Role
from app.infrastructure.asaas import Asaas
from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_billing import payload, provider, setup, webhook  # noqa: F401


def test_browser_billing_flow(session, provider, monkeypatch):  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    owner, team, client, path = setup(session)
    user = session.get(User, owner.user_id)
    user.email, user.password_hash = "billing@example.com", hash_password("browser-password-123")
    team.name = "Time comercial isolado"
    session.commit()
    client.headers.pop("Authorization", None)
    original_request = Asaas.request
    pix_code = "000201" + "1234567890" * 24

    def with_pix(self, method, path, *args, **kwargs):
        result = original_request(self, method, path, *args, **kwargs)
        if path.endswith("/pixQrCode"):
            result["payload"] = pix_code
            result["encodedImage"] = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8"
                "AAwMCAO+/p9sAAAAASUVORK5CYII="
            )
        return result

    monkeypatch.setattr(Asaas, "request", with_pix)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 900})
        context.grant_permissions(["clipboard-read", "clipboard-write"])

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
        button("Perfil do time").click()
        expect(page.get_by_text("Plano atual", exact=True)).to_be_visible()
        button("Conhecer o PRO").click()
        expect(page.get_by_text("Plano gratuito", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Início", exact=True).click()
        button("Escalação").click()
        button("Conhecer o Pro").click()
        expect(page.get_by_text("Plano gratuito", exact=True)).to_be_visible()
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
        provider["payments"] = [{"id": "pay_test", "status": "PENDING", "dueDate": "2026-12-01"}]
        button("Confirmar assinatura e gerar Pix").click()
        expect(page.get_by_text("Aguardando pagamento", exact=True).first).to_be_visible()
        expect(page.get_by_text("Vencimento: 01/12/2026", exact=True)).to_be_visible()
        expect(page.get_by_text("Código válido até 01/12/2026", exact=True)).to_be_visible()
        expect(button("Copiar código Pix")).to_be_visible()
        button("Copiar código Pix").click()
        expect(page.get_by_text("Código Pix copiado.", exact=True)).to_be_visible()
        assert page.evaluate("navigator.clipboard.readText()") == pix_code
        for width in (320, 390, 768, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / f"pix-{width}.png"), full_page=True)
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_have_count(0)
        assert len(provider["subscriptions"]) == 1
        page.get_by_role("tab", name="Mais", exact=True).click()
        button("ELEVEN PRO").click()
        expect(button("Copiar código Pix")).to_be_visible()
        assert len(provider["subscriptions"]) == 1  # Reentry only refreshes the existing payment.
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_have_count(0)
        provider["status"] = "CONFIRMED"
        provider["payments"] = []
        assert webhook(client, payload()).status_code == 200
        button("Atualizar assinatura").click()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Início", exact=True).click()
        button("Perfil do time").click()
        button("Gerenciar assinatura").click()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        button("Cancelar assinatura").click()
        button("Confirmar cancelamento").click()
        expect(page.get_by_text("Assinatura cancelada", exact=True)).to_be_visible()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        assert not errors, errors
        context.close()
        browser.close()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MEMBER])
def test_browser_billing_read_only(session, provider, role):  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    _, team, client, _ = setup(session)
    person = make_player(session)
    team.plan = Plan.PRO
    add_member(session, team_id=team.id, player_id=person.id, role=role)
    team.plan = (
        Plan.FREE
    )  # Preserve an administrator after downgrade; billing is still president-only.
    user = session.get(User, person.user_id)
    user.email, user.password_hash = "viewer@example.com", hash_password("browser-password-123")
    session.commit()
    client.headers.pop("Authorization", None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 900})
        route_api(context, client)
        page = context.new_page()
        login(page, "viewer@example.com")
        page.get_by_role("button", name="Perfil do time", exact=True).click()
        page.get_by_role("button", name="Conhecer o PRO", exact=True).click()
        expect(
            page.get_by_text(
                "Somente o Presidente do time pode contratar ou gerenciar o ELEVEN BR PRO.",
                exact=True,
            )
        ).to_be_visible()
        for label in ("ASSINAR ELEVEN PRO", "Cancelar assinatura", "Atualizar assinatura"):
            expect(page.get_by_role("button", name=label, exact=True)).to_have_count(0)
        page.get_by_role("button", name="Atualizar plano", exact=True).click()
        team.plan = Plan.PRO
        session.commit()
        page.get_by_role("tab", name="Início", exact=True).click()
        page.get_by_role("button", name="Perfil do time", exact=True).click()
        page.get_by_role("button", name="Ver plano PRO", exact=True).click()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Cancelar assinatura", exact=True)).to_have_count(0)
        assert provider["calls"] == []
        context.close()
        browser.close()


def test_browser_billing_hosted_card_stays_pending(session, provider):  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    owner, _, client, _ = setup(session)
    user = session.get(User, owner.user_id)
    user.email, user.password_hash = "card@example.com", hash_password("browser-password-123")
    session.commit()
    client.headers.pop("Authorization", None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 900})
        route_api(context, client)
        # Never call a provider or the public site from this isolated browser regression.
        context.route(
            "https://sandbox.asaas.com/**", lambda route: route.fulfill(body="Checkout isolado")
        )
        page = context.new_page()
        login(page, "card@example.com")
        page.get_by_role("tab", name="Mais", exact=True).click()

        def button(label):
            return page.get_by_role("button", name=label, exact=True)

        button("ELEVEN PRO").click()
        button("ASSINAR ELEVEN PRO").click()
        button("Cartão de crédito").click()
        page.get_by_label("CPF ou CNPJ do pagador", exact=True).fill("12345678909")
        button("Confirmar e continuar no Asaas").click()
        with page.expect_popup() as opened:
            button("Abrir pagamento seguro no Asaas").click()
        checkout = opened.value
        expect(checkout).to_have_url(
            "https://sandbox.asaas.com/checkoutSession/show?id=checkout_test"
        )
        checkout.close()
        button("Atualizar assinatura").click()
        expect(page.get_by_text("Aguardando pagamento", exact=True)).to_be_visible()
        expect(page.get_by_text("ELEVEN PRO ATIVO", exact=True)).to_have_count(0)
        assert len([call for call in provider["calls"] if call[:2] == ("POST", "/checkouts")]) == 1
        context.close()
        browser.close()


def route_api(context, client):
    from urllib.parse import urlsplit

    def api(route):
        url = urlsplit(route.request.url)
        response = client.request(
            route.request.method,
            url.path + ("?" + url.query if url.query else ""),
            content=route.request.post_data,
            headers={
                key: value
                for key, value in route.request.headers.items()
                if key not in {"host", "content-length"}
            },
        )
        route.fulfill(
            status=response.status_code, body=response.content, headers=dict(response.headers)
        )

    context.route("**/v1/**", api)


def login(page, email):
    page.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
    page.get_by_role("button", name="Já tenho conta", exact=True).click(timeout=120000)
    page.get_by_label("Telefone ou e-mail", exact=True).fill(email)
    page.get_by_label("Senha", exact=True).fill("browser-password-123")
    page.get_by_role("button", name="Entrar", exact=True).click()
