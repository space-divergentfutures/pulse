"""Break content — the light-movement pool and hydration prompts (spec §5a, §5d, §9).

Deliberately gentle. The light layer is *movement snacks, not training* (§9): enough to
stand, move, and reset cerebral blood flow — never fatiguing, so returning to cognitive
work isn't impaired. Doing/rating is honor-based (§5a). The training library
(exercises.json / big_break.json) is a separate, heavier concern for Step 7.

Selection is index-driven (a rotating cursor), not random — the engine forbids
``Math.random``-style nondeterminism so behaviour stays reproducible and testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LightMovement:
    name: str
    detail: str  # a plain form cue / dose — no video, just words (§13)


# The light layer pool (§9). Short, easy, deliberately not fatiguing.
LIGHT_MOVEMENTS: tuple[LightMovement, ...] = (
    LightMovement("Walk it out", "a lap of the room or hallway, 1–2 min"),
    LightMovement("Band pull-aparts", "1 light set, ~15 reps — open up the chest"),
    LightMovement("Couch stretch", "30–45s each side — undo the sitting"),
    LightMovement("Cat–cow", "8–10 slow rounds — mobilise the spine"),
    LightMovement("Thoracic rotations", "6–8 per side — wake up mid-back"),
    LightMovement("Dead hang", "20–45s — decompress the shoulders"),
    LightMovement("Hip / ankle flow", "easy circles, 30–60s — loosen the base"),
    LightMovement("Air squats", "a light set of 10 — blood back to the brain"),
)

# Hydration rides on EVERY break card (§5c, §5d): one line, no logging, no guilt.
HYDRATION_PROMPTS: tuple[str, ...] = (
    "water within reach? a couple of sips",
    "a sip of water while you're up",
    "hydrate — even a few mouthfuls counts",
    "grab the water bottle on your way back",
)


def light_movement_at(index: int) -> LightMovement:
    """Pick a light movement by a rotating cursor (caller owns the cursor)."""
    return LIGHT_MOVEMENTS[index % len(LIGHT_MOVEMENTS)]


def hydration_prompt_at(index: int) -> str:
    return HYDRATION_PROMPTS[index % len(HYDRATION_PROMPTS)]
