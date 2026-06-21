from pydantic import BaseModel, ConfigDict, Field


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
    wave_power: str | None = None
    goal: str | None = None
    construction_preference: str | None = None
    requested_construction: str | None = None
    requested_length: str | None = None
    requested_brand: str | None = None


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
    board_model_id: int | None = Field(default=None, exclude=True)


class VolumeGuidance(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    minimum_litres: float = Field(alias="minimumLitres")
    maximum_litres: float = Field(alias="maximumLitres")
    label: str
    recommended_category: str = Field(alias="recommendedCategory")
    reasoning: str


class BodhiRecommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    brand: str
    model: str
    category: str
    why_it_fits: str = Field(alias="whyItFits")
    suggested_volume_or_size_range: str | None = Field(default=None, alias="suggestedVolumeOrSizeRange")
    wave_range: str | None = Field(default=None, alias="waveRange")
    skill_fit: str | None = Field(default=None, alias="skillFit")
    available_count: int = Field(default=0, alias="availableCount")
    region: str | None = None
    example_product_url: str | None = Field(default=None, alias="exampleProductUrl")
    source_type: str = Field(alias="sourceType")
    price_range: str | None = Field(default=None, alias="priceRange")
    confidence: float


class BoardGuideMessage(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str


class BoardGuideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    region: str | None = None
    page_context: str | None = None
    conversation: list[BoardGuideMessage] = Field(default_factory=list)
    intake_state: RiderProfile | None = Field(default=None, alias="intakeState")


class BoardGuideResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    guide_name: str
    reply: str
    profile: RiderProfile
    recommendation: BoardRecommendation | None = None
    suggested_boards: list[SuggestedBoard] = Field(default_factory=list)
    missing_fields: list[str]
    recommended_next_step: str | None = None
    source: str
    intake_state: RiderProfile = Field(alias="intakeState")
    missing_questions: list[str] = Field(default_factory=list, alias="missingQuestions")
    volume_guidance: VolumeGuidance | None = Field(default=None, alias="volumeGuidance")
    recommendations: list[BodhiRecommendation] = Field(default_factory=list)
    intent: str = "surfer_fit_request"
