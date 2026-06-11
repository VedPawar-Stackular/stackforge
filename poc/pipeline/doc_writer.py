"""
SDLC document writer.

After the pipeline extracts requirements, call write_sdlc_docs() to produce one
.md file per SDLC topic in poc/output/{project_id}/.

No LLM calls — requirements are already structured data; this is pure formatting.
"""

import os
from datetime import datetime

from config import SDLC_TOPICS
from db import DB

_POC_ROOT = os.path.dirname(os.path.dirname(__file__))

_TOPIC_LABELS = {
    "requirements":     "Functional Requirements & User Needs",
    "design":           "UI/UX Design & Components",
    "technical":        "Technical Architecture & Infrastructure",
    "timeline":         "Timeline, Phases & Milestones",
    "budget":           "Budget & Resource Allocation",
    "testing":          "Testing & Quality Assurance",
    "integrations":     "Third-Party Integrations & External APIs",
    "team_and_process": "Team, Roles & Process",
}

_TYPE_LABELS = {
    "functional":     "Functional Requirements",
    "non_functional": "Non-Functional Requirements",
    "constraint":     "Constraints",
    "assumption":     "Assumptions",
}


def get_output_dir(project_id: str) -> str:
    return os.path.join(_POC_ROOT, "output", project_id)


def get_doc_path(project_id: str, topic: str) -> str:
    return os.path.join(get_output_dir(project_id), f"{topic}.md")


def write_sdlc_docs(project_id: str, project_name: str) -> str:
    """
    Fetch all requirements for project_id, write one .md per SDLC topic.
    Returns the absolute path to the output directory.
    """
    with DB() as db:
        rows = db.fetch_all(
            "SELECT req_type, sdlc_topic, title, description, confidence "
            "FROM requirements WHERE project_id = %s ORDER BY sdlc_topic, confidence DESC",
            (project_id,),
        )

    grouped: dict[str, list] = {t: [] for t in SDLC_TOPICS}
    for r in rows:
        topic = r.get("sdlc_topic") or "requirements"
        grouped.setdefault(topic, []).append(r)

    # Cross-cutting items appended to design.md only: non-functional and
    # constraint requirements from any other topic (they affect UI decisions —
    # accessibility, performance budgets, compliance, platform rules) plus all
    # integration requirements (external APIs imply specific screens/flows).
    # Items already tagged sdlc_topic='design' are excluded to avoid duplication.
    design_cross_cutting = [
        r for r in rows
        if r.get("sdlc_topic") != "design"
        and (
            r.get("req_type") in ("non_functional", "constraint")
            or r.get("sdlc_topic") == "integrations"
        )
    ]

    output_dir = get_output_dir(project_id)
    os.makedirs(output_dir, exist_ok=True)

    for topic in SDLC_TOPICS:
        extra = design_cross_cutting if topic == "design" else []
        content = _render_topic_doc(topic, grouped.get(topic, []), project_name, cross_cutting=extra)
        path = get_doc_path(project_id, topic)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    return output_dir


def _render_topic_doc(
    topic: str,
    requirements: list,
    project_name: str,
    cross_cutting: list | None = None,
) -> str:
    label = _TOPIC_LABELS.get(topic, topic.replace("_", " ").title())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {project_name} — {label}",
        "",
        f"> **SDLC Category:** `{topic}`  |  **Generated:** {timestamp}",
        "",
        "---",
        "",
    ]

    if not requirements:
        lines.append("*No requirements extracted in this category.*")
        lines.append("")
    else:
        # Group within the topic by req_type
        by_type: dict[str, list] = {}
        for r in requirements:
            by_type.setdefault(r["req_type"], []).append(r)

        # Emit in a consistent order
        for req_type in ["functional", "non_functional", "constraint", "assumption"]:
            items = by_type.get(req_type, [])
            if not items:
                continue
            section_label = _TYPE_LABELS.get(req_type, req_type.replace("_", " ").title())
            lines.append(f"## {section_label}")
            lines.append("")
            for r in items:
                conf_pct = f"{r['confidence']:.0%}"
                lines.append(f"### {r['title']}")
                lines.append("")
                lines.append(r["description"])
                lines.append("")
                lines.append(f"- **Confidence:** {conf_pct}")
                lines.append(f"- **Type:** {req_type.replace('_', ' ')}")
                lines.append("")

    # Append cross-cutting context for design.md — non-functional, constraint,
    # and integration requirements from other topics that affect UI/UX decisions.
    if cross_cutting:
        lines += [
            "---",
            "",
            "## Cross-cutting Context",
            "",
            "> Requirements from other SDLC areas that constrain or inform UI design "
            "(non-functional requirements, constraints, and integration dependencies).",
            "",
        ]
        by_topic: dict[str, list] = {}
        for r in cross_cutting:
            src = r.get("sdlc_topic") or "requirements"
            by_topic.setdefault(src, []).append(r)

        for src_topic, items in sorted(by_topic.items()):
            src_label = _TOPIC_LABELS.get(src_topic, src_topic.replace("_", " ").title())
            lines.append(f"### {src_label}")
            lines.append("")
            for r in items:
                req_type = r.get("req_type", "")
                type_tag = f"`{req_type.replace('_', ' ')}`" if req_type else ""
                lines.append(f"**{r['title']}** {type_tag}")
                lines.append("")
                lines.append(r["description"])
                lines.append("")

    return "\n".join(lines)
