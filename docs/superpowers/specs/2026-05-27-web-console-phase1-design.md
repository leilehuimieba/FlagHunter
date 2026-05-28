# FlagHunter Web Console Phase 1 Redesign Design

**Date:** 2026-05-27  
**Project:** `D:\webstudy\FlagHunter`  
**Scope:** Web Console phase 1 redesign for `Dashboard + Tasks + Topbar / global state`

---

## 1. Problem Statement

The current Web Console already has a usable frontend shell and a real backend API layer, but the core operator experience is still inconsistent:

- the task conversation area is too narrow and loses priority to the side panel
- the main workflow is split between real backend data and mock-driven fallback behavior
- homepage, task detail, and global connection state do not present a single trustworthy model
- the user cannot reliably tell which actions are truly supported and which are only UI placeholders

This redesign is not a cosmetic refresh. Phase 1 turns the console into a trustworthy, usable operator-facing control surface centered on real task execution.

---

## 2. Product Goal

Phase 1 should deliver a **minimum usable control console** with these properties:

- homepage is trustworthy, even when data is empty
- task list and task detail are driven primarily by real backend responses
- task detail becomes the primary workspace
- conversation-first reading and operator input are comfortable on both laptops and desktop displays
- global state, live state, and unavailable state are clearly distinguished
- mock data is no longer required for the main workflow to function

The redesign explicitly favors operational clarity over decorative richness.

---

## 3. Phase Boundaries

### 3.1 Phase 1 includes

Phase 1 covers only the main workflow slice:

- `Topbar / global state / shell-level status`
- `Dashboard`
- `Tasks list + task detail`

Relevant frontend files include:

- `D:\webstudy\FlagHunter\web\console\src\app.jsx`
- `D:\webstudy\FlagHunter\web\console\src\shell.jsx`
- `D:\webstudy\FlagHunter\web\console\src\components.jsx`
- `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx`
- `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`
- `D:\webstudy\FlagHunter\web\console\src\api.js`
- `D:\webstudy\FlagHunter\web\console\src\styles.css`

Relevant backend file:

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

### 3.2 Phase 1 explicitly excludes

Phase 1 does **not** include a full redesign of:

- `Traces`
- `Knowledge`
- `Logs`
- `Memory`
- `Settings`

These pages may receive compatibility adjustments only. They are not the primary redesign targets.

### 3.3 Phase 2 direction

Phase 2 builds on the stabilized main workflow and extends the same principles to:

- trace truthification and readability
- knowledge / logs / memory / settings data consistency
- broader mock removal
- deeper backend view-model stabilization

---

## 4. Success Criteria

Phase 1 is successful when all of the following are true:

1. **Homepage is trustworthy**
   - `Dashboard` uses real backend data when available
   - when data is absent, the UI shows clear empty or unavailable states instead of mock-driven visual filler

2. **Task workflow is complete**
   - the operator can create a task
   - open a task
   - read the task detail
   - observe real updates

3. **Conversation area is materially improved**
   - on a typical laptop-width viewport around 1280px, the message area is no longer cramped
   - on desktop widths above 1440px, space is used for productivity rather than empty padding

4. **Dual-mode detail layout works**
   - default mode is conversation-first
   - an analysis-first mode exists for operators who need the side context visible
   - the two modes are meaningfully different, not only CSS width tweaks

5. **Main workflow no longer depends on mock data**
   - `Dashboard`
   - `Tasks list`
   - `Task detail`
   - `Topbar/global state`
   all work without mock data as their default source of truth

---

## 5. Interaction Principles

Phase 1 should follow four structural principles:

### 5.1 Primary workspace always wins

The primary workspace is the active task, its conversation, its state, and the operator actions around it. Any panel that compresses the reading and input area must become secondary, collapsible, or on-demand.

### 5.2 Homepage is for entry; task detail is for work

`Dashboard` should help the user decide where to go next.  
`Task detail` should be where the user actually works.

