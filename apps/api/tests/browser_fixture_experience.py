"""Phase 5C through Expo Web; all API writes use the isolated test schema."""

from pathlib import Path

from app.application.teams import add_member
from tests.browser_opponents_flow import account, browser_pages
from tests.conftest import make_player
from tests.test_opponents import accepted_fixture, clock  # noqa: F401

ARTIFACTS = Path(__file__).resolve().parents[3] / ".local/phase5c-browser"


def test_browser_fixture_experience(session):
    from playwright.sync_api import expect, sync_playwright

    _, (team, _, _, owner), (_, _, _, visitor) = accepted_fixture(session)
    player = make_player(session)
    player.display_name = "Jogador Convocado"
    add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    account(session, owner, "home5c@example.com")
    account(session, visitor, "away5c@example.com")
    account(session, player, "player5c@example.com")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser, (home, away, member), errors = browser_pages(
            playwright,
            session,
            ["home5c@example.com", "away5c@example.com", "player5c@example.com"],
        )

        def button(page, name):
            return page.get_by_role("button", name=name, exact=True)

        def game(page):
            page.get_by_role("tab", name="Jogos", exact=True).click()
            page.get_by_role("button", name="Abrir Mandantes x Visitantes", exact=False).click()

        def fixture(page):
            page.get_by_role("tab", name="Adversários", exact=True).click()
            button(page, "Confrontos").click()
            button(page, "Abrir confronto Mandantes x Visitantes").click()

        game(member)
        expect(member.get_by_text("Você não está convocado.", exact=True)).to_be_visible()
        expect(button(member, "VOU")).to_have_count(0)
        game(home)
        button(home, "Gerenciar convocação").click()
        home.get_by_role("checkbox", name="Jogador Convocado", exact=True).click()
        button(home, "Salvar convocação").click()
        expect(home.get_by_text("Pendentes: 1", exact=True)).to_be_visible()
        button(home, "Lembrar pendentes").click()
        expect(home.get_by_text("1 jogador foi lembrado.", exact=True)).to_be_visible()
        button(member, "Voltar aos jogos").click()
        member.get_by_role("button", name="Abrir Mandantes x Visitantes", exact=False).click()
        button(member, "VOU").click()
        expect(member.get_by_text("Confirmados: 1", exact=True)).to_be_visible()
        home.get_by_label("Nome/apelido do convidado", exact=True).fill("Goleiro convidado")
        button(home, "Adicionar convidado").click()
        expect(home.get_by_text("Goleiro convidado • Pendente", exact=True)).to_be_visible()
        for width in (320, 390, 768, 1280):
            home.set_viewport_size({"width": width, "height": 900})
            assert home.evaluate("document.documentElement.scrollWidth <= innerWidth")
            home.get_by_role(
                "heading", name="Mandantes x Visitantes", exact=True
            ).scroll_into_view_if_needed()
            home.screenshot(path=str(ARTIFACTS / f"callup-{width}.png"), full_page=True)
        button(home, "Ver confronto").click()
        button(home, "Propor alteração").click()
        day = home.get_by_label("Nova data (DD/MM/AAAA)", exact=True)
        day.fill("31102026")
        expect(day).to_have_value("31/10/2026")
        hour = home.get_by_label("Novo horário (HH:MM)", exact=True)
        hour.fill("2000")
        expect(hour).to_have_value("20:00")
        day.fill("31022026")
        button(home, "Enviar proposta").click()
        expect(
            home.get_by_text("Informe data, horário e local válidos.", exact=True)
        ).to_be_visible()
        day.fill("11102026")
        hour.fill("2580")
        button(home, "Enviar proposta").click()
        expect(
            home.get_by_text("Informe data, horário e local válidos.", exact=True)
        ).to_be_visible()
        hour.fill("2000")
        home.get_by_label("Novo local", exact=True).fill("Arena Nova")
        button(home, "Enviar proposta").click()
        expect(home.get_by_text("Proposta enviada ao adversário.", exact=True)).to_be_visible()
        fixture(away)
        button(away, "Aceitar alteração").click()
        expect(away.get_by_text("Proposta aceita.", exact=True)).to_be_visible()
        for width in (320, 390, 768, 1280):
            away.set_viewport_size({"width": width, "height": 900})
            assert away.evaluate("document.documentElement.scrollWidth <= innerWidth")
            away.get_by_role(
                "heading", name="Mandantes x Visitantes", exact=True
            ).scroll_into_view_if_needed()
            away.screenshot(path=str(ARTIFACTS / f"fixture-{width}.png"), full_page=True)
        button(away, "Solicitar cancelamento").click()
        button(away, "Enviar proposta").click()
        button(home, "Voltar aos adversários").click()
        button(home, "Confrontos").click()
        button(home, "Abrir confronto Mandantes x Visitantes").click()
        button(home, "Aceitar cancelamento").click()
        expect(home.get_by_text("CANCELADO POR ACORDO", exact=True)).to_be_visible()
        expect(button(home, "Desistir do confronto")).to_have_count(0)
        assert not errors, errors
        browser.close()
