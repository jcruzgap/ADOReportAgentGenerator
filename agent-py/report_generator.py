import os
import json
from dataclasses import asdict
from .config_loader import ReportConfig
from .data_transformer import ProjectReport
from .claude_code import invoke_claude_code


def generate_report(report: ProjectReport, config: ReportConfig) -> str:
    output_dir = os.path.abspath(config.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Write the data file for Claude Code to consume
    data_path = os.path.join(output_dir, "report-data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)

    output_file = config.filename

    # Compose the prompt
    prompt = f"""
You are a report generation expert. Your task is to create a single-file,
interactive HTML report from the project data provided.

## Input Data

The file `report-data.json` in the current directory contains the full
project report data. Read it and use it to generate the report.

## Report Requirements

### Structure
1. **Header**: Report title ("{report.title}"), generation timestamp,
   and a prominent overall progress bar showing {report.summary.overall_progress_percent}% completion.

2. **Executive Summary Cards**: Show total work items, total tasks,
   completed/in-progress/pending counts as metric cards with icons.

3. **Phase Progress Section**: For each phase, display:
   - Phase name with its configured color as accent
   - Phase-level progress bar with percentage
   - Expandable/collapsible list of work items in that phase

4. **Work Item Detail** (inside each phase): For each work item show:
   - Work item ID and title
   - **Completion percentage badge** (e.g. "75%") prominently next to the title,
     derived from `progress_percent` in the data (completed tasks / total tasks * 100).
     Color-code it: green >= 80%, orange 40-79%, red < 40%. Show "N/A" when total_tasks = 0.
   - Individual progress bar (completed tasks / total tasks) with the exact percentage label
   - Task counts inline: e.g. "5 / 8 tasks completed"
   - Task breakdown table: Task ID, Title, State (with color-coded badges), Assigned To
   - Visual indicator: green = completed, blue = in progress, gray = pending

5. **Uncategorized Section**: If any work items don't match a configured phase tag,
   list them in a separate "Uncategorized" section.

6. **Project Summary Footer**:
   - Bar chart or horizontal stacked bars showing progress per phase
   - Overall project health indicator

### Tab Navigation
The report must have **three top-level tabs**:
- **"Overview"** tab -- contains everything described in sections 1-6 above.
- **"Timeline"** tab -- contains the timeline visualisation described below.
- **"Simulation"** tab -- contains the simulation described below.

Render the tabs as a sticky tab bar just below the header. Only one tab's content
is visible at a time; clicking a tab shows its panel and hides the other.

### Timeline Tab
The Timeline tab must contain **two SVG charts** rendered entirely from inline data
(no external libraries):

#### Chart 1 -- Gantt / Phase Schedule
A horizontal Gantt chart spanning all phases:
- X-axis: calendar dates from the earliest `start_date` to the latest `end_date`
  across all phases. Draw monthly tick marks with abbreviated month+year labels.
- Y-axis: one row per phase, labelled with `display_name`.
- Each phase row shows two overlapping horizontal bars:
  - A **light-grey background bar** spanning the full planned duration
    (`start_date` -> `end_date`).
  - A **colored progress bar** (using the phase color) that spans from `start_date`
    to `start_date + (end_date - start_date) * progress_percent / 100`.
- Draw a vertical dashed red line at today's date.
- Show the phase color legend below the chart.

#### Chart 2 -- Actual vs Projected Progress (grouped bar chart)
For each phase compute two values in JavaScript at render time:

  projected_today = clamp(
    (today - start_date_ms) / (end_date_ms - start_date_ms) * 100,
    0, 100
  )
  actual = progress_percent   (from the JSON data)

where `today` is `Date.now()`, `start_date_ms` / `end_date_ms` are
`new Date(phase.start_date).getTime()` / `new Date(phase.end_date).getTime()`.

Render a **grouped bar chart** (inline SVG) with one group per phase:
- Left bar (semi-transparent, phase color at 40% opacity, hatched or lighter fill):
  height = projected_today%. Label it "Expected".
- Right bar (solid phase color):
  height = actual%. Label it "Actual".
- Above each group show a delta badge: "+X%" in green if actual >= projected_today,
  "-X%" in red if actual < projected_today (where X = abs(actual - projected_today),
  rounded to the nearest integer).
- X-axis: phase display names.
- Y-axis: 0-100% with gridlines every 25%.
- A horizontal dashed line at the projected_today value of each group (subtle,
  same color as the expected bar) to make the gap/surplus visually obvious.
- Include a legend: "Expected (at today)" / "Actual".
- Below the chart, render a small summary table with columns:
  Phase | Start | End | Expected % Today | Actual % | Delta

#### Chart 3 -- Actual vs Projected Progress over Time (line chart)
A time-series line chart rendered as inline SVG, showing two lines **per phase**
plotted across the full date range of the project (earliest start_date to latest end_date):

**Projected line** (dashed, phase color, 60% opacity):
- Drawn only within the phase window [start_date, end_date].
- A straight line from (start_date, 0%) to (end_date, 100%).

**Actual line** (solid, phase color, full opacity):
- Drawn only within the phase window [start_date, min(today, end_date)].
- A straight line from (start_date, 0%) to (min(today, end_date), progress_percent).
  This assumes linear accumulation of work from phase start to now.

For phases that have not yet started (start_date > today), draw only the projected
dashed line and skip the actual line.

Axes:
- X-axis: full timeline from earliest start_date to latest end_date, with monthly
  tick marks and abbreviated "Mon YYYY" labels. Draw a vertical dashed red line at today.
- Y-axis: 0% to 100% with horizontal gridlines every 25%.

Additional elements:
- At the actual line endpoint (min(today, end_date), progress_percent), draw a filled
  circle and a small label showing the phase name and actual %.
- At the projected line point corresponding to today (or end_date if past), draw an
  open circle showing the expected %.
- Legend identifying each phase by color.

All three charts must be **responsive** (scale with container width) and include
tooltips or title attributes on interactive elements showing phase name,
dates, and progress values.

### Simulation Tab

#### Active Phase Detection
At render time (JavaScript), determine the **active phase**: the first phase where
`start_date <= today <= end_date`. If no phase is active (today is between phases or
past all phases), display the most recently completed phase instead and note it as
"last completed phase."

#### Scenario Definitions (show this as a styled explanation card above the charts)
Using the active phase data, compute in JavaScript:

  days_total    = (end_date_ms - start_date_ms) / 86400000
  days_elapsed  = (today_ms    - start_date_ms) / 86400000   // clamped >= 1
  days_remaining = days_total - days_elapsed
  current_pct   = phase.progress_percent
  daily_velocity = current_pct / days_elapsed   // % per day at current pace

Then define three velocity multipliers and projected end-states:

  Best case:      velocity = daily_velocity * 1.4
  Most likely:    velocity = daily_velocity * 1.0
  Worst case:     velocity = daily_velocity * 0.6

For each scenario, the projected progress at any future date d (days after today) is:
  projected(d) = min(100, current_pct + velocity * d)

Also compute the estimated completion date for each scenario:
  if velocity > 0:  completion_date = today + (100 - current_pct) / velocity  days
  else:             completion_date = "Not achievable within phase"

Show a **criteria explanation card** (styled info box) above the charts with a table:

  Scenario     | Velocity Multiplier | Assumption
  Best case    | 1.4x current pace   | Team accelerates: resolved blockers, added capacity, or improved efficiency
  Most likely  | 1.0x current pace   | Team maintains the exact pace observed so far in this phase
  Worst case   | 0.6x current pace   | Team slows down: holidays, new blockers, scope creep, or resource constraints

Below the table add one line: "Current daily velocity: X.X% per day
(based on Y days elapsed since phase start)."

#### Three Scenario Charts
Render **three separate inline SVG line charts**, one per scenario, laid out vertically
(or in a responsive grid). Each chart is identical in structure:

X-axis: date range from phase start_date to max(end_date, estimated_completion_date),
  with daily or weekly tick marks and "DD Mon" labels. Extend the X-axis 10% past
  end_date if the scenario does not finish by end_date.
Y-axis: 0% to 100% with gridlines every 25%.

Lines on every chart:
1. **Historical actual** (solid dark line, neutral color): from (start_date, 0%) to
   (today, current_pct). This is the same on all three charts.
2. **Projected scenario line** (solid colored line):
   - Best case: green (#27ae60)
   - Most likely: orange (#e67e22)
   - Worst case: red (#e74c3c)
   From (today, current_pct) forward, plotted day by day until min(100%, x-axis end).
3. **Ideal/planned line** (dashed grey): from (start_date, 0%) to (end_date, 100%).
   This is the planned linear ramp for reference.

Markers:
- Vertical dashed red line at today.
- Vertical dashed grey line at end_date labelled "Deadline".
- Filled circle at (today, current_pct) on the historical line.
- If the scenario reaches 100% before the x-axis end, mark the completion point with
  a star or diamond and label "Est. done: [date]".
- If the scenario does NOT reach 100% by end_date, shade the gap area between the
  projected line and 100% in the scenario color at 10% opacity.

Chart titles:
- "Best Case -- 1.4x velocity (Est. completion: [date])"
- "Most Likely -- Current pace (Est. completion: [date])"
- "Worst Case -- 0.6x velocity (Est. completion: [date] or 'At risk')"

Each chart must have a `title` attribute on SVG elements for tooltips showing exact
values at key points.

### Technical Requirements
- **Single HTML file** -- all CSS and JS inline (no external dependencies)
- Use modern CSS (grid, flexbox, custom properties) for layout
- Responsive design (works on mobile and desktop)
- Collapsible sections using `<details>`/`<summary>` or vanilla JS
- Smooth CSS transitions on progress bars
- Print-friendly styles via `@media print`
- Use the phase colors from the data for theming
- Include a "Generated by {report.generated_by}" footer with timestamp
- Light/dark mode toggle (optional, nice-to-have)

### Chart Rendering
For any charts, use inline SVG generated from the data -- do NOT rely on
external chart libraries. Keep it dependency-free.

## Output
Write the complete HTML file to `./{output_file}`.
Do NOT create any other files. Everything must be in the single HTML file.
"""

    print("Invoking Claude Code to generate the HTML report...")
    result = invoke_claude_code(
        prompt=prompt,
        working_dir=output_dir,
        max_turns=25,
    )

    print(f"[Claude Code output] {result[:500]}")

    report_path = os.path.join(output_dir, output_file)
    if not os.path.exists(report_path):
        print(f"Claude Code did not produce the expected file: {report_path}")
        print(f"Raw report data saved at: {data_path} -- you can use it manually.")
        raise FileNotFoundError(
            f"Claude Code did not produce the expected file: {report_path}"
        )

    # Clean up the data file after successful generation
    if os.path.exists(data_path):
        os.remove(data_path)

    return report_path
