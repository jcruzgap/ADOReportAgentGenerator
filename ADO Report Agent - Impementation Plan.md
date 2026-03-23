# Azure DevOps Project Report Agent — Implementation Plan

## 1. Overview

This agent automates the generation of interactive HTML progress reports from Azure DevOps (ADO) work items. It:

1. Connects to ADO via a custom MCP server using PAT authentication
2. Retrieves work items (and their child tasks) using a configurable WIQL query
3. Groups work items by tags that represent project phases
4. Calculates progress percentages per work item, per phase, and overall
5. Uses Claude Code (CLI) to generate a polished, interactive HTML report

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Orchestrator Agent                     │
│                  (Node.js / TypeScript)                   │
│                                                          │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────┐ │
│  │  Config   │   │  MCP Client  │   │  Claude Code CLI │ │
│  │  Loader   │──▶│  (ADO calls) │──▶│  (Report Gen)    │ │
│  │ (YAML)    │   │              │   │                  │ │
│  └──────────┘   └──────────────┘   └──────────────────┘ │
│        │               │                    │            │
│        ▼               ▼                    ▼            │
│   config.yaml    ADO REST API        report.html        │
│                  (via MCP Server)                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              MCP Server (Standalone Process)              │
│              ado-mcp-server (TypeScript)                  │
│                                                          │
│  Tools exposed:                                          │
│   • ado_execute_wiql  — Run a WIQL query                │
│   • ado_get_work_item — Get single item + relations     │
│   • ado_get_work_item_tasks — Get child tasks of item   │
│   • ado_get_work_items_batch — Bulk fetch by IDs        │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Project Structure

```
ado-report-agent/
├── README.md                         # Setup & usage docs
├── package.json                      # Root monorepo config
├── tsconfig.json
│
├── config/
│   └── report-config.yaml            # User-editable configuration
│
├── mcp-server/                       # MCP Server for ADO
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts                  # Server entry point
│       ├── server.ts                 # MCP server setup & tool registration
│       ├── ado-client.ts             # ADO REST API wrapper (PAT auth)
│       ├── tools/
│       │   ├── execute-wiql.ts       # WIQL query executor tool
│       │   ├── get-work-item.ts      # Single work item fetcher
│       │   ├── get-tasks.ts          # Child-task fetcher
│       │   └── get-batch.ts          # Batch work item fetcher
│       └── types.ts                  # Shared type definitions
│
├── agent/                            # Orchestrator Agent
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts                  # Agent entry point
│       ├── config-loader.ts          # YAML config parser
│       ├── data-fetcher.ts           # MCP client → fetch & assemble data
│       ├── data-transformer.ts       # Group by tags, compute progress
│       ├── report-generator.ts       # Invoke Claude Code CLI
│       ├── claude-code.ts            # Claude Code CLI wrapper
│       └── types.ts                  # Agent-specific types
│
├── templates/                        # Report assets (optional)
│   └── report-prompt.md              # Prompt template for Claude Code
│
└── output/                           # Generated reports land here
    └── .gitkeep
```

---

## 4. Configuration File (`config/report-config.yaml`)

```yaml
# =============================================================
# ADO Report Agent Configuration
# =============================================================

# --- Azure DevOps Connection ---
ado:
  organization: "https://dev.azure.com/YOUR_ORG"
  project: "YOUR_PROJECT"
  pat_env_var: "ADO_PAT"            # Name of env var holding the PAT

# --- Work Item Query ---
query:
  # WIQL query to retrieve top-level work items (User Stories, Features, etc.)
  wiql: |
    SELECT [System.Id], [System.Title], [System.State], [System.Tags]
    FROM WorkItems
    WHERE [System.TeamProject] = @project
      AND [System.WorkItemType] IN ('User Story', 'Feature')
      AND [System.State] <> 'Removed'
    ORDER BY [System.Id] ASC

# --- Phase Tags (used for grouping) ---
# Only work items tagged with these values are included in the report.
# The order here determines the display order in the report.
phases:
  - tag: "Phase 1 - Discovery"
    display_name: "Discovery"
    color: "#4A90D9"
  - tag: "Phase 2 - Design"
    display_name: "Design"
    color: "#7B68EE"
  - tag: "Phase 3 - Development"
    display_name: "Development"
    color: "#50C878"
  - tag: "Phase 4 - Testing"
    display_name: "Testing"
    color: "#FFA500"
  - tag: "Phase 5 - Deployment"
    display_name: "Deployment"
    color: "#FF6347"

# --- Report Output ---
report:
  output_dir: "./output"
  filename: "project-report.html"
  title: "Project Progress Report"
  generated_by: "ADO Report Agent"

# --- Task State Mapping ---
# Maps ADO task states to completed/pending for progress calculation.
task_states:
  completed:
    - "Closed"
    - "Done"
    - "Resolved"
  in_progress:
    - "Active"
    - "In Progress"
  pending:
    - "New"
    - "To Do"
    - "Proposed"
```

