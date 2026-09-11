from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
OptionalText80 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Password = Annotated[str, Field(min_length=8, max_length=128)]
Email = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TeacherRef(Schema):
    id: int
    label: str


class ErrorBody(Schema):
    code: str
    message: str
    details: Any = None


class ErrorResponse(Schema):
    error: ErrorBody


class Message(Schema):
    message: str
