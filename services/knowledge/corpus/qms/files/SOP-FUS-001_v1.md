## 1. Purpose
This procedure governs review of RNA fusion calls from rna-fusion jobs.

## 2. Parameters
A fusion is reported only with at least 5 supporting reads across split and spanning evidence.
Artifact filtering is on by default and removes read-through transcripts between adjacent genes.
Disabling artifact filtering requires a documented justification in the service request.

## 3. Known Artifact Classes
- Read-through between neighboring genes on the same strand.
- Fusions involving highly expressed housekeeping genes with low junction diversity.
- Breakpoints that fall in repetitive or low-complexity sequence.

## 4. Review Steps
Check that the fusion keeps the reading frame when the partner genes suggest an oncogenic product.
Compare the breakpoint with the curated fusion targets table before calling it recurrent.
Low RNA input below the library minimum in SOP-PREP-001 lowers sensitivity; say so in the review.

## 5. Limits
The workbench never releases a fusion result; release is a signed human decision.
