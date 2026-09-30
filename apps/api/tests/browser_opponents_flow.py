"""Real Expo browser, isolated API/PostgreSQL: the opponents center from search to review."""

from datetime import datetime
from pathlib import Path

from app.domain import opponents as rules
from app.domain.policies import Plan
from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.browser_billing_flow import login, route_api
from tests.test_opponents import club
from tests.test_team_profiles import client_for

TABS = ["Início", "Jogos", "Adversários", "Elenco", "Mais"]
ARTIFACTS = Path(__file__).resolve().parents[3] / ".local/phase5-browser"


def account(session, president, email):
    user = session.get(User, president.user_id)
    user.email, user.password_hash = email, hash_password("browser-password-123")
    session.commit()


def fits(page):
    """No horizontal scroll and every bottom tab label fully visible on narrow phones."""
    size = page.viewport_size
    for width in (320, 360, 390, 414):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for name in TABS:
            tab = page.get_by_role("tab", name=name, exact=True)
            label = tab.locator("div[dir='auto']").last
            assert label.evaluate("item => item.scrollWidth <= item.clientWidth"), (width, name)
    page.set_viewport_size(size)


def browser_pages(playwright, session, emails):
    browser = playwright.chromium.launch()
    errors: list[str] = []
    pages = []
    for email in emails:
        context = browser.new_context(viewport={"width": 320, "height": 900})
        # One API client per browser: a shared cookie jar would reuse the first login.
        route_api(context, client_for(session))
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        login(page, email)
        pages.append(page)
    return browser, pages, errors


