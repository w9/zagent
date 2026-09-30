# Zagent: Demo Script (about 4 minutes)

**Audience:** clinical and bioinformatics stakeholders
**Arc:** the golden path (query, draft, confirm, failure, diagnosis, rerun), with each guarantee shown when it matters
**Voice:** second person, plain English, short sentences, about 540 words at roughly 150 wpm

---

## Pre-production

- Run the stack in live model mode (`make cluster-live` or `make live`). Don't mention the mode on camera.
- Use two browser tabs on the same session. Tab B is only used for the stale-edit beat.
- **Pre-stage the reveal:** in a fresh session, send
  `Give me the metadata of patient NGC-0041872. Show the patient table.` and let it finish. Leave
  X-ray **off**. Record the opening on a separate, empty session, then cut to this one.
- Prepare two diagram cutaways: the zones graph (ARCHITECTURE §6) and the event-log sequence
  diagram (ARCHITECTURE §4).
- Have the evidence report (`docs/evals/index.html`) open in a third tab, scrolled to **Requirements**.
- A synthetic job runs for about 40 seconds. Cut the wait between its progress and its failure.
- Paste prompts instead of typing them live.

---

## Script

### [0:00-0:15] Opening: the question every lab asks

**SCREEN:** Zagent's home screen with an empty session. The cursor blinks in the chat box.

**VO:**
> Genomics labs want AI help. Finding samples. Setting up analyses. Working out why a run failed.
> But one question always comes first. Can we trust it with patient data?
> This is Zagent. Let me show you why the answer is yes.

---

### [0:15-0:35] The reveal: what the AI saw

**SCREEN:** Cut to the pre-staged session. The patient table fills the working surface, showing a
real synthetic MRN and name.
Click **X-ray**. The view splits: **Display** shows `NGC-0041872`, and **Model** shows `[PT_1]`.
Click the highlighted MRN so its token lights up in both panes.

**VO:**
> On the left is the patient, as your team sees them. Real name. Real record number.
> On the right is what the AI was actually sent. Just a placeholder: `PT_1`.
> This AI helps run a genomics lab. It has never seen a patient's name or ID.

---

### [0:35-1:05] Cutaway: a wall, not a filter

**SCREEN:** Zones diagram. Highlight the clinical zone, then the agent zone, then the one arrow to
the model provider.

**VO:**
> This isn't a filter that tries to catch names on the way out.
> Names and IDs are swapped for placeholders the moment they come in.
> The real values only come back in two places: the database, and your screen.
> The AI's side of the system has no network path to patient data.
> And as a last check, every message to the AI is scanned.
> If it contains a known patient ID, it's blocked.

---

### [1:05-1:30] Handles, not rows

**SCREEN:** Toggle X-ray off. Paste:
`Show the specimens received in the last week for that patient.`
A specimen table appears on the right. Expand the step marker in chat. The tool result shows a
handle, a row count and a schema, but no rows.

**VO:**
> Ask for specimens, and a table appears.
> Now open what the AI got back. It's not the data.
> It's a reference to the result, a row count, and the column names.
> The AI puts the table on screen without reading it.
> So it can't misquote a value. It never had one.

---

### [1:30-1:50] One draft, two editors

**SCREEN:** Paste: `Prepare somatic variant calling on those specimens.`
A pre-filled **Somatic variant calling** form opens. Paste in chat: `min VAF 0.03`.
**Minimum VAF** changes in place. In the form, set **Minimum depth** to `30` and save.

**VO:**
> Ask for somatic calling, and you get a filled-in form.
> Want a change? Just say it. The form updates.
> Or edit the form yourself. The AI sees that too.
> Chat and form edit one shared draft. So they can never disagree.

---

### [1:50-2:20] Only a human can submit

**SCREEN:** In Tab A, start changing **Minimum VAF** to `0.02` but don't save. Switch to Tab B (a
colleague), change **Minimum depth** to `25` and save. Back in Tab A, click **Save changes**. It's
rejected with a **Draft changed** alert showing `min_depth: 30 to 25`. Click **Review current
draft**, then **Confirm submission**. A job card appears with the status **queued**.

**VO:**
> Now submit. Only you can do this.
> The AI has no way to submit a job. It can only edit the draft.
> And your approval is locked to the exact version on your screen.
> Say a colleague changes the draft while you're reviewing it.
> Your save is stopped, and you're shown exactly what changed.
> So you only ever approve what you actually saw.

---

### [2:20-2:45] Refresh doesn't lose work

**SCREEN:** The job card shows a progress bar and a log tail. Press **F5** mid-progress. The page
reloads with the same transcript and the same card, and progress keeps climbing. Brief cutaway to
the event-log sequence diagram.

**VO:**
> While the job runs, refresh the page. Nothing is lost.
> The work doesn't live in your browser. It runs on the server.
> Every step is written to a record that is only ever added to, never changed.
> Your browser just reads that record.
> So after a refresh, a closed laptop, or on a second screen, you pick up right where you left off.

---

### [2:45-3:25] The job fails, and the agent explains why

**SCREEN:** *(Jump cut.)* The job card turns red: `genotype_concordance_failed`. Paste:
`What happened? Explain it using the relevant SOP, quote the line you're relying on, and prepare a corrected rerun with verified specimen identity. Don't submit it.`
The answer streams in, citing **SOP-IDENTITY-001** with a line range. A new draft form opens with
the tumor and normal roles corrected. **Confirm submission** is waiting.

**VO:**
> Then the job fails. It fails a sample identity check.
> The samples don't match what the lab has on record.
> Ask what happened. The AI reads the job log.
> It finds the lab's SOP for sample identity. It quotes the exact line it relies on.
> The answer: the tumor and normal samples were swapped.
> So it prepares a new draft with the right samples.
> The failed job and its logs are kept, for the audit trail.
> And the rerun waits for you. The AI still can't submit anything.

---

### [3:25-4:00] Close: closed doors vs. measured behavior

**SCREEN:** Switch to the evidence report, **Requirements** section. Pan across the invariants,
each marked pass or fail. Then scroll to **Scope classification** and **Identifier detection
recall**, where rates are shown with Wilson confidence intervals. Hold on the report title.

**VO:**
> Everything you just saw falls into two groups.
> Some things are simply impossible.
> The AI can't see patient IDs. It can't run a job without you. A refresh can't lose work.
> We don't rely on the AI behaving well here. The system just has no way to do these things.
> So we test them as pass or fail.
> Other things depend on the AI's judgment. For example, spotting a patient ID that's been disguised.
> Those can't be guaranteed. So we measure them, and show how sure we are of the result.
> Zagent always tells you which is which.

**SCREEN:** Fade to black on the report.

---

## Timing check

| Beat | Duration | Guarantee shown |
|---|---|---|
| Opening | 15s | Sets up the trust question |
| Reveal: X-ray | 20s | Tokenization at ingress |
| Zones cutaway | 30s | NetworkPolicy + egress tripwire |
| Handles, not rows | 25s | Model never sees data values |
| One draft, two editors | 20s | Shared versioned draft |
| Only a human can submit | 30s | No submit tool, hash-bound confirmation |
| Refresh | 25s | Event log as the spine |
| Failure and diagnosis | 40s | SOP-grounded diagnosis, human-gated rerun |
| Close | 35s | Invariants vs. measured properties |
