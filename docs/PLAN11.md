# PLAN11: The Gallery

**Status:** not started
**Depends on:** [PLAN10](PLAN10.md)
**Prerequisite:** land shared assistant Markdown rendering before building the gallery stories.
**Shippable outcome:** a guarantee gallery where each claim has a demo that cannot flake, a link to
the code that enforces it, and the evidence behind it.

---

## Goal

Present the work to someone who has thirty seconds of patience and then, if convinced, thirty
minutes.

This is built last on purpose. A showcase built early showcases intentions. Built now, every story
in it is backed by a mechanism that exists and a measurement that ran.

---

## What you can see when it's done

A gallery, one story per requirement, in the Storybook idiom but organized around guarantees rather
than components. Each story has the same four parts:

| Part | Contents |
|---|---|
| **Claim** | The requirement statement and its tier, invariant or measured |
| **Mechanism** | How it is enforced, in two sentences, linked to the enforcing code |
| **Demo** | The behavior, replayed from cassettes so it never flakes, with a "run live" toggle to prove it is not canned |
| **Evidence** | The measured result, the cases, the mutation that breaks it, and provenance |

The "run live" toggle matters more than it looks. A canned demo invites the suspicion that it is a
video. A canned demo with a switch that runs the real thing answers that suspicion without risking a
live failure in front of an audience.

---

## Scope

**Pre-gallery usability: assistant Markdown.** Implement safe, streaming-compatible Markdown
rendering in the product's shared transcript component before starting the gallery. Use an
established parser/renderer for paragraphs, headings, emphasis, lists, blockquotes, inline and
fenced code, links, and GFM tables. Keep user messages as plain text. Incomplete Markdown during
streaming must remain legible; completion, refresh, and replay must produce the same rendering.
Code and tables may scroll within their own bounds, never widen the mobile page.

This is presentation only: preserve the original response text in the event log, model context,
cassettes, and exports. Do not filter, rewrite, retry, or replace responses. Query result tables
still belong in published views; rendering Markdown does not change that presentation contract.

Disable raw HTML execution and remote images, allow only safe link schemes, and protect external
links. Never resolve private identifiers into link destinations. Preserve privacy highlights in
displayed text and keep X-ray's model-visible request representation unchanged. Existing titled
view references remain host-owned navigation; model-authored links cannot invoke tools, mutate
state, or substitute for validated working-surface references.

**The gallery shell.** Routed views over the same components the application uses. No parallel
implementation, because a showcase that drifts from the product is worse than no showcase.

**Stories for every requirement,** grouped by theme: streaming and durability, scope control,
privacy, job safety, grounding, and isolation.

**Three set pieces,** which carry most of the persuasive weight and deserve disproportionate polish.

*X-ray mode.* The rendered transcript beside the model-visible transcript, with token spans linked
across panes. It converts the privacy claim from a diagram into an observation, and it is the single
most effective thing in the project.

*The chaos button.* Kills the tab or the runtime pod mid-stream, live, then shows the recovered
transcript diffed against an uninterrupted turn. Doing this to yourself in front of an audience is
more convincing than any number of passing tests.

*The scope guard curve.* Precision against recall, with the operating point marked and the
near-boundary cases listed. It communicates, without saying so, that the project knows the
difference between a threshold and a guarantee.

**The mutation panel.** Flip a mutation from the UI and watch the relevant story's evidence go red.
This is where the two-tier model becomes intuitive rather than explained: an invariant's demo stops
being possible, while a measured property's number drops.

**The golden path recording.** Two minutes, at the top of the README.

1. "What came in yesterday for patient NGC-0041872?" A table appears.
2. "Run somatic calling on those." A pre-filled form, with the missing matched normal flagged.
3. "min VAF 0.03." The form updates live.
4. Confirm. The job runs and then fails on genotype concordance.
5. "What happened?" The agent explains, citing the SOP.
6. It drafts a corrected re-run.
7. "Show me today's running jobs." A live grid.
8. "What's 2+2?" Refused.
9. X-ray toggle.
10. Refresh mid-stream. It resumes.