---

## 5. Implementation Steps

### Step 1: MCP Server — ADO Client (`mcp-server/src/ado-client.ts`)

**Purpose:** Low-level HTTP wrapper for the ADO REST API authenticated with a PAT.

```typescript
// Key responsibilities:
// - Accept PAT from environment variable
// - Base64-encode PAT for Basic auth header
// - Expose methods: executeWiql(), getWorkItem(), getWorkItemsBatch()
// - Handle pagination, rate limiting, and error responses

import axios, { AxiosInstance } from "axios";

export class AdoClient {
  private http: AxiosInstance;

  constructor(orgUrl: string, project: string, pat: string) {
    this.http = axios.create({
      baseURL: `${orgUrl}/${project}/_apis`,
      headers: {
        Authorization: `Basic ${Buffer.from(`:${pat}`).toString("base64")}`,
        "Content-Type": "application/json",
      },
      params: { "api-version": "7.1" },
    });
  }

  async executeWiql(query: string): Promise<{ id: number }[]> {
    const res = await this.http.post("/wit/wiql", { query });
    return res.data.workItems ?? [];
  }

  async getWorkItem(id: number, expand?: string): Promise<any> {
    const res = await this.http.get(`/wit/workitems/${id}`, {
      params: { $expand: expand ?? "relations" },
    });
    return res.data;
  }

  async getWorkItemsBatch(ids: number[], fields?: string[]): Promise<any[]> {
    // ADO batch API supports max 200 IDs per request
    const chunks = chunkArray(ids, 200);
    const results: any[] = [];
    for (const chunk of chunks) {
      const res = await this.http.post("/wit/workitemsbatch", {
        ids: chunk,
        fields: fields ?? [
          "System.Id", "System.Title", "System.State",
          "System.Tags", "System.WorkItemType",
          "System.AssignedTo", "Microsoft.VSTS.Scheduling.RemainingWork",
        ],
        $expand: "relations",
      });
      results.push(...res.data.value);
    }
    return results;
  }
}
```

### Step 2: MCP Server — Tool Registration (`mcp-server/src/server.ts`)

**Purpose:** Register MCP tools using the `@modelcontextprotocol/sdk`.

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { AdoClient } from "./ado-client.js";

