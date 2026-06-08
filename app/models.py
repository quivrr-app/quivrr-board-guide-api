from pydantic import BaseModel, Field


class RiderProfile(BaseModel):
    height_cm: int | None = None
    weight_kg: int | None = None
    ability: str | None = None
    current_board: str | None = None
    current_volume_litres: float | None = None
    region: str | None = None
    wave_size: str | None = None
    wave_type: str | None = None
    goal: str | None = None


class BoardRecommendation(BaseModel):
    board_category: str
    suggested_length_range: str
    suggested_volume_range_litres: str
    construction_notes: str | None = None
    why_it_fits: str
    quivrr_search_direction: str


class SuggestedBoard(BaseModel):
    brand: str
    model: str
    category: str
    confidence: float
    why_it_fits: str
    trade_offs: str | None = None
    source: str = "quivrr_controlled_knowledge"


class BoardGuideMessage(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str


class BoardGuideRequest(BaseModel):
    message: str
    region: str | None = None
    page_context: str | None = None
    conversation: list[BoardGuideMessage] = Field(default_factory=list)


class BoardGuideResponse(BaseModel):
    guide_name: str
    reply: str
    profile: RiderProfile
    recommendation: BoardRecommendation | None = None
    suggested_boards: list[SuggestedBoard] = Field(default_factory=list)
    missing_fields: list[str]
    recommended_next_step: str | None = None
    source: str
