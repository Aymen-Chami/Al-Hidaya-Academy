from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.models.enums import Role
from app.schemas.common import Email, Name, OptionalText80, Password, Phone, Schema

Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]


class EmailIn(Schema):
    email: Email


class VerifyCodeIn(Schema):
    email: Email
    code: Code


class CompletionTokenOut(Schema):
    completion_token: str
    expires_in_seconds: int


class SignupCompleteIn(Schema):
    completion_token: str = Field(min_length=10, max_length=100)
    first_name: Name
    last_name: Name
    password: Password
    phone: Phone | None = None


class LoginIn(Schema):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class ResetCompleteIn(Schema):
    completion_token: str = Field(min_length=10, max_length=100)
    new_password: Password


class ChangePasswordIn(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class MeOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    display_name: str | None
    phone: str | None
    role: Role
    created_at: datetime


class MeUpdateIn(Schema):
    first_name: Name | None = None
    last_name: Name | None = None
    display_name: OptionalText80 | None = None
    phone: Phone | None = None