Every beat of that sequence is a guarantee from the table, in an order that tells a story rather
than enumerates features.

**README completion.** Replace the placeholder with the recording, fill in the status table, and
publish the final report.

---

## Out of scope

| Deferred | Owner |
|---|---|
| A hosted public instance | not a goal. The synthetic data is safe to host, but the operational burden is not worth it |
| Design polish beyond legibility | not a goal |
| Narrated walkthrough video beyond the two-minute recording | optional |

---

## Key decisions

**Cassette-backed demos with a live toggle.** Reliability for the audience, verifiability for the
skeptic.

**Organized by guarantee, not by component.** Storybook's conventional organization is by component,
which would produce a catalog of UI parts. The audience for this project cares about claims, so the
stories are claims.

**The same components as the product.** A gallery with its own implementations is a liability, and
it will be wrong within a month.

**Mutations are exposed in the gallery, not just in CI.** Letting a viewer break a guarantee
themselves is the fastest way to communicate that the guarantee is real. It is also the only part of
the evidence architecture that is genuinely fun.

**Build it last.** Stated as a decision because the temptation to build it early is strong, and
doing so would have produced a showcase of things that did not work yet.

---

## Definition of done

- [ ] Shared assistant Markdown rendering is implemented in the product before gallery stories,
  with readable streaming, completed, refreshed, and replayed responses on desktop and mobile.
- [ ] Renderer tests cover split delimiters/code fences, lists, code, links, tables, malicious
  HTML and URL schemes, and bounded layout at 320 pixels.
- [ ] Original response/event text is unchanged; privacy highlights and host-owned view references
  still work, and rendering or activating a Markdown link cannot trigger workflow mutations.
- [ ] Every requirement in the register has a story.
- [ ] Every story has all four parts, with the mechanism linking to real code.
- [ ] Every demo replays from cassettes and never flakes.
- [ ] The live toggle works for every story.
- [ ] X-ray, chaos and the scope curve are polished set pieces.
- [ ] The mutation panel works from the UI, and the affected evidence visibly changes.
- [ ] The two-minute recording is in the README.
- [ ] The status table is complete.
- [ ] The published report is linked from every story and from the README badges.
- [ ] A clean clone, one command, and the gallery runs with no API key.

That last item is the real acceptance test for the whole project. Someone who finds the repository
should be able to run everything in it, including all the evidence, without a key, a credential, or
a conversation.

---

## Evidence added

The gallery itself reports existing evidence rather than inventing new behavioral claims.
The Markdown prerequisite adds component and browser regressions for streaming, replay, link/HTML
safety, privacy highlighting, view navigation, and responsive layout. Keep these in the product's
existing test suites; formatting must not require rewriting event or conversation goldens.

One addition worth making: a story for the evidence architecture itself, whose claim is "the suite
detects broken guarantees", whose mechanism is the mutation framework, and whose evidence is the
mutation table. It is the most important story in the gallery and the easiest to forget to write.

---

## Traps

**Polish drifting into rebuild.** The gallery uses product components. When one is not good enough
for the showcase, improve it in the product rather than forking it.

**Stories that argue instead of showing.** The mechanism section is two sentences and a link. If it
needs more, the mechanism is too complicated and that is a finding about the architecture.

**A recording that demonstrates features.** The golden path works because it is a story with a
problem and a resolution. A tour of capabilities is forgettable in a way that a diagnosed failure is
not.

**Overclaiming in the final README.** The last thing written is the most likely to overstate. Every
claim in the README must trace to a requirement in the register, and the measured ones must carry
their intervals. A reader who checks one claim and finds it precisely supported will trust the rest.
A reader who finds one overstated will not.

---

## After this

The project is complete as scoped. Directions that would extend it without changing its thesis:

- Additional MCP servers, to exercise the extensibility claim with something not written for it.
- Federated queries across sites, which pairs naturally with the isolation work already present.
- A written methodology piece on the two-tier model, which is the part of this project most likely
  to be useful to other people.