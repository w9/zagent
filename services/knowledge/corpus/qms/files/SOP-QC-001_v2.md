## 1. Purpose
This procedure defines read quality review for libraries analyzed in the workbench.

## 2. Coverage
Readqc fails when a selected library's coverage is below the confirmed minimum coverage.
All libraries require a mean coverage of at least 30x.
Report the recorded observed coverage and confirmed threshold, not a guessed new threshold.
Only a human-confirmed new draft can start another execution.

## 3. Tumor Purity
Tumor purity below 0.20 produces a warning because reduced sensitivity may affect interpretation.
A completed job with a low-purity warning is not a failed job.

## 4. Records
Record each review on the QC review record.

## 5. Revision History
| Version | Effective | Change |
| --- | --- | --- |
| 1 | 2023-01-09 | Initial release. |
| 2 | 2024-03-01 | Single 30x minimum for all libraries; purity warning added. |
