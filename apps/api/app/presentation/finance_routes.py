from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.application import finance, finance_dashboard, finance_writes
from app.application.finance_commands import (
    CancelEntryInput,
    CategoryInput,
    CompetenceInput,
    DuesActionInput,
    EditDuesInput,
    EditEntryInput,
    EntryInput,
    GenerateInput,
    PaymentInput,
    PreferencesInput,
    SettingsInput,
)
from app.presentation.dependencies import CurrentUser, SessionDep

router = APIRouter(prefix="/v1/teams/{team_id}/finance", tags=["finance"])
Offset = Annotated[int, Query(ge=0)]


def transaction(session: Session, operation: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        result = operation()
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


@router.get("")
def context(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return finance.context(session, user.id, team_id)


@router.put("/settings")
def settings(
    team_id: UUID, data: SettingsInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(session, lambda: finance_writes.settings(session, user.id, team_id, data))


@router.post("/dues/preview")
def preview(
    team_id: UUID, data: CompetenceInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return finance_writes.generation(session, user.id, team_id, data.competence)[0]


@router.post("/dues/generate")
def generate(
    team_id: UUID, data: GenerateInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(session, lambda: finance_writes.generate(session, user.id, team_id, data))


@router.get("/dues")
def dues(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    competence: date | None = None,
    offset: Offset = 0,
) -> dict[str, object]:
    return finance.dues_page(session, user.id, team_id, competence=competence, offset=offset)


@router.get("/dues/{dues_id}")
def detail(
    team_id: UUID, dues_id: UUID, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return finance.dues_detail(session, user.id, team_id, dues_id)


@router.post("/dues/{dues_id}/payments")
def payment(
    team_id: UUID, dues_id: UUID, data: PaymentInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_writes.pay(session, user.id, team_id, dues_id, data)
    )


@router.post("/dues/{dues_id}/actions")
def action(
    team_id: UUID, dues_id: UUID, data: DuesActionInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_writes.dues_action(session, user.id, team_id, dues_id, data)
    )


@router.get("/cash")
def cash(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    start: date | None = None,
    end: date | None = None,
    kind: Literal["INCOME", "EXPENSE"] | None = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    offset: Offset = 0,
    search: Annotated[str | None, Query(max_length=160)] = None,
) -> dict[str, object]:
    return finance.cash_page(
        session,
        user.id,
        team_id,
        start=start,
        end=end,
        kind=kind,
        category=category,
        offset=offset,
        search=search,
    )


@router.post("/cash")
def entry(
    team_id: UUID, data: EntryInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_writes.manual_entry(session, user.id, team_id, data)
    )


@router.post("/cash/{entry_id}/reverse")
def reverse(
    team_id: UUID, entry_id: UUID, data: CancelEntryInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_writes.cancel_entry(session, user.id, team_id, entry_id, data)
    )


@router.get("/dashboard")
def dashboard(
    team_id: UUID, month: date, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    if month.day != 1 or not 2000 <= month.year <= 2100:
        raise HTTPException(422, "Informe o primeiro dia da competência entre 2000 e 2100.")
    return finance_dashboard.summary(session, user.id, team_id, month)


@router.put("/preferences")
def preferences(
    team_id: UUID, data: PreferencesInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_dashboard.save_preferences(session, user.id, team_id, data)
    )


@router.post("/categories")
def category(
    team_id: UUID, data: CategoryInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_dashboard.create_category(session, user.id, team_id, data)
    )


@router.get("/categories")
def categories(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    finance.authorize(session, user.id, team_id, manage=True)
    return dict(finance_dashboard.categories(session, team_id))


@router.get("/cash/{entry_id}")
def entry_detail(
    team_id: UUID, entry_id: UUID, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return finance_dashboard.entry_detail(session, user.id, team_id, entry_id)


@router.put("/cash/{entry_id}")
def edit_entry(
    team_id: UUID, entry_id: UUID, data: EditEntryInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_dashboard.edit_entry(session, user.id, team_id, entry_id, data)
    )


@router.put("/dues/{dues_id}")
def edit_dues(
    team_id: UUID, dues_id: UUID, data: EditDuesInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return transaction(
        session, lambda: finance_dashboard.edit_dues(session, user.id, team_id, dues_id, data)
    )
