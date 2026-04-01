from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class HSCodeEntry(BaseModel):
    """A single HS-6 code in a material bucket."""
    code: str
    description: str
    quality: str = Field(description="'clean' or 'shared'")
    relevance: str = Field(description="Why this HS code relates to the material")


class MaterialBucket(BaseModel):
    """All HS codes related to a single material."""
    hs_codes: List[HSCodeEntry]
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    model: str = "openai:gpt-5.3"


class TradeFlowRow(BaseModel):
    """One row of the output CSV."""
    material: str
    hs_bucket: str
    hs_bucket_quality: str
    year: int
    exporter: str
    exporter_iso3: str
    import_value_usd: float
    import_share_pct: float
    exporter_rank: int
