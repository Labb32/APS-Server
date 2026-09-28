"""Structured Idea curation task owned by APS Core."""

from __future__ import annotations

from ...content_models import IdeaCurationPlan
from ..contracts import AgentTaskSpec


def idea_curation_task(max_input_chars: int, timeout_seconds: int) -> AgentTaskSpec:
    return AgentTaskSpec(
        task_id="ideas.curate-plan",
        mode="workflow",
        instructions=(
            "Organize pending APS Ideas using only the supplied records. Assign every pending source ID "
            "exactly once to new_ideas, append_candidates or deferred_ideas. Combine strongly overlapping "
            "pending Ideas into one new Idea. Append a pending Idea only when an existing candidate clearly "
            "represents the same Idea. Defer uncertain records with a short reason. Preserve the source "
            "meaning and do not invent IDs, paths, project facts or implementation details. Do not create "
            "Idea Sets. Return the complete structured curation plan."
        ),
        output_model=IdeaCurationPlan,
        max_steps=1,
        max_input_chars=max_input_chars,
        max_output_chars=200_000,
        timeout_seconds=timeout_seconds,
        validation_attempts=2,
    )
