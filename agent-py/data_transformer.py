from dataclasses import dataclass, field
from typing import Optional
from .config_loader import ReportConfig
from .data_fetcher import WorkItemData


@dataclass
class ClassifiedTask:
    id: int
    title: str
    state: str
    status: str  # "completed" | "in_progress" | "pending"
    assigned_to: Optional[str]


@dataclass
class WorkItemReport:
    id: int
    title: str
    state: str
    assigned_to: Optional[str]
    tags: list[str]
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    progress_percent: int  # 0-100
    tasks: list[ClassifiedTask]


@dataclass
class PhaseReport:
    tag: str
    display_name: str
    color: str
    work_items: list[WorkItemReport]
    total_work_items: int
    completed_work_items: int
    in_progress_work_items: int
    pending_work_items: int
    total_tasks: int
    completed_tasks: int
    progress_percent: int


@dataclass
class ProjectSummary:
    total_work_items: int
    completed_work_items: int
    in_progress_work_items: int
    pending_work_items: int
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    overall_progress_percent: int


@dataclass
class ProjectReport:
    title: str
    generated_at: str
    generated_by: str
    phases: list[PhaseReport]
    summary: ProjectSummary
    uncategorized: list[WorkItemReport]


def transform_data(items: list[WorkItemData], config: ReportConfig) -> ProjectReport:
    from datetime import datetime, timezone

    completed_states = {s.lower() for s in config.completed_states}
    in_progress_states = {s.lower() for s in config.in_progress_states}

    def classify_task(state: str) -> str:
        lower = state.lower()
        if lower in completed_states:
            return "completed"
        if lower in in_progress_states:
            return "in_progress"
        return "pending"

    def build_work_item_report(item: WorkItemData) -> WorkItemReport:
        classified = [
            ClassifiedTask(
                id=t.id,
                title=t.title,
                state=t.state,
                status=classify_task(t.state),
                assigned_to=t.assigned_to,
            )
            for t in item.tasks
        ]
        completed = sum(1 for t in classified if t.status == "completed")
        in_progress = sum(1 for t in classified if t.status == "in_progress")
        pending = sum(1 for t in classified if t.status == "pending")
        total = len(classified)

        return WorkItemReport(
            id=item.id,
            title=item.title,
            state=item.state,
            assigned_to=item.assigned_to,
            tags=item.tags,
            total_tasks=total,
            completed_tasks=completed,
            in_progress_tasks=in_progress,
            pending_tasks=pending,
            progress_percent=round((completed / total) * 100) if total > 0 else 0,
            tasks=classified,
        )

    # Build reports for all items
    all_reports = [build_work_item_report(item) for item in items]

    # Group by phase tags
    phase_tag_set = {p.tag.lower() for p in config.phases}
    phase_map: dict[str, list[WorkItemReport]] = {}
    uncategorized: list[WorkItemReport] = []

    for report in all_reports:
        matched = False
        for tag in report.tags:
            lower = tag.lower()
            if lower in phase_tag_set:
                matched = True
                phase_map.setdefault(lower, []).append(report)
        if not matched:
            uncategorized.append(report)

    # Build phase reports in configured order
    phases: list[PhaseReport] = []
    for phase in config.phases:
        wis = phase_map.get(phase.tag.lower(), [])
        total_tasks = sum(w.total_tasks for w in wis)
        completed_tasks = sum(w.completed_tasks for w in wis)

        phases.append(PhaseReport(
            tag=phase.tag,
            display_name=phase.display_name,
            color=phase.color,
            work_items=wis,
            total_work_items=len(wis),
            completed_work_items=0,
            in_progress_work_items=0,
            pending_work_items=0,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            progress_percent=(
                round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
            ),
        ))

    # Overall progress = average of phase progress percentages
    phases_with_tasks = [p for p in phases if p.total_tasks > 0]
    overall_progress = (
        round(sum(p.progress_percent for p in phases_with_tasks) / len(phases_with_tasks))
        if phases_with_tasks
        else 0
    )

    total_tasks = sum(r.total_tasks for r in all_reports)
    completed_tasks = sum(r.completed_tasks for r in all_reports)
    in_progress_tasks = sum(r.in_progress_tasks for r in all_reports)
    pending_tasks = sum(r.pending_tasks for r in all_reports)

    return ProjectReport(
        title=config.title,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generated_by=config.generated_by,
        phases=phases,
        summary=ProjectSummary(
            total_work_items=len(all_reports),
            completed_work_items=0,
            in_progress_work_items=0,
            pending_work_items=0,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            in_progress_tasks=in_progress_tasks,
            pending_tasks=pending_tasks,
            overall_progress_percent=overall_progress,
        ),
        uncategorized=uncategorized,
    )
