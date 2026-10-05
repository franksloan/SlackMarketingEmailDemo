import base64
from pathlib import Path

from agent.generate_email import render
from agent.models.state import AgentState
from langgraph.types import Command, Send

_HTML_OUTPUT_DIR = Path(__file__).parents[3] / "generated_emails"


def html_generator_node(state: AgentState) -> Command:
    """Renders a single ContentDraft to HTML and chains to html_check."""
    drafts = state.get("drafts", [])
    selected_image = state.get("selected_image")
    _HTML_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load selected image as base64 if one was chosen
    banner_image_b64: str | None = None
    banner_image_filename: str | None = None
    if selected_image and selected_image.get("path"):
        try:
            img_bytes = Path(selected_image["path"]).read_bytes()
            banner_image_b64 = base64.b64encode(img_bytes).decode()
            banner_image_filename = selected_image["filename"]
        except OSError:
            pass

    file_paths: list[str] = []
    for draft in drafts:
        html = render(draft, banner_image_b64=banner_image_b64, banner_image_filename=banner_image_filename)
        path = _HTML_OUTPUT_DIR / f"email_{draft.audience_id}.html"
        path.write_text(html, encoding="utf-8")
        file_paths.append(str(path))

    return Command(
        update={"html_file_paths": file_paths},
        goto=Send("html_check", {"html_file_paths": file_paths}),
    )
