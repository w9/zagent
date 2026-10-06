## 1. Purpose
This procedure governs review of somatic SNV and indel calls produced by somatic-snv jobs.

## 2. Parameters
The default minimum variant allele frequency is 0.05 for reportable somatic calls.
Calls also need a minimum depth of 20 reads at the variant position in the tumor library.
Analysts may lower min_vaf to 0.03 only when tumor coverage is at least 100x and the request documents why.
There is no matched_normal parameter; the specimen query must contain both tumor and normal specimens.
Missing normal specimens leave the draft invalid until a normal is added to the selection.

## 3. Review Steps
- Confirm the job completed and the identity check passed.
- Check tumor purity; a low-purity warning lowers sensitivity for subclonal variants.
- Review calls between 0.05 and 0.10 VAF against the panel of normals.
- Record artifacts such as strand bias and oxidation damage with their evidence.

## 4. Limits
The workbench never releases a somatic result; release is a signed human decision.
Parameter changes after confirmation require a new draft and a new confirmation.

## 5. Revision History
| Version | Effective | Change |
| --- | --- | --- |
| 1 | 2024-01-15 | Initial release with min_vaf 0.10. |
| 2 | 2025-03-17 | Default min_vaf lowered to 0.05 after VAL-WGS-2025. |