def test_browser_opponents_center_flow(session, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    moment = {"now": datetime(2026, 10, 5, 12, 0)}
    monkeypatch.setattr(rules, "local_now", lambda: moment["now"])
    _, _, girls_president = club(session, "Fut Girl")
    club(session, "Leões", category="male")  # Nearby but incompatible: never listed.
    _, _, lionesses_president = club(session, "Leoas FC")
    account(session, girls_president, "girls@example.com")
    account(session, lionesses_president, "lionesses@example.com")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser, (home, away), errors = browser_pages(
            playwright, session, ["girls@example.com", "lionesses@example.com"]
        )

        def button(page, name):
            return page.get_by_role("button", name=name, exact=True)

        def text(page, value):
            return page.get_by_text(value, exact=True)

        tabs = home.get_by_role("tab")
        expect(tabs).to_have_count(5)
        assert [tabs.nth(index).get_attribute("aria-label") for index in range(5)] == TABS
        fits(home)
        home.get_by_role("tab", name="Adversários", exact=True).click()
        expect(home.get_by_role("heading", name="Adversários", exact=True)).to_be_visible()
        expect(home.get_by_role("radio", name="Campo", exact=True)).to_be_checked()
        expect(home.get_by_role("radio", name="Feminino", exact=True)).to_be_checked()
        free_note = "Buscar é livre. Plano Free: 1 desafio por mês — disponível."
        expect(text(home, free_note)).to_be_visible()
        button(home, "Buscar adversários").click()
        expect(text(home, "Times próximos: sua cidade")).to_be_visible()
        expect(button(home, "Abrir perfil de Leões")).to_have_count(0)
        fits(home)
        home.screenshot(path=str(ARTIFACTS / "search-320.png"), full_page=True)
        button(home, "Abrir perfil de Leoas FC").click()
        expect(text(home, "Sem histórico suficiente")).to_be_visible()
        home.get_by_label("Data (DD/MM/AAAA)", exact=True).fill("10/10/2026")
        home.get_by_label("Horário (HH:MM)", exact=True).fill("16:00")
        home.get_by_label("Local", exact=True).fill("Arena Central")
        button(home, "Enviar desafio").click()
        expect(
            text(home, "Desafio enviado. O adversário foi avisado e responde em Adversários.")
        ).to_be_visible()
        used = (
            "O desafio gratuito deste mês já foi usado. "
            "No ELEVEN BR PRO os desafios são ilimitados."
        )
        expect(text(home, used)).to_be_visible()  # Free credit spent on the valid send.
        expect(button(home, "CONHECER O ELEVEN BR PRO")).to_be_visible()
        expect(button(home, "Enviar desafio")).to_have_count(0)

        away.get_by_role("tab", name="Adversários", exact=True).click()
        expect(button(away, "Recebidos (1)")).to_be_visible()
        button(away, "Aceitar desafio").click()
        expect(
            text(away, "Desafio aceito. O confronto já está em Jogos para os dois times.")
        ).to_be_visible()
        button(away, "Ver confronto").click()
        expect(text(away, "AGUARDANDO PLACAR")).to_be_visible()
        expect(
            text(away, "O placar pode ser informado a partir do horário do jogo.")
        ).to_be_visible()

        moment["now"] = datetime(2026, 10, 10, 18, 0)
        button(home, "Voltar aos adversários").click()
        button(home, "Confrontos").click()
        button(home, "Abrir confronto Fut Girl x Leoas FC").click()
        home.get_by_label("Gols de Fut Girl", exact=True).fill("4")
        home.get_by_label("Gols de Leoas FC", exact=True).fill("2")
        button(home, "Informar placar").click()
        expect(text(home, "Placar enviado ao adversário.")).to_be_visible()
        expect(text(home, "AGUARDANDO CONFIRMAÇÃO")).to_be_visible()

        button(away, "Voltar aos adversários").click()
        button(away, "Confrontos").click()
        button(away, "Abrir confronto Fut Girl x Leoas FC").click()
        button(away, "Confirmar placar 4 x 2").click()
        expect(text(away, "RESULTADO VALIDADO")).to_be_visible()
        expect(text(away, "AVALIAÇÃO DISPONÍVEL")).to_be_visible()
        for question in (
            "Compareceu ao jogo?",
            "Cumpriu o horário combinado?",
            "Cumpriu o que foi combinado?",
        ):
            away.get_by_role("radio", name=f"{question} Sim", exact=True).click()
        button(away, "Enviar avaliação").click()
        expect(text(away, "Avaliação enviada.")).to_be_visible()
        expect(text(away, "AVALIAÇÃO CONCLUÍDA")).to_be_visible()
        for width in (320, 768, 1280):
            away.set_viewport_size({"width": width, "height": 900})
            assert away.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            away.screenshot(path=str(ARTIFACTS / f"fixture-{width}.png"), full_page=True)

        button(away, "Ver perfil de Fut Girl").click()
        expect(text(away, "Histórico entre os times")).to_be_visible()
        expect(text(away, "RESULTADO VALIDADO")).to_be_visible()
        home.get_by_role("tab", name="Jogos", exact=True).click()
        expect(text(home, "CONFRONTO OFICIAL")).to_be_visible()
        fits(home)
        assert not errors, errors
        browser.close()


def test_browser_opponent_search_filters_and_expansion(session):
    from playwright.sync_api import expect, sync_playwright

    _, _, president = club(
        session, "Tabajara FC", modalities=("campo", "society", "futsal"), plan=Plan.PRO
    )
    club(session, "Aurora", city="Campinas", modalities=("society",))
    club(session, "Gaviões", modalities=("society",), category=None)
    club(session, "Dragões", category="male")
    rio = {"city": "Rio de Janeiro", "state": "RJ", "modalities": ("futsal",)}
    club(session, "Juntas", category="mixed", **rio)
    account(session, president, "tabajara@example.com")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser, (page,), errors = browser_pages(playwright, session, ["tabajara@example.com"])

        def button(name):
            return page.get_by_role("button", name=name, exact=True)

        def radio(name):
            return page.get_by_role("radio", name=name, exact=True)

        def text(value):
            return page.get_by_text(value, exact=True)

        page.get_by_role("tab", name="Adversários", exact=True).click()
        pro_note = "Buscar é livre. No ELEVEN BR PRO os desafios são ilimitados."
        expect(text(pro_note)).to_be_visible()
        expect(text("Escolha a modalidade do confronto.")).to_be_visible()  # Not presumed.
        expect(button("Buscar adversários")).to_be_disabled()
        radio("Society / Fut7").click()
        button("Buscar adversários").click()
        widened = "Nenhum adversário compatível na sua cidade. A busca foi ampliada."
        expect(text(widened)).to_be_visible()
        expect(text("Busca ampliada: seu estado")).to_be_visible()
        expect(text("Categoria não informada")).to_be_visible()
        expect(button("Abrir perfil de Gaviões")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(ARTIFACTS / "search-expanded-320.png"), full_page=True)

        radio("Campo").click()
        radio("Masculino").click()
        button("Buscar adversários").click()
        expect(text("Times próximos: sua cidade")).to_be_visible()
        expect(button("Abrir perfil de Dragões")).to_be_visible()

        radio("Futsal").click()
        radio("Misto").click()
        radio("Escolher UF/cidade").click()
        button("UF").click()
        page.get_by_label("Pesquisar UF", exact=True).fill("Rio de Janeiro")
        button("Rio de Janeiro (RJ)").click()
        button("Buscar adversários").click()
        expect(text("Times em RJ")).to_be_visible()
        expect(button("Abrir perfil de Juntas")).to_be_visible()

        radio("Perto do meu time").click()
        radio("Campo").click()
        button("Buscar adversários").click()
        expect(text("Nenhum adversário encontrado")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()
