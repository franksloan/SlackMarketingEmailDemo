import os
from pathlib import Path

from agent.llm import llm
from pydantic import BaseModel, Field

from agent.models.state import AgentState
from agent.tracing import elapsed_ms, save_trace, start_timer

_ASSETS_DIR = Path(__file__).parents[3] / "assets"
_LOGO_FILENAME = "aws-logo.png"
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _discover_images() -> list[dict]:
    """Return metadata for every campaign image in the assets folder (excludes the logo)."""
    images = []
    for entry in sorted(_ASSETS_DIR.iterdir()):
        if entry.is_file() and entry.suffix.lower() in _IMAGE_EXTENSIONS and entry.name != _LOGO_FILENAME:
            images.append({
                "filename": entry.name,
                "path": str(entry),
                "size_kb": round(entry.stat().st_size / 1024, 1),
            })
    return images


class _ImageSelection(BaseModel):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: how each image's filename/content relates to the campaign audience and product"
    )
    selected_filename: str = Field(
        description="Filename of the most appropriate image, chosen from the available list"
    )
    selection_rationale: str = Field(
        description="One-sentence explanation of why this image fits the campaign best"
    )
    alternative_filenames: list[str] = Field(
        description="Other image filenames that could also work, in order of relevance (may be empty)"
    )


_structured = llm.with_structured_output(_ImageSelection)


async def image_selector_node(state: AgentState) -> dict:
    t0 = start_timer()
    images = _discover_images()

    if not images:
        save_trace(
            node="image_selector",
            inputs={"images_found": 0},
            thinking_and_reasoning="No campaign images found in assets folder.",
            outputs={"selected_image": None},
            duration_ms=elapsed_ms(t0),
        )
        return {"selected_image": None, "image_alternatives": []}

    plan = state.get("plan")
    product = state.get("product_lookup")
    product_name = product.product.name if product and product.product else "Unknown product"
    audiences = ", ".join(a.title for a in plan.matched_audiences) if plan else "Unknown"
    tone = plan.tone if plan else "professional"

    image_list = "\n".join(
        f"- {img['filename']} ({img['size_kb']} KB)" for img in images
    )

    prompt = (
        f"You are selecting a banner image for a marketing email campaign.\n\n"
        f"Product: {product_name}\n"
        f"Target audiences: {audiences}\n"
        f"Tone: {tone}\n\n"
        f"Available images in the assets folder:\n{image_list}\n\n"
        f"Choose the single most appropriate image based on its filename and how well it "
        f"fits the product and audience. List any other viable options as alternatives."
    )

    output: _ImageSelection = await _structured.ainvoke(prompt)

    # Validate the selected filename exists in our discovered list
    available = {img["filename"]: img for img in images}
    selected = available.get(output.selected_filename)
    if not selected:
        # LLM hallucinated a filename — fall back to first available
        selected = images[0]

    alternatives = [
        available[fn] for fn in output.alternative_filenames if fn in available and fn != selected["filename"]
    ]

    save_trace(
        node="image_selector",
        inputs={"images_found": len(images), "product": product_name, "audiences": audiences},
        thinking_and_reasoning=output.thinking_and_reasoning,
        outputs={"selected": selected["filename"], "alternatives": [a["filename"] for a in alternatives]},
        duration_ms=elapsed_ms(t0),
    )

    return {
        "selected_image": selected,
        "image_alternatives": alternatives,
    }
