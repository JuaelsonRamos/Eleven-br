"""Real Expo browser, isolated API/PostgreSQL: official team location confirmation."""

from app.application.teams import add_member
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.models import MembershipPermission, Team
from tests.browser_opponents_flow import account, browser_pages
from tests.conftest import make_player
from tests.test_foundation import make_team


def test_browser_president_confirms_and_changes_the_team_location(session):
    from playwright.sync_api import expect, sync_playwright

    president = make_player(session)
    team = make_team(session, president, Plan.PRO)
    team.name, team.city, team.state = "Tabajara FC", "vila  velha", "ES"  # Legacy typed city.
    admin = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=admin.id, role=Role.ADMIN)
    session.add(
        MembershipPermission(membership_id=membership.id, permission=Permission.MANAGE_TEAM)
    )
    session.commit()
    account(session, admin, "admin@example.com")
    account(session, president, "president@example.com")
    with sync_playwright() as playwright:
        browser, (manager, owner), errors = browser_pages(
            playwright, session, ["admin@example.com", "president@example.com"]
        )
        card = "Confirme a localização do seu time"
        expect(manager.get_by_text("Tabajara FC", exact=True).first).to_be_visible()
        expect(manager.get_by_text(card, exact=True)).to_have_count(0)  # President only.
        manager.get_by_role("button", name="Perfil do time", exact=True).click()
        manager.get_by_role("button", name="Editar time", exact=True).click()
        only = "Somente o Presidente confirma ou altera a localização."
        expect(manager.get_by_text(only, exact=True)).to_be_visible()
        expect(manager.get_by_role("button", name="Alterar localização", exact=True)).to_have_count(
            0
        )

        expect(owner.get_by_text(card, exact=True)).to_be_visible()
        expect(owner.get_by_text("Localização atual: vila  velha / ES", exact=True)).to_be_visible()
        expect(owner.get_by_role("button", name="Cidade", exact=True)).to_contain_text("Vila Velha")
        assert owner.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        session.refresh(team)
        assert team.location_confirmed_at is None  # The suggestion alone confirms nothing.
        owner.get_by_role("button", name="CONFIRMAR LOCALIZAÇÃO", exact=True).click()
        expect(owner.get_by_text(card, exact=True)).to_have_count(0)
        expect(owner.get_by_text("Vila Velha · ES", exact=True)).to_be_visible()

        owner.get_by_role("button", name="Perfil do time", exact=True).click()
        owner.get_by_role("button", name="Editar time", exact=True).click()
        owner.get_by_role("button", name="Alterar localização", exact=True).click()
        owner.get_by_role("button", name="UF", exact=True).last.click()
        owner.get_by_label("Pesquisar UF", exact=True).fill("Rio de Janeiro")
        owner.get_by_role("button", name="Rio de Janeiro (RJ)", exact=True).click()
        city = owner.get_by_role("button", name="Cidade", exact=True).last
        expect(city).to_contain_text("Pesquisar cidade")  # A new UF clears the city.
        city.click()
        owner.get_by_label("Pesquisar cidade", exact=True).fill("niter")
        owner.get_by_role("button", name="Niterói", exact=True).click()
        owner.get_by_role("button", name="Salvar localização", exact=True).click()
        expect(owner.get_by_text("Niterói/RJ", exact=True)).to_be_visible()
        session.expire_all()
        saved = session.get(Team, team.id)
        assert saved and (saved.city, saved.state, saved.municipality_code) == (
            "Niterói",
            "RJ",
            3303302,
        )
        assert not errors, errors
        browser.close()
