from pydantic import BaseModel, Field


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=10_000)
    unit_price_cents: int = Field(ge=0, le=10_000_000)


class InvoiceIn(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    lines: list[LineIn] = Field(min_length=1, max_length=100)


class Line(LineIn):
    id: int


class Invoice(BaseModel):
    id: int
    customer: str
    lines: list[Line]
    subtotal_cents: int
    total_cents: int