export function createServer(client: AdoClient): McpServer {
  const server = new McpServer({
    name: "ado-mcp-server",
    version: "1.0.0",
  });

  // Tool 1: Execute WIQL
  server.tool(
    "ado_execute_wiql",
    "Execute a WIQL query and return matching work item IDs",
    { query: z.string().describe("The WIQL query string") },
    async ({ query }) => {
      const items = await client.executeWiql(query);
      return {
        content: [{
          type: "text",
          text: JSON.stringify(items),
        }],
      };
    }
  );

  // Tool 2: Get single work item with relations
  server.tool(
    "ado_get_work_item",
    "Fetch a single work item by ID including its relations",
    {
      id: z.number().describe("Work item ID"),
      expand: z.string().optional().describe("Expand option: relations, fields, all"),
    },
    async ({ id, expand }) => {
      const item = await client.getWorkItem(id, expand);
      return {
        content: [{ type: "text", text: JSON.stringify(item) }],
      };
    }
  );

  // Tool 3: Get child tasks of a work item
  server.tool(
    "ado_get_work_item_tasks",
    "Fetch all child tasks of a given parent work item",
    { parentId: z.number().describe("Parent work item ID") },
    async ({ parentId }) => {
      const parent = await client.getWorkItem(parentId, "relations");
      const childLinks = (parent.relations ?? []).filter(
        (r: any) => r.rel === "System.LinkTypes.Hierarchy-Forward"
      );
      const childIds = childLinks.map((r: any) => {
        const url: string = r.url;
        return parseInt(url.substring(url.lastIndexOf("/") + 1), 10);
      });
      if (childIds.length === 0) {
        return { content: [{ type: "text", text: "[]" }] };
      }
      const tasks = await client.getWorkItemsBatch(childIds);
      return {
        content: [{ type: "text", text: JSON.stringify(tasks) }],
      };
    }
  );

  // Tool 4: Batch fetch work items
  server.tool(
    "ado_get_work_items_batch",
    "Fetch multiple work items by their IDs in a single batch call",
    {
      ids: z.array(z.number()).describe("Array of work item IDs"),
      fields: z.array(z.string()).optional().describe("Fields to retrieve"),
    },
    async ({ ids, fields }) => {
      const items = await client.getWorkItemsBatch(ids, fields);
      return {
        content: [{ type: "text", text: JSON.stringify(items) }],
      };
    }
  );

  return server;
}

