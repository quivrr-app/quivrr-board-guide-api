"""Governed surfer-stage safety gates used before volume and catalogue ranking."""
from __future__ import annotations

from dataclasses import dataclass
import re


STAGE_1 = "STAGE_1_TRUE_BEGINNER"
STAGE_2 = "STAGE_2_PROGRESSING_BEGINNER"
STAGE_3 = "STAGE_3_EARLY_INTERMEDIATE"
STAGE_4 = "STAGE_4_INTERMEDIATE"
STAGE_5 = "STAGE_5_ADVANCED"
STAGE_6 = "STAGE_6_EXPERT"

STAGE_LABELS = {
    STAGE_1: "True beginner", STAGE_2: "Progressing beginner", STAGE_3: "Early intermediate",
    STAGE_4: "Intermediate", STAGE_5: "Advanced", STAGE_6: "Expert",
}
BEGINNER_QUESTION = "No problem. Are you still learning to stand in the whitewater, or can you already catch green waves and ride along the face?"
PREMIUM_BEGINNER_POSITIONING = (
    "Quivrr focuses on premium hardboards from established surfboard manufacturers—boards designed to be surfed regularly and kept in a quiver for years. "
    "We do not currently catalogue foamies or surf-school softboards, even though one may be the safest first board."
)


@dataclass(frozen=True)
class StageAssessment:
    stage: str | None
    source: str
    confidence: float
    clarification_required: bool = False

    @property
    def guidance_only(self) -> bool:
        return self.stage == STAGE_1


def assess_surfer_stage(message: str, ability: str | None, pending: dict | None = None) -> StageAssessment:
    text = (message or "").lower().replace("’", "'")
    if pending and pending.get("type") == "surfer_stage":
        source = "clarification_answer"
    else:
        source = "current_message"
    if re.search(r"\b(?:never surfed|only surfed (?:once|twice)|whitewater|white water|still learning to stand|can(?:not|'t) consistently stand|can't catch green|cannot catch green)\b", text):
        return StageAssessment(STAGE_1, source, .98)
    if re.search(r"\b(?:catch(?:ing)? green waves sometimes|stand(?:ing)? regularly|ride along the face sometimes|go down the line sometimes|angle takeoffs? sometimes)\b", text):
        return StageAssessment(STAGE_2, source, .92)
    if re.search(r"\b(?:catch green waves consistently|ride along the face consistently|basic turns?|turn a little|trim both directions|paddle and position)\b", text):
        return StageAssessment(STAGE_3, source, .9)
    if re.search(r"\b(?:bottom turn|cutbacks?)\b", text):
        return StageAssessment(STAGE_4, source, .94)
    if re.search(r"\b(?:overhead reef|advanced surfer|advanced)\b", text):
        return StageAssessment(STAGE_5, source, .9)
    if re.search(r"\b(?:expert|professional|pro surfer)\b", text):
        return StageAssessment(STAGE_6, source, .9)
    ability_key = (ability or "").lower()
    says_beginner = bool(re.search(r"\b(?:beginner|begginner|new to surfing|learning to surf)\b", text)) or ability_key == "beginner"
    if says_beginner:
        return StageAssessment(None, "ambiguous_beginner", .8, clarification_required=True)
    if "progressing" in ability_key:
        return StageAssessment(STAGE_2, "profile_ability", .6)
    if "intermediate" in ability_key:
        return StageAssessment(STAGE_4, "profile_ability", .6)
    if ability_key == "advanced":
        return StageAssessment(STAGE_5, "profile_ability", .7)
    if ability_key == "expert":
        return StageAssessment(STAGE_6, "profile_ability", .7)
    return StageAssessment(None, "not_applicable", 0.0)


def stage_allows_board(stage: str | None, board) -> bool:
    """Hard exclusion gate. It must run before ranking or inventory enrichment."""
    if stage not in {STAGE_2, STAGE_3}:
        return stage != STAGE_1
    family = " ".join(str(value or "").lower() for value in (
        getattr(board, "authoritative_public_family", None), getattr(board, "detailed_category", None),
        getattr(board, "category", None), getattr(board, "skill_fit", None),
    ))
    unsafe = ("performance shortboard", "performance daily", "step up", "semi gun", "gun", "performance fish", "technical fish", "performance twin")
    if any(token in family for token in unsafe):
        return False
    if stage == STAGE_2 and any(token in family for token in ("advanced", "expert", "competition", "high performance")):
        return False
    return any(token in family for token in ("hybrid", "daily", "mid", "fish", "groveller", "longboard", "forgiving"))


def beginner_guidance(stage: str, weight_kg: int | None, saved_volume_ignored: bool) -> str:
    weight = f"At {weight_kg:g} kg, " if weight_kg else ""
    ignored = " Your saved board-volume reference is not being used as the target for this beginner scenario." if saved_volume_ignored else ""
    if stage == STAGE_1:
        return (
            "Because you are still learning, I would not recommend a performance daily driver or shortboard. "
            f"{weight}prioritise a long, wide, stable beginner board with easy paddling and glide—often an 8'0-class softboard or a large mini-mal. "
            f"{PREMIUM_BEGINNER_POSITIONING} {ignored} "
            "Once you are catching green waves consistently and riding along the face, I can help with a forgiving premium hardboard transition option."
        )
    return (
        f"{weight}you are at the transition stage, so length, width, stability and paddle support matter more than a precise litre target. "
        "I will only consider forgiving hybrids, daily drivers or mid-lengths that pass the stage-safety gate. "
        f"{PREMIUM_BEGINNER_POSITIONING}{ignored}"
    )
