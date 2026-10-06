---
title: Coverage (genetics)
requested_title: Coverage (genetics)
revision_id: 1368671266
revision_timestamp: '2026-08-10T12:10:47Z'
url: https://en.wikipedia.org/w/index.php?oldid=1368671266
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

In genetics, coverage is one of several measures of the depth or completeness of DNA sequencing, and is more specifically expressed in any of the following terms:

Sequence coverage (or depth) is the number of unique reads that include a given nucleotide in the reconstructed sequence. Deep sequencing refers to the general concept of aiming for high number of unique reads of each region of a sequence.
Physical coverage, the cumulative length of reads or read pairs expressed as a multiple of genome size.
Genomic coverage, the percentage of all base pairs or loci of the genome covered by sequencing.

## Sequence coverage

### Rationale

Even though the sequencing accuracy for each individual nucleotide is very high, the very large number of nucleotides in the genome means that if an individual genome is only sequenced once, there will be a significant number of sequencing errors. Furthermore, many positions in a genome contain rare single-nucleotide polymorphisms (SNPs). Hence to distinguish between sequencing errors and true SNPs, it is necessary to increase the sequencing accuracy even further by sequencing individual genomes a large number of times.

### Ultra-deep sequencing

The term "ultra-deep" can sometimes also refer to higher coverage (>100-fold), which allows for detection of sequence variants in mixed populations. In the extreme, error-corrected sequencing approaches such as maximum-depth sequencing can make it so that coverage of a given region approaches the throughput of a sequencing machine, allowing coverages of >108.

### Transcriptome sequencing

Deep sequencing of transcriptomes, also known as RNA-Seq, provides both the sequence and frequency of RNA molecules that are present at any particular time in a specific cell type, tissue or organ. Counting the number of mRNAs that are encoded by individual genes provides an indicator of protein-coding potential, a major contributor to phenotype. Improving methods for RNA sequencing is an active area of research both in terms of experimental and computational methods.

### Calculation

The average coverage for a whole genome can be calculated from the length of the original genome (G), the number of reads (N), and the average read length (L) as

N
×
L

/

G

{\textstyle N\times L/G}

. For example, a hypothetical genome with 2,000 base pairs reconstructed from 8 reads with an average length of 500 nucleotides will have 2× redundancy. This parameter also enables one to estimate other quantities, such as the percentage of the genome covered by reads (sometimes also called breadth of coverage). A high coverage in shotgun sequencing is desired because it can overcome errors in base calling and assembly. The subject of DNA sequencing theory addresses the relationships of such quantities.

## Physical coverage

Sometimes a distinction is made between sequence coverage and physical coverage. Where sequence coverage is the average number of times a base is read, physical coverage is the average number of times a base is read or spanned by mate paired reads.

## Genomic coverage

In terms of genomic coverage and accuracy, whole genome sequencing can broadly be classified into either of the following:

A draft sequence, covering approximately 90% of the genome at approximately 99.9% accuracy
A finished sequence, covering more than 95% of the genome at approximately 99.99% accuracy
Producing a truly high-quality finished sequence by this definition is very expensive. Thus, most human "whole genome sequencing" results are draft sequences (sometimes above and sometimes below the accuracy defined above).