// Entry point
async function main() {
  const orgUrl = process.env.ADO_ORG_URL!;
  const project = process.env.ADO_PROJECT!;
  const pat = process.env[process.env.ADO_PAT_ENV_VAR ?? "ADO_PAT"]!;

  const client = new AdoClient(orgUrl, project, pat);
  const server = createServer(client);
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
```

### Step 3: Agent — Config Loader (`agent/src/config-loader.ts`)

```typescript
import fs from "fs";
import yaml from "js-yaml";
import path from "path";

export interface PhaseConfig {
  tag: string;
  display_name: string;
  color: string;
}

export interface ReportConfig {
  ado: {
    organization: string;
    project: string;
    pat_env_var: string;
  };
  query: { wiql: string };
  phases: PhaseConfig[];
  report: {
    output_dir: string;
    filename: string;
    title: string;
    generated_by: string;
  };
  task_states: {
    completed: string[];
    in_progress: string[];
    pending: string[];
  };
}

export function loadConfig(configPath?: string): ReportConfig {
  const resolved = configPath ?? path.join(process.cwd(), "config", "report-config.yaml");
  const raw = fs.readFileSync(resolved, "utf-8");
  return yaml.load(raw) as ReportConfig;
}
```

### Step 4: Agent — Data Fetcher (`agent/src/data-fetcher.ts`)

**Purpose:** Use the MCP client SDK to call the ADO MCP server tools and assemble the full data model.

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { ReportConfig } from "./config-loader.js";

export interface TaskInfo {
  id: number;
  title: string;
  state: string;
  assignedTo: string | null;
  remainingWork: number | null;
}

export interface WorkItemData {
  id: number;
  title: string;
  state: string;
  tags: string[];
  assignedTo: string | null;
  tasks: TaskInfo[];
}

export async function fetchAllData(config: ReportConfig): Promise<WorkItemData[]> {
  // 1. Spawn MCP server as child process
  const transport = new StdioClientTransport({
    command: "node",
    args: ["../mcp-server/dist/index.js"],
    env: {
      ...process.env,
      ADO_ORG_URL: config.ado.organization,
      ADO_PROJECT: config.ado.project,
      ADO_PAT_ENV_VAR: config.ado.pat_env_var,
    },
  });

  const client = new Client({ name: "ado-agent", version: "1.0.0" });
  await client.connect(transport);

  try {
    // 2. Execute WIQL to get work item IDs
    const wiqlResult = await client.callTool({
      name: "ado_execute_wiql",
      arguments: { query: config.query.wiql },
    });
    const workItemIds: { id: number }[] = JSON.parse(
      (wiqlResult.content as any)[0].text
    );

    // 3. Batch-fetch all work items
    const ids = workItemIds.map((w) => w.id);
    const batchResult = await client.callTool({
      name: "ado_get_work_items_batch",
      arguments: { ids },
    });
    const rawItems: any[] = JSON.parse(
      (batchResult.content as any)[0].text
    );

    // 4. For each work item, fetch child tasks
    const allData: WorkItemData[] = [];
    for (const item of rawItems) {
      const tasksResult = await client.callTool({
        name: "ado_get_work_item_tasks",
        arguments: { parentId: item.id },
      });
      const rawTasks: any[] = JSON.parse(
        (tasksResult.content as any)[0].text
      );

      allData.push({
        id: item.id,
        title: item.fields["System.Title"],
        state: item.fields["System.State"],
        tags: (item.fields["System.Tags"] ?? "")
          .split(";")
          .map((t: string) => t.trim())
          .filter(Boolean),
        assignedTo: item.fields["System.AssignedTo"]?.displayName ?? null,
        tasks: rawTasks.map((t) => ({
          id: t.id,
          title: t.fields["System.Title"],
          state: t.fields["System.State"],
          assignedTo: t.fields["System.AssignedTo"]?.displayName ?? null,
          remainingWork:
            t.fields["Microsoft.VSTS.Scheduling.RemainingWork"] ?? null,
        })),
      });
    }

    return allData;
  } finally {
    await client.close();
  }
}
```

### Step 5: Agent — Data Transformer (`agent/src/data-transformer.ts`)

**Purpose:** Group work items by phase tags, compute progress metrics.

```typescript
import { ReportConfig, PhaseConfig } from "./config-loader.js";
import { WorkItemData } from "./data-fetcher.js";

export interface WorkItemReport {
  id: number;
  title: string;
  state: string;
  assignedTo: string | null;
  tags: string[];
  totalTasks: number;
  completedTasks: number;
  inProgressTasks: number;
  pendingTasks: number;
  progressPercent: number;   // 0-100
  tasks: {
    id: number;
    title: string;
    state: string;
    status: "completed" | "in_progress" | "pending";
    assignedTo: string | null;
  }[];
}

export interface PhaseReport {
  tag: string;
  displayName: string;
  color: string;
  workItems: WorkItemReport[];
  totalTasks: number;
  completedTasks: number;
  progressPercent: number;
}

export interface ProjectReport {
  title: string;
  generatedAt: string;
  generatedBy: string;
  phases: PhaseReport[];
  summary: {
    totalWorkItems: number;
    totalTasks: number;
    completedTasks: number;
    inProgressTasks: number;
    pendingTasks: number;
    overallProgressPercent: number;
  };
  uncategorized: WorkItemReport[];  // Items not matching any configured phase tag
}

export function transformData(
  items: WorkItemData[],
  config: ReportConfig
): ProjectReport {
  const completedStates = new Set(config.task_states.completed.map(s => s.toLowerCase()));
  const inProgressStates = new Set(config.task_states.in_progress.map(s => s.toLowerCase()));

  // Helper: classify a task state
  function classifyTask(state: string): "completed" | "in_progress" | "pending" {
    const lower = state.toLowerCase();
    if (completedStates.has(lower)) return "completed";
    if (inProgressStates.has(lower)) return "in_progress";
    return "pending";
  }

  // Helper: build WorkItemReport
  function buildWorkItemReport(item: WorkItemData): WorkItemReport {
    const classifiedTasks = item.tasks.map(t => ({
      ...t,
      status: classifyTask(t.state),
    }));
    const completed = classifiedTasks.filter(t => t.status === "completed").length;
    const inProgress = classifiedTasks.filter(t => t.status === "in_progress").length;
    const pending = classifiedTasks.filter(t => t.status === "pending").length;
    const total = classifiedTasks.length;

    return {
      id: item.id,
      title: item.title,
      state: item.state,
      assignedTo: item.assignedTo,
      tags: item.tags,
      totalTasks: total,
      completedTasks: completed,
      inProgressTasks: inProgress,
      pendingTasks: pending,
      progressPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
      tasks: classifiedTasks,
    };
  }

  // Build reports for all items
  const allReports = items.map(buildWorkItemReport);

  // Group by phase tags
  const phaseTagSet = new Set(config.phases.map(p => p.tag.toLowerCase()));
  const phaseMap = new Map<string, WorkItemReport[]>();
  const uncategorized: WorkItemReport[] = [];

  for (const report of allReports) {
    let matched = false;
    for (const tag of report.tags) {
      const lower = tag.toLowerCase();
      if (phaseTagSet.has(lower)) {
        matched = true;
        if (!phaseMap.has(lower)) phaseMap.set(lower, []);
        phaseMap.get(lower)!.push(report);
      }
    }
    if (!matched) uncategorized.push(report);
  }

  // Build phase reports in configured order
  const phases: PhaseReport[] = config.phases.map((phase) => {
    const wis = phaseMap.get(phase.tag.toLowerCase()) ?? [];
    const totalTasks = wis.reduce((s, w) => s + w.totalTasks, 0);
    const completedTasks = wis.reduce((s, w) => s + w.completedTasks, 0);
    return {
      tag: phase.tag,
      displayName: phase.display_name,
      color: phase.color,
      workItems: wis,
      totalTasks,
      completedTasks,
      progressPercent: totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0,
    };
  });

  // Overall summary
  const totalTasks = allReports.reduce((s, w) => s + w.totalTasks, 0);
  const completedTasks = allReports.reduce((s, w) => s + w.completedTasks, 0);
  const inProgressTasks = allReports.reduce((s, w) => s + w.inProgressTasks, 0);
  const pendingTasks = allReports.reduce((s, w) => s + w.pendingTasks, 0);

  return {
    title: config.report.title,
    generatedAt: new Date().toISOString(),
    generatedBy: config.report.generated_by,
    phases,
    summary: {
      totalWorkItems: allReports.length,
      totalTasks,
      completedTasks,
      inProgressTasks,
      pendingTasks,
      overallProgressPercent: totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0,
    },
    uncategorized,
  };
}
```

### Step 6: Agent — Claude Code CLI Wrapper (`agent/src/claude-code.ts`)

**Purpose:** Invoke Claude Code via CLI to generate the HTML report. Uses the host machine's existing Claude CLI authentication.

```typescript
import { execFile } from "child_process";
import { promisify } from "util";
import fs from "fs";
import path from "path";

const execFileAsync = promisify(execFile);

interface ClaudeCodeOptions {
  prompt: string;
  workingDir: string;
  maxTurns?: number;
}

export async function invokeClaudeCode(options: ClaudeCodeOptions): Promise<string> {
  const { prompt, workingDir, maxTurns = 10 } = options;

  // Write prompt to a temp file to avoid shell escaping issues
  const promptFile = path.join(workingDir, ".agent-prompt.md");
  fs.writeFileSync(promptFile, prompt, "utf-8");

  try {
    const { stdout, stderr } = await execFileAsync(
      "claude",
      [
        "--print",                          // Print output, don't open interactive
        "--dangerously-skip-permissions",   // Agent mode — no confirmation prompts
        "--max-turns", String(maxTurns),
        "--input-file", promptFile,
      ],
      {
        cwd: workingDir,
        maxBuffer: 50 * 1024 * 1024, // 50 MB buffer for large outputs
        timeout: 300_000,            // 5 min timeout
      }
    );

    if (stderr) console.warn("[claude-code stderr]", stderr);
    return stdout;
  } finally {
    // Clean up temp prompt file
    fs.unlinkSync(promptFile);
  }
}
```

### Step 7: Agent — Report Generator (`agent/src/report-generator.ts`)

**Purpose:** Compose the prompt for Claude Code and trigger HTML report generation.

```typescript
import fs from "fs";
import path from "path";
import { ProjectReport } from "./data-transformer.js";
import { ReportConfig } from "./config-loader.js";
import { invokeClaudeCode } from "./claude-code.js";

export async function generateReport(
  report: ProjectReport,
  config: ReportConfig
): Promise<string> {
  const outputDir = path.resolve(config.report.output_dir);
  fs.mkdirSync(outputDir, { recursive: true });

  // Write the data file for Claude Code to consume
  const dataPath = path.join(outputDir, "report-data.json");
  fs.writeFileSync(dataPath, JSON.stringify(report, null, 2), "utf-8");

  const outputFile = config.report.filename;

  // Compose the prompt
  const prompt = `
You are a report generation expert. Your task is to create a single-file, 
interactive HTML report from the project data provided.

## Input Data

The file \`report-data.json\` in the current directory contains the full 
project report data. Read it and use it to generate the report.

## Report Requirements

### Structure
1. **Header**: Report title ("${report.title}"), generation timestamp, 
   and a prominent overall progress bar showing ${report.summary.overallProgressPercent}% completion.

2. **Executive Summary Cards**: Show total work items, total tasks, 
   completed/in-progress/pending counts as metric cards with icons.

3. **Phase Progress Section**: For each phase, display:
   - Phase name with its configured color as accent
   - Phase-level progress bar with percentage
   - Expandable/collapsible list of work items in that phase

4. **Work Item Detail** (inside each phase): For each work item show:
   - Work item ID and title
   - Individual progress bar (completed tasks / total tasks)
   - Task breakdown table: Task ID, Title, State (with color-coded badges), Assigned To
   - Visual indicator: green = completed, blue = in progress, gray = pending

5. **Uncategorized Section**: If any work items don't match a configured phase tag, 
   list them in a separate "Uncategorized" section.

6. **Project Summary Footer**: 
   - Bar chart or horizontal stacked bars showing progress per phase
   - Overall project health indicator

### Technical Requirements
- **Single HTML file** — all CSS and JS inline (no external dependencies)
- Use modern CSS (grid, flexbox, custom properties) for layout
- Responsive design (works on mobile and desktop)
- Collapsible sections using \`<details>\`/\`<summary>\` or vanilla JS
- Smooth CSS transitions on progress bars
- Print-friendly styles via \`@media print\`
- Use the phase colors from the data for theming
- Include a "Generated by ${report.generatedBy}" footer with timestamp
- Light/dark mode toggle (optional, nice-to-have)

### Chart Rendering
For any charts, use inline SVG generated from the data — do NOT rely on 
external chart libraries. Keep it dependency-free.

## Output
Write the complete HTML file to \`./${outputFile}\`.
Do NOT create any other files. Everything must be in the single HTML file.
`;

  console.log("Invoking Claude Code to generate the HTML report...");
  const result = await invokeClaudeCode({
    prompt,
    workingDir: outputDir,
    maxTurns: 15,
  });

  console.log("[Claude Code output]", result.substring(0, 500));

  const reportPath = path.join(outputDir, outputFile);
  if (!fs.existsSync(reportPath)) {
    throw new Error(
      `Claude Code did not produce the expected file: ${reportPath}`
    );
  }

  return reportPath;
}
```

### Step 8: Agent — Main Orchestrator (`agent/src/index.ts`)

```typescript
import { loadConfig } from "./config-loader.js";
import { fetchAllData } from "./data-fetcher.js";
import { transformData } from "./data-transformer.js";
import { generateReport } from "./report-generator.js";

