"""Editor node — makes targeted in-place edits to an existing draft based on marketer feedback.

Handles both text changes and image swaps. The LLM is given the current image and the list
of available alternatives (loaded from campaign state) so it can swap if the feedback asks for it.
"""
from agent.llm import llm
from pydantic import BaseModel, Field

from agent.models.draft import ContentDraft
from agent.models.state import AgentState
from agent.tracing import elapsed_ms, save_trace, start_timer


class _EditOutput(ContentDraft):
    thinking_and_reasoning: str = Field(
        description=(
            "Step-by-step reasoning: which fields were changed, why each change addresses "
            "the feedback, and what was deliberately kept the same"
        )
    )
    swap_image: bool = Field(
        description="True if the feedback asks for a different banner image"
    )
    new_image_filename: str | None = Field(
        default=None,
        description=(
            "Filename of the replacement image, chosen from the alternatives list. "
            "Only set when swap_image=True and alternatives are available."
        ),
    )


_structured = llm.with_structured_output(_EditOutput)


async def editor_node(state: AgentState) -> dict:
    t0 = start_timer()
    feedback = state["feedback"]
    draft = state["existing_draft"]
    current_image: dict | None = state.get("selected_image")
    alternatives: list[dict] = state.get("image_alternatives") or []

    current_image_info = (
        f"Current banner image: {current_image['filename']}"
        if current_image
        else "Current banner image: none (gradient placeholder)"
    )
    alternatives_info = (
        "Available alternative images:\n"
        + "\n".join(f"  - {a['filename']}" for a in alternatives)
        if alternatives
        else "No alternative images available."
    )

    prompt = (
        f"You are an expert marketing editor.\n"
        f"Make targeted edits to the draft below based on the marketer's feedback.\n"
        f"Only change what the feedback asks for. Keep everything else identical.\n\n"
        f"Marketer feedback:\n{feedback}\n\n"
        f"Original draft (JSON):\n{draft.model_dump_json(indent=2)}\n\n"
        f"{current_image_info}\n"
        f"{alternatives_info}\n\n"
        f"If the feedback asks for a different image, set swap_image=true and pick "
        f"new_image_filename from the alternatives list above. "
        f"If no alternatives exist, set swap_image=false.\n"
        f"Return the complete edited draft. audience_id must remain '{draft.audience_id}'."
    )

    output: _EditOutput = await _structured.ainvoke(prompt)
    edited = ContentDraft(
        **{
            k: v
            for k, v in output.model_dump().items()
            if k not in ("thinking_and_reasoning", "swap_image", "new_image_filename")
        }
    )

    result: dict = {"drafts": [edited]}

    # Apply image swap if requested and the filename is valid
    if output.swap_image and output.new_image_filename:
        new_image = next(
            (a for a in alternatives if a["filename"] == output.new_image_filename), None
        )
        if new_image:
            result["selected_image"] = new_image

    save_trace(
        node="editor",
        inputs={
            "audience_id": draft.audience_id,
            "feedback": feedback,
            "current_image": current_image["filename"] if current_image else None,
            "alternatives": [a["filename"] for a in alternatives],
        },
        thinking_and_reasoning=output.thinking_and_reasoning,
        outputs={
            "draft": edited,
            "swap_image": output.swap_image,
            "new_image": output.new_image_filename,
        },
        duration_ms=elapsed_ms(t0),
        label=draft.audience_id,
    )
    return result
