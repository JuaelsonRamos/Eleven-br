from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, field_validator


def exact_money(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("Envie o valor como texto decimal, por exemplo 30.00.")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(exact_money),
    Field(gt=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2),
]
Note = Annotated[str, Field(max_length=500)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SettingsInput(Input):
    amount: Money
    due_day: int = Field(ge=1, le=31, strict=True)
    active: StrictBool
    expected_version: int = Field(ge=0, strict=True)
    repeat_monthly: StrictBool | None = None


class CompetenceInput(Input):
    competence: date

    @field_validator("competence")
    @classmethod
    def monthly(cls, value: date) -> date:
        if value.day != 1 or not 2000 <= value.year <= 2100:
            raise ValueError("Informe o primeiro dia da competência, entre 2000 e 2100.")
        return value


class GenerateInput(CompetenceInput):
    preview_token: str = Field(min_length=64, max_length=64)
    confirm: StrictBool = False


class VersionInput(Input):
    expected_version: int = Field(ge=1, strict=True)
    confirm: StrictBool = False


class PaymentInput(VersionInput):
    command_id: UUID
    amount: Money
    entry_date: date
    payment_method: Literal["PIX", "CASH", "CARD", "OTHER"]
    note: Note | None = None


class DuesActionInput(VersionInput):
    action: Literal["exempt", "undo_exemption", "cancel"]
    reason: Note | None = None


class EntryInput(Input):
    command_id: UUID
    kind: Literal["INCOME", "EXPENSE"]
    category: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=160)
    amount: Money
    entry_date: date
    note: Note | None = None
    confirm: StrictBool = False


class CancelEntryInput(Input):
    expected_dues_version: int | None = Field(default=None, ge=1, strict=True)
    reason: str = Field(min_length=1, max_length=500)
    confirm: StrictBool = False


class PreferencesInput(Input):
    opening_balance: Annotated[
        Decimal,
        BeforeValidator(exact_money),
        Field(
            ge=Decimal("-99999999.99"), le=Decimal("99999999.99"), max_digits=10, decimal_places=2
        ),
    ]
    opening_date: date
    share_summary: StrictBool
    expected_version: int = Field(ge=0, strict=True)
    confirm: StrictBool = False


class CategoryInput(Input):
    kind: Literal["INCOME", "EXPENSE"]
    name: str = Field(min_length=1, max_length=60)


class EditEntryInput(VersionInput):
    category: str = Field(min_length=1, max_length=60)
    description: str = Field(max_length=160)
    amount: Money
    entry_date: date


class EditDuesInput(VersionInput):
    amount: Money
