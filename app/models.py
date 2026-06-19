from pydantic import BaseModel, Field


class RiderProfile(BaseModel):
    height_cm: int | None = None
    weight_kg: int | None = None
    ability: str | None = None
    current_board: str | None = None
    current_volume_litres: float | None = None
    target_volume_litres: float | None = None
    age: int | None = None
    fitness_level: str | None = None
    surf_frequency_per_week: float | None = None
    preferred_board_type: str | None = None
    desired_feel: str | None = None
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
    adjustment_factors: list[str] = Field(default_factory=list)


class SuggestedBoard(BaseModel):
    brand: str
    model: str
    category: str
    confidence: float
    why_it_fits: str
    description: str | None = None
    short_description: str | None = None
    trade_offs: str | None = None
    suggested_size: str | None = None
    volume_range: str | None = None
    wave_range: str | None = None
    skill_fit: str | None = None
    available_count: int = 0
    manufacturer_direct_count: int = 0
    retailer_count: int = 0
    example_live_source_url: str | None = None
    price_range: str | None = None
    region: str | None = None
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
