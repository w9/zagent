# PLAN3: The Working Surface

**Status:** complete
**Depends on:** [PLAN2](PLAN2.md)
**Shippable outcome:** the agent pushes a table onto the right panel, and the user can flip back
to every previous view.

---

## Goal

Make the right panel real, with exactly one view kind. The point of this increment is not the
table. It is the view-spec contract, the registry, and the history model, all of which are much
easier to get right with one view kind than with six.

At the end of this increment the application has its final shape. Everything after it is
substituting real behavior for scripted behavior.

---

## What you can see when it's done

Send a message. Text streams in the middle panel, and a table appears in the right panel with a
title and a row count. Send another. A second table appears and the first is still reachable
through back navigation, with a breadcrumb or tab strip showing where you are.

Refresh. The view stack is exactly as it was, because it is a projection of the event log rather
than component state.

---

## Scope

**The view spec.** `{kind, version, props}`, validated against a JSON Schema at the boundary. The
model, and in this increment the script, never emits markup or code. One kind only:

```json
{
  "kind": "table",
  "version": 1,
  "props": {
    "title": "Specimens received in the last 24 hours",
    "columns": [{"key": "specimen_id", "label": "Specimen", "type": "string"}],
    "rows": [["SPC-0001"]],
    "row_count": 14
  }
}
```

Rows are inline here. From PLAN4 they are replaced by a query handle, and the renderer fetches.
Design the props so that swap is additive: `rows` and `handle` are alternative sources and the
component handles both.

**The registry.** `kind` maps to a schema and a React component. Registering a view kind means
adding a schema file and a component, with no changes to the panel, the reducer or the runner.
This is the extension point that PLAN8 and any future MCP server use.

**`view_pushed`.** Carries the validated spec plus a `view_id`. Validation happens on the
emitting side, and an invalid spec produces a `conversation_turn_failed` rather than a broken
panel. A view that cannot be rendered is a bug worth surfacing, not worth degrading around.

**The view stack.** A projection over `view_pushed` events for the session. Back and forward walk
it. The panel follows the newest view when the user is at the head, and stops following once they
navigate back, which is the behavior every browser-like surface has and the thing users complain
about when it is missing.

**Collapsible event markers.** The middle panel renders `step_started` and `step_finished` as
collapsed markers. The script emits two steps now; the model/tool loop supplies real steps
from PLAN4 onward. Completion updates the same marker without resetting its open state.

**Snapshot testing.** Register the view kinds in a component snapshot suite, so a spec renders to
stable markup. This is the deterministic half of visual correctness. Screenshot comparisons
are deliberately not a CI gate, since image diffing is a maintenance burden out of proportion
to what it catches here. Browser screenshots remain inspection artifacts, not pixel goldens.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Charts | PLAN4, once there is real data to chart |
| Forms | PLAN7 |
| Live-updating views | PLAN8 |
| MCP Apps and tool-owned views | PLAN8 |
| Query handles | PLAN4 |

One kind now. The temptation to add charts, cards and timelines in this increment should be
resisted: each kind is surface area that needs a schema, a component, a snapshot and cases, and
none of them teach anything the table has not already taught.

---

## Key decisions

**Specs, never code.** A model that emits markup or JavaScript cannot be validated, snapshotted
or safely rendered. A spec can be all three. This also keeps the door open for MCP Apps at PLAN8
without a second rendering model, because a tool-owned view is a spec whose renderer happens to
live in a sandboxed frame.

**The stack is derived, not stored.** Storing panel state separately from the log creates two
sources of truth and a reconciliation bug on every refresh. Deriving it means refresh
correctness is the same code path as initial load.

**Validate on emit, fail the conversation turn.** The alternative, rendering a fallback for an
invalid spec, hides exactly the class of bug that matters once a model is generating specs.

**One component, two data sources.** Building `rows` now and `handle` at PLAN4 as alternatives in
one component avoids a rewrite of the table and of every case that asserts on it.

---

## Definition of done

- [x] A scripted conversation turn pushes two tables, and both are reachable through navigation.
- [x] Refreshing restores the view stack and the current position.
- [x] Navigating back stops the panel from auto-following, and returning to the head resumes it.
- [x] An invalid spec produces `conversation_turn_failed` with a schema error, and the panel is untouched.
- [x] Step markers render collapsed, and expand to show their contents.
- [x] Component snapshots exist for the table kind, including empty and truncated states.
- [x] Chaos mode passes on every view case: interrupting a conversation turn mid-push never leaves a partial
      view on screen.