### 5.3 Live state should have a single user-facing interpretation

The interface must consistently express:

- backend connected / disconnected
- event stream active / reconnecting / stale
- action available / unavailable / unsupported

The user should not have to infer these states from scattered badges or fallback behavior.

### 5.4 Responsive behavior means re-prioritization, not shrinking

Different viewport widths should change which panels are simultaneously visible. They should not merely scale everything down until the primary workspace becomes unreadable.

---

## 6. Page Structure Design

## 6.1 Sidebar

The sidebar remains navigation-focused.

### Sidebar keeps

- route navigation
- active route highlight
- lightweight global badges if helpful

### Sidebar avoids

- long-form runtime explanation
- dense live/mock explanations
- detailed workflow context that belongs in the main workspace or topbar

Reason: sidebar width is structurally limited and should not compete with task detail width.

---

## 6.2 Topbar / Global Status

The topbar becomes the single cross-page control and status bar.

### Topbar responsibilities

1. **Current context**
   - current page title
   - breadcrumb leaf
   - current task id / run id when inside task detail

2. **System state**
   - backend connected / disconnected / degraded
   - live stream active / reconnecting / idle
   - running task count when available

3. **Quick actions**
   - new task
   - command palette / search
   - return to task list
   - detail mode toggle in task detail

The topbar becomes the visible source of truth for the console’s global status model.

---

## 6.3 Dashboard

Dashboard changes from a “dense demo board” into a “trustworthy overview and routing page”.

### Dashboard structure

1. **Header**
   - title
   - short summary
   - primary action: create task
   - only actions that are actually supported

2. **Core health row**
   A reduced KPI set focused on:
   - running
   - tasks today
   - success rate
   - token/tool usage
   - flags captured

3. **Recent activity**
   Focused sections for:
   - recent tasks
   - recent tool calls
   - alerts / flags

4. **Chart policy**
   - show charts only when real data exists
   - otherwise show explicit empty states
   - avoid using mock-backed charts to create artificial dashboard richness

### Dashboard purpose after redesign

Dashboard should answer four operator questions quickly:

- Is the system online?
- Is work actively happening?
- Were there recent useful outcomes or warnings?
- Where should I go next?

---

## 6.4 Tasks Page

The tasks page becomes the main operator workspace and is split conceptually into:

1. **Task list selector**
2. **Task detail workspace**

### Task list role

The task list is for:

- browsing
- filtering
- switching tasks
- creating a task

It is not the primary reading surface.

### Task detail role

The detail workspace is for:

- reading messages
- tracking execution state
- sending hints or future continue-style input
- viewing attachments, notes, knowledge hits, and observations
- jumping to trace only when deeper inspection is needed

---

## 7. Task Detail Dual-Mode Design

Task detail supports two operator modes.

### 7.1 Default mode: Conversation-first

This is the default experience and should serve most active usage.

#### Layout intent

- task list remains available as a selector
- message area becomes the dominant visual region
- side context is collapsed, summarized, or shown via on-demand panels

#### Best for

- reading long agent output
- watching live execution
- injecting hints
- staying focused on a single task stream

### 7.2 Secondary mode: Analysis-first

This mode is for users who need persistent context alongside the conversation.

#### Layout intent

- message area stays central but yields more width to the right-hand analysis panel
- analysis panel shows grouped context such as:
  - plan
  - observations
  - knowledge hits
  - notes
  - attachments
  - current strategy / tool context when available

#### Best for

- post-run review
- correlating conversation with plan and evidence
- debugging task execution behavior
- research-heavy operator sessions

### 7.3 Mode change requirements

The two modes must differ in three ways:

1. **Visibility**
   - conversation-first hides or minimizes secondary context
   - analysis-first keeps more context visible

2. **Interaction placement**
   - conversation-first emphasizes compact toggles and drawers
   - analysis-first emphasizes persistent side context

