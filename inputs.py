"""Request validation shared by HTTP forms and confirmed assistant writes."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

import detect


def _known_category(value: str) -> str:
    if value not in detect.ALL_CATEGORIES:
        raise ValueError("اختر تصنيف من القائمة.")
    return value


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ExpenseIn(Input):
    name: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    category: str = Field(pattern=r"^(essential|flexible):.{1,30}$")

    _cat = field_validator("category")(classmethod(lambda cls, v: _known_category(v)))

    @field_validator("amount")
    @classmethod
    def whole_cents(cls, value):
        if round(value, 2) != value:
            raise ValueError("المبلغ بحد أقصى منزلتين عشريتين.")
        return value


class PlanIn(Input):
    name: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    day: int = Field(ge=1, le=28)
    remaining: int | None = Field(default=None, ge=1, le=600)
    kind: Literal["bnpl", "loan", "recurring"] = "recurring"


class UpdatePlanIn(Input):
    plan_id: str = Field(min_length=1, max_length=80)
    amount: float | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    remaining: int | None = Field(default=None, ge=0, le=600)


class WishIn(Input):
    name: str = Field(min_length=1, max_length=60)
    price: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    method: Literal["cash", "bnpl3", "bnpl4", "bnpl6", "fin12", "save"]


class DeletePlanIn(Input):
    plan_id: str = Field(min_length=1, max_length=80)


class DeleteWishIn(Input):
    item_id: int = Field(gt=0)


class CategoryIn(Input):
    merchant: str = Field(min_length=1, max_length=80)
    category: str = Field(pattern=r"^(essential|flexible):.{1,30}$")
    _cat = field_validator("category")(classmethod(lambda cls, v: _known_category(v)))


class ContactIn(Input):
    name: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=5, max_length=2000)