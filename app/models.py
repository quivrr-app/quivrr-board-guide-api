from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class RiderProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    age: int | None = None
    age_band: str | None = None
    ability: str | None = None
    surfer_stage: str | None = Field(default=None, alias="surferStage")
    surf_frequency_per_week: float | None = Field(default=None, alias="surf_frequency")
    fitness_level: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fitness_level", "fitness"),
        serialization_alias="fitness",
    )
    paddle_strength: str | None = None
    stance: str | None = None

    region: str | None = None
    home_break_type: str | None = None
    wave_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("wave_type", "home_break_type"),
        serialization_alias="wave_type",
    )
    wave_size: str | None = None
    wave_size_min_ft: float | None = None
    wave_size_max_ft: float | None = None
    wave_power: str | None = None
    wave_quality: str | None = None

    preferred_board_type: str | None = None
    desired_feel: str | None = Field(
        default=None,
        validation_alias=AliasChoices("desired_feel", "preferred_feel"),
        serialization_alias="preferred_feel",
    )
    goal: str | None = None
    preferred_brands: list[str] = Field(default_factory=list)
    construction_preference: str | None = None
    requested_construction: str | None = None
    requested_length: str | None = None
    requested_brand: str | None = None

    current_board: str | None = None
    current_board_brand: str | None = None
    current_board_model: str | None = None
    current_board_length: str | None = None
    current_volume_litres: float | None = None
    current_board_volume_litres: float | None = None
    current_board_feedback: str | None = None
    target_volume_litres: float | None = None
    target_volume_min_litres: float | None = None
    target_volume_max_litres: float | None = None
    target_volume_source: str | None = None
    target_volume_confidence: str | None = None
    home_break: str | None = None
    home_country: str | None = None

    confidence: float | None = None
    profile_sources: list[str] = Field(default_factory=list)
    profile_conflicts: list[str] = Field(default_factory=list)
    field_provenance: dict[str, str] = Field(default_factory=dict, alias="fieldProvenance")


class BoardRecommendation(BaseModel):
    board_category: str
    suggested_length_range: str
    suggested_volume_range_litres: str
    construction_notes: str | None = None
    why_it_fits: str
    quivrr_search_direction: str
    adjustment_factors: list[str] = Field(default_factory=list)


class RetailerOffer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    offer_id: str = Field(alias="offerId")
    canonical_model_id: int | None = Field(default=None, alias="canonicalModelId")
    canonical_board_size_id: int | None = Field(default=None, alias="canonicalBoardSizeId")
    brand: str | None = None
    model: str | None = None
    construction: str | None = None
    length: str | None = None
    volume_litres: float | None = Field(default=None, alias="volumeLitres")
    retailer_id: int | None = Field(default=None, alias="retailerId")
    retailer_name: str | None = Field(default=None, alias="retailerName")
    region: str
    currency: str | None = None
    observed_price: float | None = Field(default=None, alias="observedPrice")
    stock_status: str | None = Field(default=None, alias="stockStatus")
    in_stock: bool = Field(default=False, alias="inStock")
    product_url: str | None = Field(default=None, alias="productUrl")
    source_type: str = Field(alias="sourceType")
    observed_timestamp: str | None = Field(default=None, alias="observedTimestamp")
    match_quality: str = Field(alias="matchQuality")
    match_label: str = Field(alias="matchLabel")
    sponsored: bool = False
    sponsor_campaign_id: str | None = Field(default=None, alias="sponsorCampaignId")
    sponsor_disclosure: str | None = Field(default=None, alias="sponsorDisclosure")
    impression_id: str | None = Field(default=None, alias="impressionId")
    click_id: str | None = Field(default=None, alias="clickId")
    sponsor_destination_url: str | None = Field(default=None, alias="sponsorDestinationUrl")
    sponsor_priority: int | None = Field(default=None, alias="sponsorPriority")


