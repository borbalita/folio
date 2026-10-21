"""Typed output for a finance answer: text plus cards that point at invoices or drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FinanceCard(BaseModel):
    kind: Literal["invoices", "payments"] = Field(
        description="invoices: invoice ids from list_invoices or get_invoice. "
        "payments: draft ids from prepare_payments."
    )
    ids: list[UUID]


class FinanceAnswer(BaseModel):
    answer: str
    cards: list[FinanceCard] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FinanceTurnResult:
    answer: FinanceAnswer
    usage: dict[str, int]
