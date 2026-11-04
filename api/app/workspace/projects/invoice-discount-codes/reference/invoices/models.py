from pydantic import BaseModel, Field, field_validator


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=10_000)
    unit_price_cents: int = Field(ge=0, le=10_000_000)


class InvoiceIn(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    lines: list[LineIn] = Field(min_length=1, max_length=100)
    discount_code: str | None = Field(default=None, max_length=40)

    @field_validator("discount_code")
    @classmethod
    def _normalise_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper() or None


class Line(LineIn):
    id: int


class Invoice(BaseModel):
    id: int
    customer: str
    lines: list[Line]
    discount_code: str | None
    subtotal_cents: int
    discount_cents: int
    total_cents: int