async function main() {
  const configPath = process.argv[2]; // Optional: custom config path
  console.log("Loading configuration...");
  const config = loadConfig(configPath);

  console.log(`Connecting to ADO: ${config.ado.organization}/${config.ado.project}`);
  console.log("Fetching work items via MCP server...");
  const rawData = await fetchAllData(config);
  console.log(`Fetched ${rawData.length} work items`);

  console.log("Transforming data and computing progress...");
  const report = transformData(rawData, config);
  console.log(`Phases: ${report.phases.map(p => p.displayName).join(", ")}`);
  console.log(`Overall progress: ${report.summary.overallProgressPercent}%`);

  console.log("Generating interactive HTML report via Claude Code...");
  const reportPath = await generateReport(report, config);

  console.log(`\n✅ Report generated successfully: ${reportPath}`);
  console.log(`Open it in your browser: file://${reportPath}`);
}

main().catch((err) => {
  console.error("Agent failed:", err);
  process.exit(1);
});
```

---

## 6. Dependencies

### MCP Server (`mcp-server/package.json`)

```json
{
  "name": "ado-mcp-server",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.0",
    "axios": "^1.7.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "@types/node": "^22.0.0"
  }
}
```

### Agent (`agent/package.json`)

```json
{
  "name": "ado-report-agent",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "report": "npm run build && node dist/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.0",
    "js-yaml": "^4.1.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "@types/js-yaml": "^4.0.9",
    "@types/node": "^22.0.0"
  }
}
```

---

## 7. Prerequisites & Environment Setup

### System Requirements

| Requirement          | Version / Details                                    |
|----------------------|------------------------------------------------------|
| Node.js              | >= 20.x LTS                                          |
| npm                  | >= 10.x                                              |
| TypeScript           | >= 5.5                                               |
| Claude CLI           | Latest (`claude` command available and authenticated) |
| Azure DevOps PAT     | Scopes: `Work Items (Read)` at minimum               |

### Environment Variables

```bash
# Required
export ADO_PAT="your-personal-access-token-here"

