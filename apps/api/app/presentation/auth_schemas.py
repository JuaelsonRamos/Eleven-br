from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.domain.contacts import normalize_contact

Name = Annotated[str, Field(min_length=1, max_length=80)]
Contact = Annotated[str, Field(min_length=3, max_length=254)]
ChallengeToken = Annotated[str, Field(min_length=32, max_length=128)]


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    contact: Contact
    password: SecretStr = Field(min_length=8, max_length=128)
    password_confirmation: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Informe seu nome.")
        return value

    @field_validator("contact")
    @classmethod
    def clean_contact(cls, value: str) -> str:
        return normalize_contact(value)[1]

    @model_validator(mode="after")
    def matching_passwords(self) -> Self:
        if self.password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError("As senhas não coincidem.")
        return self


class LoginInput(BaseModel):
    contact: Contact
    password: SecretStr = Field(min_length=1, max_length=128)


class ChallengeInput(BaseModel):
    challenge_token: ChallengeToken


class VerifyInput(ChallengeInput):
    code: str = Field(pattern=r"^\d{6}$")


class ChangeContactInput(ChallengeInput):
    contact: Contact

    @field_validator("contact")
    @classmethod
    def clean_contact(cls, value: str) -> str:
        return normalize_contact(value)[1]


class RefreshInput(BaseModel):
    refresh_token: SecretStr | None = Field(default=None, min_length=32, max_length=128)


class VerificationRead(BaseModel):
    status: Literal["verification_required"] = "verification_required"
    challenge_token: str
    masked_contact: str
    resend_after: int
    development_code: str | None = None


class SessionRead(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    access_token: str
    refresh_token: str | None = None
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 900


class ProfileInput(BaseModel):
    name: Name

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return RegisterInput.clean_name(value)
