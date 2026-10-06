> DRAFT for review under CHG-0024. Not effective. Do not use for routine work.

## 1. Purpose
This procedure defines read quality review for libraries analyzed in the Zagent workbench.

## 2. Coverage
Readqc fails when a selected library's coverage is below the confirmed minimum coverage.
Normal and germline libraries require a mean coverage of at least 30x.
Tumor libraries intended for somatic calling would require a mean coverage of at least 45x.
The proposed 45x tumor minimum is based on the VAL-SOM-2025 low-VAF results and is still under review.

## 3. Sequencing Quality
Libraries with a mapping rate below 95 percent are held for review.
Duplication above 15 percent would fail readqc instead of only being recorded.
The duplication rule needs an impact estimate from the bioinformatics team before approval.

## 4. Tumor Purity
Tumor purity below 0.20 produces a warning because reduced sensitivity may affect interpretation.

## 5. Open Review Comments
QA asks whether the 45x minimum should apply to RNA-only cases; it should not.
The lab director asks for the expected increase in top-up sequencing before sign-off.
