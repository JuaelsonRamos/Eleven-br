"""Internal daily job: generate current monthly dues, never collect money."""

import calendar
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import finance as f
from app.application.finance_writes import audit
from app.application.notification_events import finance_notice
from app.domain.notifications import NotificationType
from app.infrastructure.database import get_engine
from app.infrastructure.finance_models import DuesSettings, MonthlyDues
from app.infrastructure.models import Team, TeamMembership


def generate_current(session: Session, team_id: UUID) -> int:
    team = session.scalar(select(Team).where(Team.id == team_id).with_for_update())
    if not team or team.status != "active" or not f.enabled(session, team):
        return 0
    config = session.scalar(
        select(DuesSettings)
        .where(DuesSettings.team_id == team_id)
        .execution_options(populate_existing=True)
    )
    month = datetime.now(ZoneInfo("America/Sao_Paulo")).date().replace(day=1)
    if (
        not config
        or not config.active
        or not config.repeat_monthly
        or not config.next_competence
        or config.next_competence > month
    ):
        return 0
    existing = select(MonthlyDues.membership_id).where(
        MonthlyDues.team_id == team_id, MonthlyDues.competence == month
    )
    members = list(
        session.scalars(
            select(TeamMembership.id).where(
                TeamMembership.team_id == team_id,
                TeamMembership.status == "active",
                TeamMembership.id.not_in(existing),
            )
        )
    )
    for member_id in members:
        item = MonthlyDues(
            team_id=team_id,
            membership_id=member_id,
            competence=month,
            amount=config.amount,
            due_date=month.replace(
                day=min(config.due_day, calendar.monthrange(month.year, month.month)[1])
            ),
            created_by=config.updated_by,
        )
        session.add(item)
        session.flush()
        audit(
            session,
            team_id,
            config.updated_by,
            "GENERATED_RECURRING",
            dues_id=item.id,
            reason="Geração automática conforme configuração autorizada; "
            "ator é o responsável pela configuração.",
        )
        finance_notice(session, item, NotificationType.FINANCE_CHARGE_CREATED)
    config.next_competence = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    session.flush()
    return len(members)


def main() -> None:
    engine = get_engine()
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(DuesSettings.team_id).where(
                    DuesSettings.active.is_(True), DuesSettings.repeat_monthly.is_(True)
                )
            )
        )
    failed = 0
    for team_id in ids:
        try:
            with Session(engine) as session, session.begin():
                generate_current(session, team_id)
        except Exception:
            # Do not log contacts, SQL parameters or financial payloads.
            failed += 1
    if failed:
        raise SystemExit(f"{failed} equipe(s) não processada(s); verificar e repetir a rotina.")
    print("Rotina de mensalidades concluída.")


if __name__ == "__main__":
    main()
