# Report Generation Prompt Template

This template is used by the ADO Report Agent to instruct Claude Code CLI
to generate an interactive HTML report.

## Variables

The following variables are injected at runtime:

- `{{title}}` — Report title from config
- `{{overallProgress}}` — Overall completion percentage
- `{{generatedBy}}` — Attribution string from config
- `{{outputFile}}` — Target filename for the HTML report

## Prompt

You are a report generation expert. Your task is to create a single-file,
interactive HTML report from the project data provided.

### Input Data

The file `report-data.json` in the current directory contains the full
project report data in JSON format. Read it and use it to generate the report.

### Report Structure

1. **Header**: Report title, generation timestamp, and a prominent overall
   progress bar.

2. **Executive Summary Cards**: Total work items, total tasks,
   completed/in-progress/pending counts as metric cards with icons.

3. **Phase Progress Section**: For each phase:
   - Phase name with configured color accent
   - Phase-level progress bar with percentage
   - Expandable/collapsible list of work items

4. **Work Item Detail** (inside each phase):
   - Work item ID and title
   - Individual progress bar
   - Task breakdown table with color-coded state badges
   - Green = completed, Blue = in progress, Gray = pending

5. **Uncategorized Section**: Work items not matching any phase tag.

6. **Project Summary Footer**: Phase progress chart and health indicator.

### Technical Requirements

- Single HTML file with all CSS/JS inline
- Modern CSS (grid, flexbox, custom properties)
- Responsive design
- Collapsible sections
- Smooth CSS transitions
- Print-friendly styles
- Phase colors from data
- Attribution footer with timestamp