# The following are read from config.yaml but can also be env vars:
# ADO_ORG_URL, ADO_PROJECT
```

### Claude CLI Authentication

The agent assumes the user running it has already authenticated with Claude CLI:

```bash
# Verify Claude CLI is authenticated
claude --version
claude --print "Hello"   # Should return a response without auth errors
```

---

## 8. Build & Run Instructions

```bash
# 1. Clone and install
cd ado-report-agent
npm install --workspaces    # If using npm workspaces, or install each separately

# 2. Build MCP server
cd mcp-server
npm run build
cd ..

# 3. Build agent
cd agent
npm run build
cd ..

# 4. Configure
cp config/report-config.yaml config/report-config.yaml.bak
# Edit config/report-config.yaml with your ADO org, project, PAT env var, WIQL, and phases

# 5. Set PAT
export ADO_PAT="your-pat-here"

# 6. Run
cd agent
npm run report

# Or with a custom config path:
node dist/index.js /path/to/custom-config.yaml
```

---

## 9. Testing Strategy

### Unit Tests

| Component            | What to Test                                                |
|----------------------|-------------------------------------------------------------|
| `config-loader`      | Valid YAML parsing, missing fields, defaults                |
| `data-transformer`   | Progress calculation, tag grouping, edge cases (0 tasks)    |
| `ado-client`         | Mock HTTP responses, pagination, auth header construction   |

### Integration Tests

| Test                          | Description                                           |
|-------------------------------|-------------------------------------------------------|
| MCP Server smoke test         | Start server, call each tool with mock ADO responses  |
| Agent → MCP round-trip        | Agent spawns MCP server, fetches mock data end-to-end |
| Claude Code invocation        | Verify prompt file creation and CLI execution          |

### Manual Validation

- Run against a real ADO project with known data
- Verify HTML report opens correctly in Chrome, Firefox, Safari
- Check responsive layout at mobile widths
- Validate progress percentages against manual count
- Test with work items that have no tasks (0/0 edge case)
- Test with work items not matching any phase tag (uncategorized)

---

## 10. Error Handling & Edge Cases

| Scenario                         | Handling                                                   |
|----------------------------------|------------------------------------------------------------|
| PAT expired or invalid           | Catch 401, log clear message with re-auth instructions     |
| WIQL returns 0 results           | Generate report with "No work items found" message         |
| Work item has 0 child tasks      | Show 0% progress with "No tasks" indicator                 |
| Work item belongs to 2+ phases   | Include it in ALL matching phases (note in report)         |
| ADO rate limiting (429)          | Exponential backoff with max 3 retries                     |
| Claude Code fails or times out   | Retry once; if still fails, save raw JSON for manual use   |
| MCP server process crash         | Catch spawn errors, log, and exit with actionable message  |
| Network timeout                  | 30s timeout per ADO API call, retry logic in ado-client    |

---

## 11. Future Enhancements

- **Scheduled runs**: Add cron/GitHub Actions workflow to generate daily reports
- **Delta reports**: Compare current report with previous run, highlight changes
- **Email delivery**: Auto-send the HTML report to stakeholders via SMTP
- **Multiple projects**: Support array of projects in config, generate combined report
- **Custom fields**: Allow config to specify additional ADO fields to include
- **Export formats**: PDF export via Puppeteer, Markdown summary
- **Caching layer**: Cache ADO responses to speed up re-runs during development
- **Webhook trigger**: Start report generation on ADO work item state changes