3. **Reading behavior**
   - conversation-first prioritizes scrolling, reading, and input comfort
   - analysis-first prioritizes simultaneous multi-panel visibility

---

## 8. Task Detail Internal Information Hierarchy

The current task detail header contains multiple classes of information mixed together. Phase 1 reorganizes it into three layers:

### 8.1 Identity layer

- status
- detected type
- task id
- run id

### 8.2 Description layer

- title
- target
- goal

### 8.3 Runtime summary layer

- started time
- tokens
- tool calls
- final flag
- stop reason

This makes the header scannable and reduces the feeling of one long metadata ribbon.

### 8.4 Message region

The message region becomes the primary container and should optimize for:

- width
- stable vertical reading
- clear distinction between user / agent / system messages
- readable long-form content
- low-friction operator input

### 8.5 Composer

The composer should remain fixed and legible near the bottom of the detail workspace and should make availability obvious:

- if action is supported, show it clearly
- if not supported, disable it with accurate explanation

### 8.6 Side context grouping

The right-side analysis content should be grouped into:

1. **Execution context**
   - plan
   - strategy / current tool context where available

2. **Observed activity**
   - observations
   - live event summaries

3. **Supporting evidence**
   - knowledge hits
   - notes
   - attachments

This is more readable than a long unstructured stack of cards.

---

## 9. Responsive Strategy

### 9.1 Desktop widths (1440px and above)

- keep task list visible
- let conversation-first and analysis-first both operate fully
- show full right analysis panel in analysis-first mode

### 9.2 Common laptop widths (~1280px)

- keep sidebar compact
- keep task list narrow
- default to conversation-first mode
- move analysis content into drawer / overlay behavior instead of permanently compressing the message region

### 9.3 Narrower windows

Phase 1 does not target full mobile design, but it should still avoid:

- unreadable horizontal overflow
- inaccessible actions
- permanent multi-column compression

---

## 10. Current Real Data Surface

The backend already exposes a workable live surface through:

