"""Structured Idea curation task owned by APS Core."""

from __future__ import annotations

from ...content_models import IdeaCurationPlan
from ..contracts import AgentTaskSpec


def idea_curation_task(max_input_chars: int, timeout_seconds: int) -> AgentTaskSpec:
    return AgentTaskSpec(
        task_id="ideas.curate-plan",
        mode="workflow",
        instructions=(
            "Organize pending APS Ideas using only the supplied records. Normalize each pending Idea title, "
            "keywords and summary without changing its source ID or meaning. Suggest merge candidates only "
            "for strongly overlapping Ideas and Idea Set candidates only for a coherent reusable group. "
            "Every merge or Set must include at least one pending Idea. Do not invent source IDs, paths, "
            "project facts or implementation details. Return the complete structured curation plan."
        ),
        output_model=IdeaCurationPlan,
        max_steps=1,
        max_input_chars=max_input_chars,
        max_output_chars=200_000,
        timeout_seconds=timeout_seconds,
        validation_attempts=2,
    )
