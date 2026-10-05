from pathlib import Path

from agent.models.state import AgentState

# Elements that every generated email must contain.
# Values can be a single string (must be present) or a list of strings (at least one must be present).
_REQUIRED_MARKERS: dict[str, str | list[str]] = {
    "aws_logo": 'data:image/png;base64,',
    # Banner is either a CSS gradient (no image selected) or an embedded <img> (image selected)
    "banner": ['linear-gradient', 'border-radius:8px'],
    "cta_link": '<a ',
    "footer_legal": 'Amazon Web Services',
}


def html_check_node(state: AgentState) -> dict:
    """Deterministic node: validates each saved HTML file for required structure."""
    file_paths = state.get("html_file_paths", [])

    results: list[dict] = []
    for path_str in file_paths:
        path = Path(path_str)
        issues: list[str] = []

        if not path.exists():
            issues.append(f"File not found: {path_str}")
            results.append({"path": path_str, "passed": False, "issues": issues})
            continue

        content = path.read_text(encoding="utf-8")
        for name, marker in _REQUIRED_MARKERS.items():
            if isinstance(marker, list):
                if not any(m in content for m in marker):
                    issues.append(f"Missing {name} (expected one of: {marker})")
            elif marker not in content:
                issues.append(f"Missing {name} ({marker!r})")

        results.append({"path": path_str, "passed": len(issues) == 0, "issues": issues})

    return {"html_check_results": results}
