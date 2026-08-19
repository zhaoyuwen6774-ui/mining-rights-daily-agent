from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Status(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    accessed_at: datetime
    published_at: datetime | None = None
    page: int | None = Field(default=None, ge=1)


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: HttpUrl
    published_at: datetime | None = None
    summary: str = ""
    source_name: str
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class Article(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: HttpUrl
    text: str
    published_at: datetime | None = None
    author: str | None = None


class ReportCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    title: str
    url: str
    reporting_code: Literal["NI 43-101", "JORC", "Unknown"] = "Unknown"
    published_at: date | None = None


class ResourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Literal["Indicated", "Inferred"]
    tonnage_mt: float = Field(gt=0)
    grade_value: float = Field(gt=0)
    grade_unit: Literal["g/t Au", "% Cu", "% Li2O", "unknown"]
    contained_metal: float | None = Field(default=None, gt=0)
    metal_unit: Literal["oz", "t", "unknown"] | None = None
    reporting_code: Literal["NI 43-101", "JORC", "Unknown"] = "Unknown"
    source_url: str
    source_page: int = Field(ge=1)
    source_text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commodity: str
    date: date
    price: float = Field(gt=0)
    currency: str = "USD"
    unit: str = "tonne"
    price_type: str = "LME official cash"
    source_url: str
    provider: str


class PriceTrend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commodity: str
    points: list[PricePoint]
    change_absolute: float | None = None
    change_percent: float | None = None

    @field_validator("points")
    @classmethod
    def points_must_be_ordered(cls, value: list[PricePoint]) -> list[PricePoint]:
        if value != sorted(value, key=lambda point: point.date):
            raise ValueError("price points must be ordered by date")
        return value


T = TypeVar("T")

Commodity = Literal["copper", "zinc", "nickel", "lithium", "iron_ore", "gold", "unknown"]
ReportingCode = Literal["NI 43-101", "JORC", "Unknown"]
GradeUnit = Literal["g/t Au", "% Cu", "% Li2O", "unknown"]
MetalUnit = Literal["oz", "t", "unknown"]


class ToolResult(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    status: Status
    data: T
    sources: list[SourceRef] = Field(default_factory=list)
    as_of: datetime
    warnings: list[str] = Field(default_factory=list)


class BriefIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    company: str | None = None
    commodity: Commodity
    days: int = Field(default=7, ge=1, le=90)
