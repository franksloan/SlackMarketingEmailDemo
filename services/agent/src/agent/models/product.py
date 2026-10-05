from typing import Literal

from pydantic import BaseModel


class ProductMatch(BaseModel):
    name: str
    url: str


class ProductLookupResult(BaseModel):
    confidence: Literal["high", "low"]
    product: ProductMatch | None = None          # set when confidence is high
    candidates: list[ProductMatch] = []          # set when confidence is low
    clarification_message: str | None = None     # returned to user when ambiguous