class SuggestedBoard(BaseModel):
    brand: str
    model: str
    category: str
    confidence: float
    fit_score: int | None = None
    fit_confidence: str | None = None
    why_it_fits: str
    description: str | None = None
    short_description: str | None = None
    design_context: str | None = None
    trade_offs: str | None = None
    suggested_size: str | None = None
    volume_range: str | None = None
    wave_range: str | None = None
    skill_fit: str | None = None
    available_count: int = 0
    manufacturer_direct_count: int = 0
    retailer_count: int = 0
    availability_checked: bool = False
    availability_status: str = "not_checked"
    inventory_source: str | None = None
    inventory_match_count: int = 0
    exact_size_inventory_count: int = 0
    close_size_inventory_count: int = 0
    exact_size_stock: bool = False
    model_level_stock: bool = False
    example_live_source_url: str | None = None
    quivrr_search_url: str | None = None
    source_product_url: str | None = None
    board_size_id: int | None = None
    selected_construction: str | None = None
    selected_volume_litres: float | None = None
    volume_delta_litres: float | None = None
    selected_size_reason: str | None = None
    volume_compatibility: str | None = None
    price_range: str | None = None
    offers: list[RetailerOffer] = Field(default_factory=list)
    region: str | None = None
    region_code: str | None = None
    source: str = "quivrr_controlled_knowledge"
    board_model_id: int | None = Field(default=None, exclude=True)
    authoritative_public_family: str | None = None
    detailed_category: str | None = None
    primary_fin_setup: str | None = None
    alternative_fin_setup: list[str] = Field(default_factory=list)
    recommendation_lanes: list[str] = Field(default_factory=list)
    excluded_recommendation_lanes: list[str] = Field(default_factory=list)
    match_reason: str | None = None
    recommendation_role: str = "primary"


class RecommendationScore(BaseModel):
    total: float
    ability_fit: float = 0.0
    condition_fit: float = 0.0
    volume_fit: float = 0.0
    goal_fit: float = 0.0
    transition_fit: float = 0.0
    evidence_quality: float = 0.0
    penalties: list[str] = Field(default_factory=list)


class BoardReference(BaseModel):
    brand: str
    model: str


class BoardComparison(BaseModel):
    board_a: BoardReference
    board_b: BoardReference
    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    better_for_board_a: list[str] = Field(default_factory=list)
    better_for_board_b: list[str] = Field(default_factory=list)
    rider_specific_conclusion: str | None = None
    evidence_confidence: float = 0.0
    board_a_dna: dict = Field(default_factory=dict)
    board_b_dna: dict = Field(default_factory=dict)
    dna_tradeoffs: list[str] = Field(default_factory=list)


class VolumeRecommendation(BaseModel):
    target_midpoint_litres: float | None = None
    comfortable_min_litres: float | None = None
    comfortable_max_litres: float | None = None
    performance_min_litres: float | None = None
    forgiving_max_litres: float | None = None
    confidence: float = 0.0
    explanation: str


class TargetVolumeContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_litres: float | None = Field(default=None, alias="targetLitres")
    minimum_litres: float | None = Field(default=None, alias="minimumLitres")
    maximum_litres: float | None = Field(default=None, alias="maximumLitres")
    source: str = "missing"
    confidence: str = "low"


class ProfileExtractionResult(BaseModel):
    profile: RiderProfile
    confidence_by_field: dict[str, float] = Field(default_factory=dict)
    evidence_by_field: dict[str, str] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)


class BoardIntelligenceProfile(BaseModel):
    brand: str
    model: str
    canonical_board_model_id: int | None = None
    category: str | None = None
    subcategory: str | None = None
    ability_min: str | None = None
    ability_ideal: list[str] = Field(default_factory=list)
    wave_size_min_ft: float | None = None
    wave_size_max_ft: float | None = None
    wave_power: list[str] = Field(default_factory=list)
    wave_types: list[str] = Field(default_factory=list)
    paddle_score: float | None = None
    stability_score: float | None = None
    speed_score: float | None = None
    drive_score: float | None = None
    hold_score: float | None = None
    looseness_score: float | None = None
    forgiveness_score: float | None = None
    responsiveness_score: float | None = None
    rocker_profile: str | None = None
    rail_profile: str | None = None
    outline_profile: str | None = None
    tail_profile: str | None = None
    bottom_contours: str | None = None
    quiver_role: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    volume_notes: str | None = None
    sizing_notes: str | None = None
    construction_notes: str | None = None
    evidence_source: str | None = None
    confidence: float = 0.0
    curated: bool = False