- `GET /api/status`
- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/hint`
- `GET /api/dashboard/summary`
- `GET /api/traces`
- `GET /api/traces/{runId}`
- `GET /api/events/stream`
- `GET /api/tasks/{taskId}/attachments`
- `POST /api/tasks/{taskId}/attachments`

Phase 1 should build around this real API surface rather than around mock-driven simulation.

---

## 11. Data Contract Design

## 11.1 Main contract rules

Phase 1 uses two allowed states for the main workflow:

1. **Real data**
2. **Trustworthy empty / unavailable state**

It should not use mock data to impersonate current live operational truth.

### 11.2 Task detail as single source of truth

`GET /api/tasks/{taskId}` becomes the primary full-detail source for task detail pages.

It should reliably provide:

#### Identity and status

- `id`
- `title`
- `target`
- `goal`
- `status`
- `detectedType`
- `currentRunId`
- `createdAt`
- `startedAt`
- `finishedAt`
- `tokensUsed`
- `toolCalls`
- `finalFlag`
- `stopReason`

#### Detail content

- `messages`
- `detailSource`
- `plan`
- `notes`
- `knowledgeHits`
- `attachments`

#### Capability declaration

Add or stabilize:

```json
{
  "capabilities": {
    "hint": true,
    "stop": true,
    "continue": false,
    "retry": false,
    "attachments": true
  }
}
```

This lets the frontend render interaction states based on explicit backend support rather than guessing from missing functions or mock fallbacks.

### 11.3 SSE role

`/api/events/stream` should be treated as an incremental update stream, not as the only truth source.

Use:

- `getTask(taskId)` for baseline truth
- SSE for incremental state, note, knowledge, and tool updates

This keeps the frontend model understandable and recoverable.

### 11.4 Dashboard contract behavior

`GET /api/dashboard/summary` can remain the main homepage API if it guarantees:

- stable keys
- numeric defaults
- empty arrays instead of omitted collections
- truthful absence instead of simulated richness

---

## 12. Mock Cleanup Strategy

Phase 1 does **not** require deleting every mock artifact from the repository. It requires removing mock dependence from the main workflow.

### 12.1 Remove mock from main-entry rendering

Highest-priority cleanup targets:

- `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx`
- `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`

Specific behaviors to remove from default operator flow:

- `MOCK.DASHBOARD`
- `offlineFlags()`
- `task_002`
- `MOCK.TASKS`
- `MOCK.MESSAGES_002`
- `MOCK.TASK_002_PANEL`

### 12.2 Keep fallback only as explicit degradation

Some synthetic logic may remain temporarily, such as:

- metrics-derived message reconstruction
- synthetic fallback messages

But these may only serve as explicit degraded states. They may not remain the normal happy path for the main workflow.

### 12.3 Reposition mock as developer support

If `mock.js` remains after phase 1, it should serve:

- local isolated UI development
- non-live preview
- design sandboxing

It should no longer silently define the product’s default operational story.

---

## 13. Required Backend Adaptations

Phase 1 should minimize backend churn, but the following adaptations are worth doing:

### 13.1 Add explicit task detail capabilities

Frontend currently expects interaction states such as continue and retry. These should be declared by backend contract rather than guessed in UI logic.

### 13.2 Stabilize task detail payload meaning

The task detail payload should be structurally stable enough that frontend pages do not need to reconstruct core meaning from many separate fallback branches.

### 13.3 Preserve trustworthy empty semantics

For dashboard and task detail responses:

- no data should return empty values
- unsupported actions should be explicit
- partial observability should be declared as partial, not hidden behind demo-like filler

### 13.4 No large backend redesign required

Phase 1 does **not** require a new service layer or major protocol redesign. The existing `web_server.py` API surface is already sufficient for the first slice, with targeted payload improvements.

---

## 14. Implementation Staging

Phase 1 should be executed in four stages.

## Stage 1: Truth-source convergence

### Goal

Make the main workflow consume stable real sources and trustworthy degradation paths.

### Work

- stabilize task detail payload
- add capability declarations
- make dashboard empty-state behavior explicit
- ensure SSE remains incremental
- make frontend consume real sources first and only degrade explicitly

### Outcome

The UI begins telling the truth even before full layout redesign lands.

---

## Stage 2: Topbar / shell / global status unification

### Goal

Unify user-facing state language across pages.

### Work

- consolidate connection state expression
- reduce duplicated or conflicting live/mock semantics
- promote key actions to topbar
- establish one visible state model for connected / reconnecting / unavailable / degraded

### Outcome

The product feels coherent at the platform level, not only at individual-page level.

---

## Stage 3: Dashboard truthification

### Goal

Convert dashboard into a trustworthy overview.

### Work

- remove mock as the default dashboard experience
- simplify cards and chart priority
- show truthful empty states
- keep navigation into tasks clear

### Outcome

Homepage becomes operationally useful without pretending to know more than the backend actually knows.

---

## Stage 4: Tasks workspace redesign

### Goal

Turn tasks into the primary operator workspace.

### Work

- remove mock task-detail dependency from the default path
- restructure header, message area, composer, and side context
- implement conversation-first and analysis-first modes
- align UI availability with backend-declared capabilities
- reduce synthetic fallback from default behavior to explicit degraded behavior

### Outcome

The core pain point is solved: the operator can work comfortably in task detail using real data.

---

## 15. Risk Control

### 15.1 Avoid CSS-first redesign before contract stabilization

If layout changes land before detail payload and capability rules stabilize, component logic will likely be rewritten twice.

### 15.2 Avoid leaving fallback on the happy path

Mock and synthetic fallback should not continue masquerading as normal live experience.

### 15.3 Avoid shallow mode switching

Dual-mode task detail must not be only a width toggle. It must change visibility, interaction placement, and reading behavior.

### 15.4 Avoid multi-page state vocabulary drift

Dashboard, Tasks, and Topbar must not each invent separate meanings for “live”, “connected”, or “available”.

### 15.5 Avoid one-shot Tasks megarefactor

The tasks redesign must still be staged internally:

1. truthify data consumption
2. reorganize structure
3. add dual-mode behavior
4. refine UX details

---

## 16. Validation Strategy

Validation should happen per stage rather than only at the end.

### Stage 1 validation

- `/api/status`
- `/api/tasks`
- `/api/tasks/{taskId}`
- `/api/dashboard/summary`
- `/api/events/stream`

Verify:

- field stability
- explicit empty states
- capability correctness

### Stage 2 validation

Verify:

- topbar state consistency
- reconnect and degraded-state clarity
- no contradictory state signals across pages

### Stage 3 validation

Verify:

- dashboard behaves correctly with real data, no data, and partial data
- main entry does not depend on mock content

### Stage 4 validation

Verify:

- task creation and selection remain stable
- task detail reads real messages and detail payload
- dual modes materially improve usability
- laptop-width reading experience is visibly improved
- analysis context no longer permanently crushes the main message area

---

## 17. Decision Checklist

The following decisions are already locked for phase 1:

- use a **main-workflow vertical slice** rather than a pure UI-only or pure data-only project
- prioritize `Dashboard + Tasks + Topbar/global state`
- design for **desktop + laptop responsive support**
- make task detail support **dual modes**
- use **conversation-first** as the default mode
- treat `getTask(taskId)` as the **task detail source of truth**
- treat SSE as **incremental**, not full truth
- remove mock dependence from the main workflow rather than demanding total repository-wide deletion in phase 1

---

## 18. Final Summary

Phase 1 redesign turns the current Web Console from a partly simulated interface into a trustworthy operator surface. It does this by:

- clarifying scope
- promoting the task detail workspace
- defining responsive dual-mode behavior
- grounding the main workflow in real backend data
- reducing mock behavior to explicit fallback only
- sequencing implementation to reduce rework

The intended end state of phase 1 is a console where the operator can trust what they see, work comfortably in the task detail view, and understand the system’s live state without guesswork.

---

## 19. Design Part 5: Final Design Summary and Decision Register

This section is the condensed recovery layer for future work. If conversation context is compressed later, this section should be enough to quickly restore the essential design intent and the decisions that must remain fixed during planning and implementation.

### 19.1 Final design summary

This redesign is not a narrow visual refresh. It is a controlled conversion of the current Web Console from a partially simulated, partially live interface into a **trustworthy operator console** built around real task execution.

The redesign solves four core problem classes:

1. **Task detail hierarchy is inverted**
   - the conversation stream is currently compressed by secondary side content
   - the operator’s primary workspace does not visibly dominate the page

2. **Main workflow truth is mixed**
   - dashboard, task list, and task detail still contain mock-driven paths
   - the operator cannot reliably infer what is live versus reconstructed

3. **Global state is not expressed consistently**
   - connected, live, unavailable, and degraded meanings are distributed across pages and components
   - system trust depends too much on user inference

4. **Common laptop-width usage is not well supported**
   - the current layout wastes priority on secondary content
   - resizing alone is not enough; the console needs structural reprioritization

The target end state of phase 1 is therefore:

- trustworthy homepage
- trustworthy topbar/global state model
- real-data-driven task list and task detail
- conversation-first default working mode
- analysis-first optional mode
- responsive behavior that serves both desktop and laptop use
- a main workflow that no longer depends on mock data to function

### 19.2 Locked design decisions

The following decisions are already approved and should be treated as locked unless the project explicitly reopens design scope:

#### Decision 1: redesign strategy

Use a **main-workflow vertical-slice redesign**, not a UI-only refresh and not a data-only backend cleanup.

#### Decision 2: phase 1 scope

Phase 1 is limited to:

- `Topbar / global state / shell`
- `Dashboard`
- `Tasks list + task detail`

#### Decision 3: phase 1 outcome target

Phase 1 must deliver a **minimum usable control console** that is trustworthy, usable, and primarily real-data-driven.

#### Decision 4: task workflow priority

`Tasks` is the highest-priority page in phase 1 because it is the primary work surface, not merely a navigation or reporting page.

#### Decision 5: task detail layout model

Task detail must support **dual modes**:

- default: **conversation-first**
- alternate: **analysis-first**

#### Decision 6: responsive target

Phase 1 is designed for **desktop + laptop** usage together, with laptop usability treated as a first-class requirement rather than a degraded afterthought.

#### Decision 7: task detail truth source

`GET /api/tasks/{taskId}` is the single primary truth source for task detail baseline rendering.

#### Decision 8: interaction capability declaration

Frontend must not infer support for actions such as continue / retry / hint / stop through mock logic or missing-function heuristics. Backend should declare supported capabilities explicitly.

#### Decision 9: SSE role

`/api/events/stream` is an **incremental update mechanism**, not the sole source of complete page truth.

#### Decision 10: main workflow data policy

The main workflow may render only:

1. real data
2. trustworthy empty, unavailable, or degraded states

It must not use mock content to impersonate current live truth.

#### Decision 11: dashboard role

Dashboard is a **trustworthy overview and routing surface**, not a dense demo board and not a BI-style page that depends on visual filler.

#### Decision 12: mock cleanup strategy

Phase 1 does not require deleting every mock artifact from the repository. It does require removing mock dependency from the default operator path.

#### Decision 13: phase 2 deferral

The following remain primarily phase-2 concerns:

- deep `Traces` redesign
- broader `Knowledge / Logs / Memory / Settings` truthification
- broader repository-wide mock retirement
- deeper backend view-model convergence outside the main workflow slice

### 19.3 Implementation constraints derived from the design

The following constraints must be respected when writing the implementation plan:

1. **Do not redesign layout before stabilizing truth sources**
   - data contract and capability rules should be clear before major structural UI edits

2. **Do not let fallback remain on the happy path**
   - fallback may exist only as explicit degradation, not as normal runtime presentation

3. **Do not implement dual mode as a cosmetic width toggle**
   - it must affect visibility, interaction placement, and reading behavior

4. **Do not let page-level state vocabulary drift**
   - Dashboard, Tasks, and Topbar must share one meaning for connected, live, degraded, and unavailable

5. **Do not treat Tasks redesign as one giant undifferentiated refactor**
   - task data truthification, layout restructuring, mode behavior, and polish should still be staged internally

### 19.4 Why this design is ready for planning

The design is ready to enter implementation planning because the following are already resolved:

- what phase 1 does
- what phase 1 does not do
- which page is the primary workspace
- how task detail should behave structurally
- which data source is authoritative
- how SSE should be used
- how mock retirement should be interpreted
- which risks must be controlled during delivery

### 19.5 One-sentence project intent

Phase 1 turns the FlagHunter Web Console into a **real-data-centered, conversation-first, state-trustworthy minimum usable control console** for active task execution.

---

## 20. Follow-on Addendum: Settings MCP add server (2026-05-28)

This addendum freezes the next **post-phase-1 live wiring slice** for the Web Console Settings page.  
It does **not** reopen the earlier phase-1 scope debate. It records the approved minimal design for the next truthful management action.

### 20.1 Goal

Turn the Settings `MCP` section from a read-only placeholder into a **minimum live action surface** that can:

1. read the actual configured MCP server list
2. add a new **SSE MCP server**
3. refresh the Settings page from the returned live payload

This is explicitly a **minimum connection slice**, not a full MCP management console.

### 20.2 Locked scope

#### Included in this slice

- `GET /api/settings` returns the real MCP configured server list
- new `POST /api/settings/mcp/servers` endpoint
- Settings page inline add form
- SSE server creation with the minimum fields:
  - `name`
  - `url`
- success path refreshes Settings state from the returned payload

#### Excluded from this slice

- `stdio` server creation
- bearer token input
- edit / delete
- connect-test / health-test
- auto reconnect
- folding add-server into the existing global `Save changes` flow

### 20.3 Product decisions

#### Decision 1: first version is SSE-only

The first live version supports only **SSE MCP servers** because it has the smallest useful operator surface and fits the current Web Console management use case best.

#### Decision 2: add-server is an independent action

Adding an MCP server is **not** part of Settings partial save.  
Reason: it writes MCP server configuration state rather than env-backed Settings fields.

#### Decision 3: UI uses an inline form, not a modal

The first version should expand an inline form directly inside the Settings `MCP` section.  
This keeps state handling small and avoids unnecessary interaction overhead.

#### Decision 4: `mcp.servers` becomes an object list

The Settings payload should expose MCP servers as objects, not plain strings.  
Minimum recommended shape:

```json
{
  "name": "docs-mcp",
  "type": "sse",
  "url": "http://127.0.0.1:8080/sse",
  "enabled": true,
  "connected": false
}
```

This keeps the first version honest while avoiding another contract break when future actions are added.

#### Decision 5: duplicate names overwrite by name

The first version preserves the current `MCPManager.add_sse_server(...)` behavior:

- same `name`
- latest request wins

No duplicate warning or confirmation dialog is required in this slice.

### 20.4 Backend contract

#### Read contract

`GET /api/settings`

The `mcp` portion should contain:

```json
{
  "enabled": true,
  "timeoutMs": 30000,
  "servers": [
    {
      "name": "docs-mcp",
      "type": "sse",
      "url": "http://127.0.0.1:8080/sse",
      "enabled": true,
      "connected": false
    }
  ]
}
```

#### Write contract

`POST /api/settings/mcp/servers`

Request body:

```json
{
  "name": "docs-mcp",
  "url": "http://127.0.0.1:8080/sse"
}
```

Success response:

```json
{
  "ok": true,
  "settings": {}
}
```

Where `settings` is the latest full Settings payload after the write succeeds.

#### Validation rules

Minimum validation only:

- `name` must be non-empty after trim
- `url` must be non-empty after trim
- `url` must start with `http://` or `https://`

