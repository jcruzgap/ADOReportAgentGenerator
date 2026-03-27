import os
import yaml
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PhaseConfig:
    tag: str
    display_name: str
    color: str
    start_date: Optional[str] = None  # ISO date string, e.g. "2026-01-01"
    end_date: Optional[str] = None    # ISO date string, e.g. "2026-04-30"


@dataclass
class ReportConfig:
    ado_organization: str
    ado_project: str
    ado_pat_env_var: str
    wiql: str
    phases: list[PhaseConfig]
    output_dir: str
    filename: str
    title: str
    generated_by: str
    completed_states: list[str]
    in_progress_states: list[str]
    pending_states: list[str]


def load_config(config_path: Optional[str] = None) -> ReportConfig:
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "config", "report-config.yaml"
        )
    config_path = os.path.abspath(config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Validate required fields
    ado = raw.get("ado", {})
    if not ado.get("organization"):
        raise ValueError("Config missing: ado.organization")
    if not ado.get("project"):
        raise ValueError("Config missing: ado.project")

    query = raw.get("query", {})
    if not query.get("wiql"):
        raise ValueError("Config missing: query.wiql")

    phases_raw = raw.get("phases", [])
    if not phases_raw:
        raise ValueError("Config missing: phases (at least one phase required)")

    report = raw.get("report", {})
    task_states = raw.get("task_states", {})

    return ReportConfig(
        ado_organization=ado["organization"],
        ado_project=ado["project"],
        ado_pat_env_var=ado.get("pat_env_var", "ADO_PAT"),
        wiql=query["wiql"],
        phases=[
            PhaseConfig(
                tag=p["tag"],
                display_name=p["display_name"],
                color=p["color"],
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
            )
            for p in phases_raw
        ],
        output_dir=report.get("output_dir", "./output"),
        filename=report.get("filename", "project-report.html"),
        title=report.get("title", "Project Progress Report"),
        generated_by=report.get("generated_by", "ADO Report Agent"),
        completed_states=task_states.get("completed", ["Closed", "Done", "Resolved"]),
        in_progress_states=task_states.get("in_progress", ["Active", "In Progress"]),
        pending_states=task_states.get("pending", ["New", "To Do", "Proposed"]),
    )