class VolumeGuidance(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    minimum_litres: float = Field(alias="minimumLitres")
    maximum_litres: float = Field(alias="maximumLitres")
    target_litres: float | None = Field(default=None, alias="targetLitres")
    label: str
    recommended_category: str = Field(alias="recommendedCategory")
    reasoning: str
    confidence: str | None = None
    board_lane: str | None = Field(default=None, alias="boardLane")


class BodhiRecommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    brand: str
    model: str
    category: str
    fit_label: str | None = Field(default=None, alias="fitLabel")
    short_reason: str | None = Field(default=None, alias="shortReason")
    volume_hint: str | None = Field(default=None, alias="volumeHint")
    availability_label: str | None = Field(default=None, alias="availabilityLabel")
    search_url: str | None = Field(default=None, alias="searchUrl")
    why_it_fits: str | None = Field(default=None, alias="whyItFits")
    design_intent: str | None = Field(default=None, alias="designIntent")
    fin_character: str | None = Field(default=None, alias="finCharacter")
    paddle_and_forgiveness: str | None = Field(default=None, alias="paddleAndForgiveness")
    trade_off: str | None = Field(default=None, alias="tradeOff")
    selection_role: str | None = Field(default=None, alias="selectionRole")
    selection_rationale: str | None = Field(default=None, alias="selectionRationale")
    suggested_volume_or_size_range: str | None = Field(default=None, alias="suggestedVolumeOrSizeRange")
    wave_range: str | None = Field(default=None, alias="waveRange")
    skill_fit: str | None = Field(default=None, alias="skillFit")
    available_count: int = Field(default=0, alias="availableCount")
    region: str | None = None
    fit_score: int | None = Field(default=None, alias="fitScore")
    fit_confidence: str | None = Field(default=None, alias="fitConfidence")
    availability_checked: bool = Field(default=False, alias="availabilityChecked")
    availability_status: str = Field(default="not_checked", alias="availabilityStatus")
    inventory_source: str | None = Field(default=None, alias="inventorySource")
    inventory_match_count: int = Field(default=0, alias="inventoryMatchCount")
    manufacturer_match_count: int = Field(default=0, alias="manufacturerMatchCount")
    retailer_match_count: int = Field(default=0, alias="retailerMatchCount")
    exact_size_inventory_count: int = Field(default=0, alias="exactSizeInventoryCount")
    close_size_inventory_count: int = Field(default=0, alias="closeSizeInventoryCount")
    exact_size_stock: bool = Field(default=False, alias="exactSizeStock")
    model_level_stock: bool = Field(default=False, alias="modelLevelStock")
    region_code: str | None = Field(default=None, alias="regionCode")
    board_model_id: int | None = Field(default=None, alias="boardModelId")
    board_size_id: int | None = Field(default=None, alias="boardSizeId")
    selected_construction: str | None = Field(default=None, alias="selectedConstruction")
    selected_volume_litres: float | None = Field(default=None, alias="selectedVolumeLitres")
    example_product_url: str | None = Field(default=None, alias="exampleProductUrl")
    quivrr_search_url: str | None = Field(default=None, alias="quivrrSearchUrl")
    source_product_url: str | None = Field(default=None, alias="sourceProductUrl")
    source_type: str = Field(default="no_verified_live_source", alias="sourceType")
    price_range: str | None = Field(default=None, alias="priceRange")
    offers: list[RetailerOffer] = Field(default_factory=list)
    volume_delta_litres: float | None = Field(default=None, alias="volumeDeltaLitres")
    selected_size_reason: str | None = Field(default=None, alias="selectedSizeReason")
    volume_compatibility: str | None = Field(default=None, alias="volumeCompatibility")
    confidence: float = 0.0
    authoritative_public_family: str | None = Field(default=None, alias="authoritativePublicFamily")
    detailed_category: str | None = Field(default=None, alias="detailedCategory")
    primary_fin_setup: str | None = Field(default=None, alias="primaryFinSetup")
    alternative_fin_setup: list[str] = Field(default_factory=list, alias="alternativeFinSetup")
    recommendation_lanes: list[str] = Field(default_factory=list, alias="recommendationLanes")
    excluded_recommendation_lanes: list[str] = Field(default_factory=list, alias="excludedRecommendationLanes")
    match_reason: str | None = Field(default=None, alias="matchReason")
    recommendation_role: str = Field(default="primary", alias="recommendationRole")

    @model_validator(mode="before")
    @classmethod
    def populate_compact_reason(cls, values):
        if isinstance(values, dict):
            updates = {}
            if not values.get("whyItFits") and not values.get("why_it_fits"):
                fallback = values.get("shortReason") or values.get("short_reason") or values.get("reason") or values.get("summary")
                if fallback:
                    updates["whyItFits"] = fallback
            if not values.get("sourceType") and not values.get("source_type"):
                updates["sourceType"] = "no_verified_live_source"
            if values.get("confidence") in (None, ""):
                fit_score = values.get("fitScore") or values.get("fit_score")
                if fit_score not in (None, ""):
                    try:
                        numeric = float(fit_score)
                        updates["confidence"] = numeric / 100 if numeric > 1 else numeric
                    except (TypeError, ValueError):
                        updates["confidence"] = 0.0
                else:
                    updates["confidence"] = 0.0
            if updates:
                values = {**values, **updates}
        return values


class BoardGuideMessage(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str


class ClientCapabilities(BaseModel):
    supports_recommendation_cards: bool = Field(default=False, alias="supportsRecommendationCards")
    supports_deep_links: bool = Field(default=False, alias="supportsDeepLinks")


class ConversationState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    last_intent: str | None = Field(default=None, alias="lastIntent")
    active_region: str | None = Field(default=None, alias="activeRegion")
    availability_constraint: str | None = Field(default=None, alias="availabilityConstraint")
    active_profile: dict = Field(default_factory=dict, alias="activeProfile")
    active_board_brief: dict = Field(default_factory=dict, alias="activeBoardBrief")
    active_board: dict | None = Field(default=None, alias="activeBoard")
    last_inventory_query: dict | None = Field(default=None, alias="lastInventoryQuery")
    last_recommendations: list[BodhiRecommendation] = Field(default_factory=list, alias="lastRecommendations")
    mentioned_boards: list[BodhiRecommendation] = Field(default_factory=list, alias="mentionedBoards")
    comparison_boards: list[BodhiRecommendation] = Field(default_factory=list, alias="comparisonBoards")
    last_question: str | None = Field(default=None, alias="lastQuestion")
    conversation_turn: int = Field(default=0, alias="conversationTurn")
    phase: str = "OPEN"
    current_topic: str | None = Field(default=None, alias="currentTopic")
    target_surfer: str = Field(default="account_holder", alias="targetSurfer")
    authenticated: bool = False
    preferred_name: str | None = Field(default=None, alias="preferredName")
    boards_discussed: list[BoardReference] = Field(default_factory=list, alias="boardsDiscussed")
    rejected_recommendations: list[dict[str, str]] = Field(default_factory=list, alias="rejectedRecommendations")
    last_unresolved_question: str | None = Field(default=None, alias="lastUnresolvedQuestion")
    preferred_families: list[str] = Field(default_factory=list, alias="preferredFamilies")
    preferred_fin_setups: list[str] = Field(default_factory=list, alias="preferredFinSetups")
    goals: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list, alias="painPoints")
    budget: str | None = None
    requested_public_family: str | None = Field(default=None, alias="requestedPublicFamily")
    requested_detailed_category: str | None = Field(default=None, alias="requestedDetailedCategory")
    requested_fin_setup: str | None = Field(default=None, alias="requestedFinSetup")
    excluded_public_families: list[str] = Field(default_factory=list, alias="excludedPublicFamilies")
    excluded_detailed_categories: list[str] = Field(default_factory=list, alias="excludedDetailedCategories")
    excluded_fin_setups: list[str] = Field(default_factory=list, alias="excludedFinSetups")
    allow_adjacent_alternatives: bool = Field(default=False, alias="allowAdjacentAlternatives")
    last_rejected_models: list[BoardReference] = Field(default_factory=list, alias="lastRejectedModels")
    last_rejected_family: str | None = Field(default=None, alias="lastRejectedFamily")
    family_correction_reason: str | None = Field(default=None, alias="familyCorrectionReason")
    family_intent_confidence: float = Field(default=0.0, alias="familyIntentConfidence")
    stock_filter_requested: bool = Field(default=False, alias="stockFilterRequested")
    stock_check_offered: bool = Field(default=False, alias="stockCheckOffered")
    stock_check_accepted: bool = Field(default=False, alias="stockCheckAccepted")
    last_presented_category: str | None = Field(default=None, alias="lastPresentedCategory")
    last_presented_models: list[BoardReference] = Field(default_factory=list, alias="lastPresentedModels")
    correction_detected: bool = Field(default=False, alias="correctionDetected")
    previous_outcome: str | None = Field(default=None, alias="previousOutcome")
    previous_search_constraints: dict = Field(default_factory=dict, alias="previousSearchConstraints")
    previous_failure_reason: str | None = Field(default=None, alias="previousFailureReason")
    previous_reply_signature: str | None = Field(default=None, alias="previousReplySignature")
    pending_profile_update: dict | None = Field(default=None, alias="pendingProfileUpdate")
    pending_clarification: dict | None = Field(default=None, alias="pendingClarification")
    surfer_stage: str | None = Field(default=None, alias="surferStage")


class ProfileUpdateProposal(BaseModel):
    """A user-confirmed, allowlisted change for the core My Quivrr profile API."""

    fields: dict[str, object]
    current_values: dict[str, object] = Field(default_factory=dict, alias="currentValues")
    message: str


class FollowUpAction(BaseModel):
    id: str
    label: str
    prompt: str | None = None


class BoardGuideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    region: str | None = None
    page_context: str | None = Field(default=None, alias="pageContext")
    conversation: list[BoardGuideMessage] = Field(default_factory=list)
    intake_state: RiderProfile | None = Field(default=None, alias="intakeState")
    profile: RiderProfile | None = None
    account_profile: RiderProfile | None = None
    conversation_state: ConversationState | None = Field(default=None, alias="conversationState")
    client_capabilities: ClientCapabilities | None = Field(default=None, alias="clientCapabilities")


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
    normalized_intent: str | None = Field(default=None, alias="normalizedIntent")
    legacy_intent: str | None = Field(default=None, alias="legacyIntent")
    intent_confidence: float | None = Field(default=None, alias="intentConfidence")
    intent_entities: dict = Field(default_factory=dict, alias="intentEntities")
    needs_clarification: bool = Field(default=False, alias="needsClarification")
    conversation_profile: RiderProfile | None = Field(default=None, alias="conversationProfile")
    conversation_state: ConversationState | None = Field(default=None, alias="conversationState")
    profile_completeness: float = Field(default=0.0, alias="profileCompleteness")
    profile_conflicts: list[str] = Field(default_factory=list, alias="profileConflicts")
    profile_update_proposal: ProfileUpdateProposal | None = Field(default=None, alias="profileUpdateProposal")
    profile_update_confirmation_requested: bool = Field(default=False, alias="profileUpdateConfirmationRequested")
    volume_recommendation: VolumeRecommendation | None = Field(default=None, alias="volumeRecommendation")
    category: str | None = None
    category_confidence: float | None = Field(default=None, alias="categoryConfidence")
    category_source: str | None = Field(default=None, alias="categorySource")
    comparison: BoardComparison | None = None
    useful_follow_up_questions: list[str] = Field(default_factory=list, alias="usefulFollowUpQuestions")
    follow_up_actions: list[FollowUpAction] = Field(default_factory=list, alias="followUpActions")
    authenticated: bool = False
    profile_loaded: bool = Field(default=False, alias="profileLoaded")
    profile_ability_source: str = Field(default="missing", alias="profileAbilitySource")
    profile_volume_source: str = Field(default="missing", alias="profileVolumeSource")
    profile_weight_source: str = Field(default="missing", alias="profileWeightSource")
    target_volume: TargetVolumeContext | None = Field(default=None, alias="targetVolume")
    model_deployment: str | None = Field(default=None, alias="modelDeployment")
    recommendation_version: str = Field(default="bodhi-sprint-4", alias="recommendationVersion")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    response_mode: str = Field(default="recommendations", alias="responseMode")
    catalogue_match_status: str | None = Field(default=None, alias="catalogueMatchStatus")
    surfer_stage: str | None = Field(default=None, alias="surferStage")
