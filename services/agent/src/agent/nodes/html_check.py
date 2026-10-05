from pathlib import Path

from agent.models.state import AgentState

# Elements that every generated email must contain
_REQUIRED_MARKERS = {
    "aws_logo": 'data:image/png;base64,',
    "gradient_banner": 'linear-gradient',
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
            if marker not in content:
                issues.append(f"Missing {name} ({marker!r})")

        results.append({"path": path_str, "passed": len(issues) == 0, "issues": issues})

    return {"html_check_results": results}