#### Error rules

- `400` for invalid JSON or invalid request fields
- `500` for internal save / read failures

#### Missing config file policy

If `mcp_servers.json` does not yet exist, the add-server path should create it through the existing MCP manager save path. This is a normal first-write flow, not an error condition.

### 20.5 Frontend interaction contract

In `Settings -> MCP`:

1. show the real configured server list
2. enable `＋ 添加服务器` only when:
   - connection is `connected` or `degraded`
   - `window.API.addMcpServer` exists
3. clicking `＋ 添加服务器` expands an inline form
4. first-version fields:
   - `name`
   - `url`
5. clicking save:
   - calls `window.API.addMcpServer(...)`
6. on success:
   - close the inline form
   - refresh current Settings state from `result.settings`
7. on failure:
   - keep typed values
   - show an inline error

#### Availability copy rules

Use the same truthful capability copy policy already established elsewhere:

- not connected -> `c.notConnected`
- API not wired -> `c.notWired`

Do **not** keep the old permanent read-only placeholder wording for this action once the live contract is wired.

### 20.6 TDD boundary for execution

The implementation plan for this slice must verify only the minimum useful behavior:

1. `GET /api/settings` exposes real MCP servers
2. `POST /api/settings/mcp/servers` writes a new SSE server
3. invalid payload returns `400`
4. Settings frontend binds the add-server UI to the live API contract

This slice should continue the repository’s current testing strategy:

- backend contract tests in `pytest`
- frontend source-level contract tests
- no new browser E2E requirement for the first iteration
