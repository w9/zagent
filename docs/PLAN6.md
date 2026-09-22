# PLAN6: The Privacy Boundary

**Status:** not started
**Depends on:** [PLAN5](PLAN5.md)
**Shippable outcome:** patient identifiers never reach the model provider, tool calls still work,
the right answer still comes back, and the X-ray toggle shows you both sides.

---

## Goal

Implement tokenization at ingress, resolution at the two edges that need real values, and an
egress tripwire. Then build the screen that makes it visible.

This is the increment PLAN4's design decisions were made for. Because tools already return handles
rather than rows, and already accept relative windows rather than dates, the boundary is an
addition rather than a restructuring.

---

## What you can see when it's done

Ask "give me the metadata of patient NGC-0041872". You get the metadata. The tool call executed
against the real identifier. The answer displays real values.

Toggle X-ray. The same conversation appears side by side with what the model actually saw, where
the identifier is `[PT_1]` and every subsequent reference is consistent. The tool call arguments on
the model's side are tokens. On the execution side they are real.

That screen is the most persuasive ninety seconds in the demo, because it replaces a diagram with
an observation.

---

## Scope

**The privacy service.** Owns the detector rule set and the token vault. Two operations, tokenize
and resolve, with per-session stable numbering so a given identifier maps to the same token
throughout a session and replay hashes stay stable.

**Every ingress is covered.** This is the part most likely to be done incompletely, so enumerate
it:

| Path into model context | Covered by |
|---|---|
| User message text | Web BFF on append |
| Tool results, structured fields | Schema annotation, tokenized by field |
| Tool results, free text | Detector rule set |
| Job log lines | Dispatcher on ingest (PLAN8) |
| Retrieved documents | KB tool result path (PLAN8) |
| View interaction events | Web BFF on append (PLAN7) |

**Structured beats heuristic.** Tool result schemas annotate which fields hold identifiers, so
those are tokenized by construction. The detector rule set covers free text only, which is a much
smaller and better-understood surface.

**Dictionary detection.** The patient registry is known, so every MRN and name in the cohort is in
a dictionary. Literal mentions get near-exact recall. Regex patterns per site format catch
identifiers not in the registry. Detector recall on obfuscated and non-literal mentions is a
measured property, reported as such, not folded into the invariant.

**The egress tripwire.** In the LLM gateway, every outbound request is matched against keyed
hashes of all known identifiers. A hit fails the request loudly and emits an alert event. The
gateway holds hashes and a key, never identifiers, so the tripwire is not itself a leak. Hashes
are keyed rather than plain so the gateway cannot be used as a confirmation oracle.

**Resolution at two edges only.** The tools gateway resolves before executing. The web BFF resolves
on the display stream. Nothing else resolves, and the ability to resolve is a credential the agent
zone does not hold.

**Display detokenization needs a holdback buffer,** because `[PT_` and `1]` can arrive in different
streamed chunks. Buffer the minimum needed to recognize a complete token and no more, so streaming
still feels immediate.

**The X-ray view.** Two panes over the same session: the rendered transcript and the model-visible
transcript reconstructed from the gateway's recorded requests. Token spans are highlighted and
linked across panes.

**Optional: a Rust privacy service.** This is the one component where `Raw<T>` and `Tokenized<T>`
newtypes make a boundary violation a compile error rather than a test failure. Worth doing if the
appetite is there. Not a prerequisite, and the Python version with Pydantic types at the boundary
is sufficient for the invariant as stated.

---

## Out of scope

| Deferred | Owner |
|---|---|
| NetworkPolicy enforcement of the zone boundary | PLAN9 |
| Adversarial and obfuscated identifier corpus | PLAN10 |
| Fault injection proving the mechanism is load-bearing | PLAN10 |
| Field-level encryption at rest, key management | not a goal |

The invariant in this increment rests on types, on the tripwire and on tests. PLAN9 adds the
network layer, and PLAN10 proves all of it can actually fail when broken.

---

## Key decisions

