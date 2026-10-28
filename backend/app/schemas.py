from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def trim_text(cls, value, info):
        if isinstance(value, str) and "password" not in info.field_name:
            return value.strip()
        return value


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class Code(Input):
    code: str = Field(min_length=6, max_length=40)


class PasswordChange(Input):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=12, max_length=128)


ClassificationName = Literal["prospect", "customer", "partner", "supplier"]


class OrganizationInput(Input):
    name: str = Field(min_length=2, max_length=180)
    industry: str | None = Field(default=None, max_length=100)
    country: str = Field(default="Cameroon", min_length=2, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    website: HttpUrl | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=10000)
    classifications: list[ClassificationName] = Field(default_factory=lambda: ["prospect"], min_length=1, max_length=4)
    owner_id: UUID | None = None

    @field_validator("classifications")
    @classmethod
    def unique_classifications(cls, value):
        return list(dict.fromkeys(value))


class ContactInput(Input):
    full_name: str = Field(min_length=2, max_length=150)
    job_title: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool = False


class StaffCreate(Input):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    role: Literal["CEO", "Manager", "Staff"] = "Staff"
    responsibilities: list[str] = Field(default_factory=list, max_length=4)


class StaffUpdate(Input):
    full_name: str = Field(min_length=2, max_length=150)
    is_active: bool
    role: Literal["CEO", "Manager", "Staff"]
    responsibilities: list[str] = Field(default_factory=list, max_length=4)


class RolePermissions(Input):
    permissions: list[str] = Field(max_length=100)
