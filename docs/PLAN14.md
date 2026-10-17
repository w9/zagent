# PLAN14: Artifacts in the Conversation

**Status:** implemented; see [Recorded findings](#recorded-findings)
**Depends on:** [PLAN3](PLAN3.md) for view specs and the view stack, [PLAN7](PLAN7.md) for drafts
and chat references, [PLAN8](PLAN8.md) for MCP Apps, [DESIGN.md](DESIGN.md) for the components.
**Shippable outcome:** every table, chart, draft and job the agent publishes appears as a card in
the conversation, where it was published. Any card can be maximized into the right panel and
minimized back. The right panel exists only while something is maximized.

---

## Goal

The working surface treated the right panel as the default home of everything the agent published.
The panel was always open, followed the newest view, and the conversation held only links to it.
The result was two places to look, and a panel that often showed something unrelated to the
message being read.

This increment reverses that. Published content, now called an **artifact**, lives in the
conversation as a card next to the turn that produced it. Small artifacts (charts, job cards, the
job grid) are live in the card. Large ones (tables, draft forms) show a preview. Maximizing a card
gives it the whole right panel; minimizing returns it to the card. With nothing maximized, the
panel collapses and the conversation uses the full width.

The vocabulary changes with the design: views become artifacts in the UI, the client, the event
log, the projections, the schemas and the HTTP routes. What the model sees does not change: the
`push_view` tool, its schema and description, the receipts with `view_id`, the `view:` link scheme
and the `view-0001` identifier format all stay, so no cassette is re-recorded.

---

## What you can see when it's done

A replayed session on a desktop screen:

1. Ask for this week's northgate specimens. The answer has a **Table** card under the agent's
   steps, showing the first five rows and "5 of 14 rows shown". The right panel is not there; the
   conversation is full width. A small **Artifacts** list floats under the conversation header's
   right corner.
2. Click **Maximize** on the card, or the table's entry in the artifact list. The right panel opens
   beside the conversation with the whole table. The card shrinks to a placeholder that says
   "Shown in panel", and the artifact list hides.
3. Ask for a coverage chart. A live chart card appears. Maximizing it replaces the table in the
   panel; the table's card returns to its preview.
4. Click **Minimize** in the panel header. The panel collapses and the chart card is live again.
5. Ask for an analysis draft, maximize it, edit and confirm. The panel switches to the live job
   card that the confirmation published.
6. Refresh. The maximized artifact is still maximized, because it is in the URL.

On a phone or tablet the same steps work, except that maximizing takes over the workspace, the
panel header's **Minimize** returns to the conversation, and the artifact list is an
"N artifacts" button in the conversation header that opens a menu.

---

## Scope

### Artifact cards

- Every published artifact gets one card in the conversation, at the position of its
  `artifact_published` event. Cards published during a run of agent steps are placed after the
  run, so a turn's steps stay together.
- A card shows the artifact's kind, title and a **Maximize** button, then an inline rendering:

| Kind | Inline | Maximized |
|---|---|---|
| `table` | First five rows, counts, **Show all rows** | Full table |
| `chart` | Live chart | Live chart |
| `draft_form` | Application, version, status, specimen query, first parameters, validation count, **Open draft** | Draft editor |
| `job_card`, `job_grid` (MCP App) | Live, compact layout (`displayMode: inline`) | Live, full layout (`displayMode: fullscreen`) |

- While an artifact is maximized, its card collapses to a placeholder (icon, title, "Shown in
  panel", **Minimize**), so live state is never rendered twice.
- Step summaries and `view:` links in answers maximize the artifact they name.
- Only the maximized artifact holds an event stream. Inline MCP Apps poll their data while the
  card is near the viewport and stop once every job has finished, so neither a long conversation
  nor a second tab uses up the browser's connections.

### The maximized panel

- One artifact at a time. The header has the artifact's title, its kind and **Minimize**. The
  previous, next and history controls are gone: the conversation and the artifact list are the
  history.
- On desktop the panel sits beside the conversation and is resizable; the conversation's share is
  remembered as before. Below desktop it replaces the conversation; the Conversation and Working
  surface tabs are gone.
- `?artifact=<id>` in the URL means maximized. It survives refresh and history navigation. An ID
  the session does not have shows an "Artifact unavailable" notice with **Minimize**. The `view`
  and `panel` search parameters are removed.
- Nothing is maximized automatically when the agent publishes. The one exception is user
  initiated: confirming a maximized draft replaces it with the job card the confirmation
  published. The confirm response carries that card's `artifact_id`.

### The artifact list

- Shown when the session has artifacts and none is maximized.
- It belongs to the conversation header. Where the conversation is wide enough to leave room
  beside the transcript (`@xwide`, 1152px), it is a small card floating under the header's right
  corner: a count, one entry per artifact with its kind icon and title, and a **Collapse** button.
  It scrolls after a few entries. Collapsed, it is an "N artifacts" button that expands it again,
  and the choice is remembered. In narrower conversations (phones, tablets, desktop windows with
  a wide sidebar) it is an "N artifacts" button in the header that opens a menu, so it never
  covers the transcript.
- Choosing an entry maximizes it.

### MCP Apps display modes

- The host sends `displayMode` (`inline` on a card, `fullscreen` when maximized) and
  `availableDisplayModes: ["inline", "fullscreen"]` in the host context.
- `ui/request-display-mode` from an app maximizes or minimizes its artifact.
- Inline frames take the height the app reports, up to a cap; the jobs app switches to a compact
  layout inline: status, progress and elapsed time per job, with **Show log** asking for
  `fullscreen`.

### The rename

| Before | After |
|---|---|
| `view_pushed {view_id, spec}` | `artifact_published {artifact_id, spec}` |
| draft `view_id` | draft `artifact_id` |
| projection `views` | projection `artifacts` |
| event schema v2 | v3; v1 and v2 rows are translated on read and stay unchanged in storage |
| `zagent/views.py`, `zagent/view_schemas/` | `zagent/artifacts.py`, `zagent/artifact_schemas/` |
| `/sessions/:id/views/:view_id/{app,data,updates}` | `/sessions/:id/artifacts/:artifact_id/{app,data,updates}` |
| privacy paths `view_spec`, `view_interaction` | `artifact_spec`, `artifact_interaction` |
| `components/surface/` (`WorkingSurface`, `ViewRenderer`, `ViewReference`) | `components/artifact/` (`ArtifactCard`, `ArtifactPanel`, `ArtifactList`, `ArtifactRenderer`) |
| `?view=…&panel=surface` | `?artifact=…` |

Kept for the model: the `push_view` tool and its schema classes, receipts with `view_id`, error
text returned to the model, the `view:` link scheme, the `view-NNNN` identifiers, and the draft
JSON added to the model's context (still keyed `view_id`). Requirement and case IDs such as
`REQ-VIEW-03` and `VIEW-001` are identifiers and stay.

---

## Out of scope

| Item | Where |
|---|---|
| Renaming the model-facing tool and receipts | needs a re-record; a later plan |
| Several artifacts maximized at once, or picture-in-picture | not a goal |
| Agent control over maximizing | not a goal; the user decides |
| Pinning, renaming or deleting artifacts | later |
| Operational data | [PLAN15](#after-this) |

---

## Key decisions

**The conversation is the history.** A view stack with its own navigation duplicated the
transcript's order in a second place. Cards keep each artifact next to the question that produced
it, and the artifact list indexes them.

**Never move the user's focus unasked.** Following the newest view meant the panel changed while
the user read something else. Publishing now only adds a card. Confirming a draft is the user's
own action, so following it to the job card is not a surprise.

**Render live state once.** A maximized artifact's card becomes a placeholder. A draft being edited
or a job log being followed exists in one place, and inline frames do not duplicate feeds.

**Preview what is large, keep live what is small.** A chart or a job card fits a card and is more
useful live. A table or a form does not, and a preview with a clear way to open it reads better
than a scrolling box inside a scrolling transcript.

**Use the protocol's display modes.** MCP Apps already define `inline` and `fullscreen`. Reporting
them lets an app adapt its layout, and honoring `ui/request-display-mode` lets an app ask for room
in the same way a user would.

**Rename everything the model does not see.** The replay cassettes are keyed by the full model
request. Renaming the tool or its receipts would invalidate all of them and change model behavior
in evals; renaming the event log, projections and client costs nothing at replay time. Old events
are translated on read, as in the v1 to v2 rename.

---

## Definition of done

- [x] Every artifact kind renders inline and maximized, in stories covering loading, empty, error,
  long titles, narrow boxes, maximized placeholders and both themes.
- [x] Every artifact in a session has exactly one card, in log order, with step runs kept together.
- [x] Maximize and minimize work from the card, the panel header, the artifact list, step links,
  answer links and `ui/request-display-mode`; the URL holds the state across refresh.
- [x] The panel is absent with nothing maximized, resizable beside the conversation on desktop and
  a takeover below desktop; the conversation never remounts when it opens or closes.
- [x] The artifact list floats beside the transcript in `@xwide` conversations and collapses to a
  button there, is a header menu button in narrower ones, never covers the transcript, and hides
  while something is maximized.
- [x] Confirming a maximized draft maximizes the job card it published; nothing else maximizes
  automatically.
- [x] Event schema v3 with translation of v1 and v2 rows on read, migration `020_artifacts.sql`,
  and the renamed routes, projections and schemas.
- [x] No cassette changes; the full replay passes as before, with goldens changed only in event
  vocabulary.
- [x] `make test`, `npm --prefix apps/web run test:design` (screenshots reviewed) and the browser
  suite on desktop and mobile pass.
- [x] README, ARCHITECTURE (sections 3 and 8), DESIGN (sections 2, 3, 4 and 5) and the evals README
  describe artifacts.

---

## Evidence added

These existing requirements are extended:

- **REQ-VIEW-01, REQ-VIEW-02:** unchanged in substance; they now cover `artifact_published` and
  the artifact projections, including legacy `view_pushed` rows translated on read.
- **REQ-VIEW-03:** maximizing from a card, the artifact list, a step or an answer link has no
  workflow side effects: no conversation turn, draft change or job submission. Covered by the
  browser suite on desktop and mobile.
- **REQ-PHI-01/02:** unchanged; no model-visible content changes, and cards render the display
  representation already sent to the client.

---

## Traps

**Pydantic schema names are model-visible.** A tool's parameter schema includes `$defs` named
after its classes. Renaming `ViewSpec` in a tool schema changes every recorded request. Keep the
model-facing class names and compare the tool definitions before and after.

**Draft state reaches the model.** The agent and the scope guard add the current draft as JSON to
the model's context. Rename the field internally, and map it back at that boundary.

**Numbering spans both event types.** Artifact IDs count earlier publications in the session. In
an existing session those are `view_pushed` rows; count both types.

**Connection limits.** Browsers allow six HTTP/1.1 connections per host, and each tab already
holds two event streams (the session and the session list). An event stream per job card starved
the job panel's own requests as soon as a second tab showed a job card. Cards poll instead, and
only the maximized artifact streams.

**Remounting the conversation.** Opening the panel must not remount the chat, or the scroll
position and the composer's text are lost. Keep both panels mounted and change the layout.

**Two copies of one form.** A draft edited in the panel and previewed in the card would diverge.
The placeholder rule prevents it; keep it.

---

## After this

- PLAN15: operational data in the clinical zone (runs, instruments, reagent lots, per-library QC
  metrics), so questions can combine query handles with knowledge thresholds and known-issue
  tickets.
- Renaming the model-facing tool and receipts to artifacts, with a full re-record.
- Picture-in-picture for a running job while another artifact is maximized.

---

## Recorded findings

**Evidence.**

- The tool definitions, response schemas and system prompt dumped before and after the rename are
  byte-identical, no cassette changed, and the full replay (3,966 trials) passes and fails exactly
  the same trials with the same messages as HEAD before the change. The two gates that fail
  (REQ-PHI-04, REQ-GROUND-03) fail identically before and after, with 12 known findings and no
  unrecognized regressions.
- Goldens changed only in vocabulary: `views` to `artifacts`, `view_pushed` to
  `artifact_published`, a draft's `view_id` to `artifact_id`, and the `/invalid-artifact`
  fixture's user text.
- pytest: 772 passed, 1 skipped, including v1 and v2 rows translated to v3, numbering that
  continues after a stored `view_pushed`, the migration over a database holding v1 rows, the
  model-facing draft JSON, and the confirm response's `artifact_id`.
- vitest: 158 passed, including the timeline's grouping, table and draft previews, the card's
  placeholder, the list's collapse preference and v3 replay of the shared fixture.
- Browser suite against an isolated Compose stack: 34 replay tests and 7 scripted tests passed on
  desktop and mobile, covering cards, the list, step and answer links, refresh, history, focus
  return, the takeover on mobile, draft confirmation following to its job card, and **Show log**
  requesting fullscreen from an inline job card.
- `test:design`: no LAYOUT, A11Y, MOTION or STATE finding in any story at any viewport in either
  theme. Screenshots of every new story and of the changed shell and chat stories were reviewed.

**Findings.**

- The first browser run caught connection starvation: with a second tab open, an event stream per
  inline job card used the sixth HTTP/1.1 connection and the maximized job's resource request
  waited forever. Cards now poll and only the maximized artifact streams.
- At 1280px the floating artifact list covered a card's **Maximize** button. The floating card now
  needs a conversation at least `@xwide` (1152px) wide; narrower ones get a header button instead.
- The model also sees draft state through the eval simulator's prompt, which the first golden
  regeneration missed (12 cassette misses). All four model-facing paths now share
  `drafts.model_facing_draft`.