**Tokenize at ingress, not in front of the model call.** A filter at the call site protects one
code path. Tokenization at ingress takes the whole agent zone out of scope, which means the
invariant can be verified by scanning everything the agent zone ever stored. That is a
qualitatively stronger claim and a much easier one to test.

**The event log holds tokens.** Consequence of the above, and the reason the X-ray view is
possible at all: the log is the model's view, and the display path is where real values appear.
It also means a database dump from the agent zone is not a breach.

**Keyed hashes in the tripwire.** Plain hashes would let the gateway answer "is this identifier in
the registry", which is a disclosure. Keyed hashes do not.

**Detector recall is measured, not claimed.** The invariant is precisely scoped: identifiers the
rule set matches never egress. Whether the rule set matches an arbitrary obfuscated mention is a
separate, measured question. Conflating the two is the overclaim that makes most privacy
architectures untrustworthy.

**Structured annotation over detection wherever possible.** Every field moved from heuristic
detection to schema annotation shrinks the measured surface and grows the invariant surface. This
is the main lever for strengthening the guarantee over time.

---

## Definition of done

- [ ] A message containing an MRN produces an event log in which the MRN does not appear.
- [ ] The tool call executes against the real MRN and returns the correct result.
- [ ] The displayed answer shows real values.
- [ ] Token numbering is stable within a session and consistent across turns.
- [ ] The tripwire fires when tokenization is disabled, and the request does not go out.
- [ ] X-ray shows both transcripts with linked highlighting.
- [ ] Streamed display detokenization never shows a partial token.
- [ ] A full-corpus scan finds zero identifiers in the event log, the gateway's recorded requests
      or the cassettes.
- [ ] Cassettes recorded before this increment are re-recorded or verified clean.

The last item matters. Cassettes are checked into a public repository, and a cassette recorded
before tokenization contains synthetic identifiers in a form the project claims never leaves the
clinical zone. Even synthetic, that inconsistency undermines the demonstration.

---

## Evidence added

**REQ-PHI-01 (invariant).** No identifier matched by the rule set appears in any request leaving
the LLM gateway. Evidence: a corpus scan over every recorded request in the suite, plus the
tripwire's hit count, reported as zero hits over N calls with the implied upper bound on the
violation rate.

**REQ-PHI-02 (invariant).** The event log contains no identifiers. Corpus scan over all goldens
and all stored events after a full suite run.

**REQ-PHI-03 (invariant).** Tool calls produce correct results despite tokenization. Asserted per
case: the resolved tool arguments match the expected real values, and the displayed answer matches
the fixture.

**REQ-PHI-04 (measured).** Detector recall on free-text identifier mentions. Initial corpus of
literal mentions across all five site formats. Expanded adversarially at PLAN10, and the figure
will drop when it is, which is the point.

New assertion kinds:

```yaml
expect:
  egress: no_known_identifiers
  tool_calls:
    - name: get_patient
      args_resolved: {mrn: NGC-0041872}   # asserted post-resolution
  display: {contains_fixture: patient.display_name}
```

---

## Traps

**The ingress you forget.** Enumerate them as a checklist in code, with a test that fails when a
new path into model context is added without a tokenization step. The list in this document will
go stale. A test will not.

**Token collisions with real content.** Choose a token format that cannot occur in the corpus, and
test that assumption against the fixtures rather than assuming it.

**Resolution leaking into the wrong place.** The agent zone must not be able to resolve. Make that
a capability, not a convention, and test it by attempting resolution from the runtime's
credentials.

**Quasi-identifiers.** Exact collection timestamps, rare diagnoses and site plus age combinations
are identifying in aggregate even with MRNs removed. The relative-window design from PLAN4 handles
the timestamp case. State the residual limitation plainly in the README rather than implying the
boundary is total.

**Stable numbering versus replay.** Token numbering must be deterministic per session for replay
hashes to be stable. Derive it from the order of first appearance within the session, not from a
global counter or a random id.

---

## Next

[PLAN7](PLAN7.md) adds the second invariant most stakeholders care about: nothing runs without a
human saying so.