## Implementation Notes

- The canonical [table v1 JSON Schema](../services/agent/zagent/view_schemas/table.v1.json) is
  loaded by Python's JSON Schema validator and imported by the browser's Ajv registry. It
  limits columns and rows, validates scalar cell types, and permits exactly one of `rows` or
  `handle`. Both boundaries additionally check unique column keys, row width, cell/column
  agreement, and `row_count` consistency. Labels and cells are rendered as text, never HTML.
- `view_pushed` carries `{view_id, spec}`. The scripted agent namespaces view, message, and step
  IDs by conversation turn. Invalid view payloads fail during emission before sequence
  allocation, not during startup; `/invalid-view` demonstrates the failure without changing
  prior views. Store appends revalidate payloads in case a caller mutated a validated object.
- Snapshots add `views` and `steps`. Both reducers retain first-seen views by ID, ignore replay
  duplicates, and preserve sequence order. No view table, cached stack, or new event schema
  version is needed. The existing v2 log projects old sessions to empty view and step lists.
- The chosen historical view is the `view` query parameter in the session URL. This is a
  per-browser navigation cursor, not a second store of view data. Missing selection means
  follow the latest; selecting the head clears the cursor. Refresh restores a pinned view,
  while two tabs may browse different history positions over the same event-derived stack.
- A single session subscription drives both panels. Mobile/tablet tabs use `panel=surface`
  to preserve the selected panel on refresh; tables scroll within their panel at narrow widths.
- Schemas are discovered from `view_schemas/*.json`; React components from
  [components/views](../apps/web/src/components/views) export `kind` and `version` metadata.
  Adding a schema and matching renderer does not change the panel, reducer, or harness runner.
  The table renderer accepts an injected handle resolver with loading, validation, retry, and
  cancellation states. PLAN3 supplies inline data only; the actual query backend is PLAN4.
- Step payloads carry `step_id`, a start `title`, optional `detail`, and a finish `status`.
  Starting sequence numbers place markers in the chat timeline. Unfinished steps become failed
  when their conversation turn fails. Native disclosure controls start collapsed.
- [views.test.tsx](../apps/web/src/components/views.test.tsx) covers complete, empty, and truncated
  component snapshots, text escaping, handle-source states, and step disclosure behavior.
  Python and TypeScript replay the same [prefix fixture](../evals/fixtures/view-replay.json),
  including a duplicate view identity and snapshot continuation after every event.
- The harness validates every view across the entire corpus and independently compares the
  view stack at each prefix. `views` asserts an ordered subsequence with exact or `~regex`
  property matches; `view_stack_depth` asserts the final depth. Four new view cases add 40
  seeded chaos trials. For turns with views, chaos disconnects immediately after a seeded
  complete `view_pushed` frame; text-only turns retain text-progress interruption.
- Verification: `make test`, `make evals`, and `make browser`. Browser checks cover two tabs,
  refresh, physical SSE interruption, history pinning and resumed following, invalid-view
  isolation, collapsed markers, and 320px/390px mobile layouts. All data remains synthetic.

---

## Evidence added

**REQ-VIEW-01 (invariant).** Every `view_pushed` payload validates against its registered schema.
Asserted as a property over the whole corpus of goldens, so it is checked on every case rather
than in a dedicated test.

**REQ-VIEW-02 (invariant).** The view stack derived from a log prefix equals the client's stack
after replaying that prefix. This is the assertion that keeps refresh correctness honest.

New assertion kind in the case format:

```yaml
expect:
  views:
    - kind: table
      props_match: {title: "~received in the last 24 hours"}
  view_stack_depth: 2
```

---

## Traps

**Auto-follow versus user navigation.** The rule that works: follow while the user is at the
head, stop when they navigate away, and offer an explicit affordance to return. Deciding this
implicitly from scroll position or timing produces a panel that fights the user.

**View identity across reconnects.** A view needs a stable `view_id` so a reconnecting client does
not duplicate it. Derive it from the event, not from client-side state.

**Schema versioning starts now.** Include `version` in the spec from the first kind. Adding it
later means either a migration over stored events or a permanent special case, and the event log
is append-only, so stored specs are forever.

**Snapshot scope creep.** Snapshot the view kinds, not the whole application shell. Shell
snapshots break on every layout tweak and catch nothing.

---

## Next

[PLAN4](PLAN4.md) replaces `ScriptedAgent` with a real model and real tools. Every golden written
so far becomes the regression test for that substitution.