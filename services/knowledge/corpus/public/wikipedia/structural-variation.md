---
title: Structural variation
requested_title: Structural variation
revision_id: 1376707654
revision_timestamp: '2026-09-25T19:58:10Z'
url: https://en.wikipedia.org/w/index.php?oldid=1376707654
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

Genomic structural variation is the variation in structure of an organism's chromosome, such as deletions, duplications, copy-number variants, insertions, inversions and translocations. Originally, a structure variation affects a sequence length about 1kb to 3Mb, which is larger than SNPs and smaller than chromosome abnormality (though the definitions have some overlap). However, the operational range of structural variants has widened to include events > 50bp. Some structural variants are associated with genetic diseases, however most are not. Approximately 13% of the human genome is defined as structurally variant in the normal population, and there are at least 240 genes that exist as homozygous deletion polymorphisms in human populations, suggesting these genes are dispensable in humans. While humans carry a median of 3.6 Mbp in SNPs (compared to a reference genome), a median of 8.9 Mbp is affected by structural variation which thus causes most genetic differences between humans in terms of raw sequence data.

## Microscopic structural variation

Microscopic means that it can be detected with optical microscopes, such as aneuploidies, marker chromosome, gross rearrangements and variation in chromosome size. The frequency in human population is thought to be underestimated due to the fact that some of these are not actually easy to identify. These structural abnormalities exist in 1 of every 375 live births by putative information.

## Sub-microscopic structural variation

Sub-microscopic structural variants are much harder to detect owing to their small size. The first study in 2004 that used DNA microarrays could detect tens of genetic loci that exhibited copy number variation, deletions and duplications, greater than 100 kilobases in the human genome. However, by 2015 whole genome sequencing studies could detect around 5,000 of structural variants as small as 100 base pairs encompassing approximately 20 megabases in each individual genome. These structural variants include deletions, tandem duplications, inversions, mobile element insertions. The mutation rate is also much higher than microscopic structural variants, estimated by two studies at 16% and 20% respectively, both of which are probably underestimates due to the challenges of accurately detecting structural variants. It has also been shown that the generation of spontaneous structural variants significantly increases the likelihood of generating further spontaneous single nucleotide variants or indels within 100 kilobases of the structural variation event.

## Copy-number variation

Copy-number variation (CNV) is a large category of structural variation, which includes insertions, deletions and duplications. In recent studies, copy-number variations are tested on people who do not have genetic diseases, using methods that are used for quantitative SNP genotyping. Results show that 28% of the suspected regions in the individuals actually do contain copy number variations. Also, CNVs in human genome affect more nucleotides than Single Nucleotide Polymorphism (SNP).
It is also noteworthy that many of CNVs are not in coding regions. Because CNVs are usually caused by unequal recombination, widespread similar sequences such as LINEs and SINEs may be a common mechanism of CNV creation.

## Inversion

There are several inversions known which are related to human disease. For instance, recurrent 400kb inversion in factor VIII gene is a common cause of haemophilia A, and smaller inversions affecting idunorate 2-sulphatase (IDS) will cause Hunter syndrome. More examples include Angelman syndrome and Sotos syndrome. However, recent research shows that one person can have 56 putative inversions, thus the non-disease inversions are more common than previously supposed. Also in this study it's indicated that inversion breakpoints are commonly associated with segmental duplications. One 900 kb inversion in the chromosome 17 is under positive selection and are predicted to increase its frequency in European population.

## Other structural variants

More complex structural variants can occur include a combination of the above in a single event. The most common type of complex structural variation are non-tandem duplications, where sequence is duplicated and inserted in inverted or direct orientation into another part of the genome. Other classes of complex structural variant include deletion-inversion-deletions, duplication-inversion-duplications, and tandem duplications with nested deletions.
There are also cryptic translocations and segmental uniparental disomy (UPD). There are increasing reports of these variations, but are more difficult to detect than traditional variations because these variants are balanced and array-based or PCR-based methods are not able to locate them.

## Structural variation and phenotypes

Some genetic diseases are suspected to be caused by structural variations, but the relation is not very certain. It is not plausible to divide these variants into two classes as "normal" or "disease", because the actual output of the same variant will also vary. Also, a few of the variants are actually positively selected for (mentioned above).
A series of studies have shown that gene disrupting spontaneous (de novo) CNVs disrupt genes approximately four times more frequently in autism than in controls and contribute to approximately 5–10% of cases. Inherited variants also contribute to around 5–10% of cases of autism.
Structural variations also have its function in population genetics. Different frequency of a same variation can be used as a genetic mark to infer relationship between populations in different areas. A complete comparison between human and chimpanzee structural variation also suggested that some of these may be fixed in one species because of its adaptative function. There are also deletions related to resistance against malaria and AIDS. Also, some highly variable segments are thought to be caused by balancing selection, but there are also studies against this hypothesis.

## Database of structural variation

Some genome browsers and bioinformatic databases have a list of structural variations in the human genome with an emphasis on CNVs, and can show them in the genome browsing page, for example, UCSC Genome Browser. Under the page viewing a part of the genome, there are "Common Cell CNVs" and "Structural Var" which can be enabled.
On NCBI, there is a special page  for structural variation. In that system, both "inner" and "outer" coordinates are shown; they are both not actual breakpoints, but surmised minimal and maximum range of sequence affected by the structural variation. The types are classified as insertion, loss, gain, inversion, LOH, everted, transchr and UPD.

## Methods of detection

New methods have been developed to analyze human genetic structural variation at high resolutions. The methods used to test the genome are in either a specific targeted way or in a genome wide manner.  For Genome wide tests, array-based comparative genome hybridization approaches bring the best genome wide scans to find new copy number variants. These techniques use DNA fragments that are labeled from a genome of interest and are hybridized, with another genome labeled differently, to arrays spotted with cloned DNA fragments. This reveals copy number differences between two genomes.
For targeted genome examinations, the best assays for checking specific areas of the genome are primarily PCR based. The best established of the PCR based methods is real time quantitative polymerase chain reaction (qPCR). A different approach is to specifically check certain areas that surround known segmental duplications since they are usually areas of copy number variation. An SNP genotyping method that offers independent fluorescence intensities for two alleles can be used to target the nucleotides in between two copies of a segmental duplication. From this, an increase in intensity from one of the alleles compared to the other can be observed.
With the development of next-generation sequencing (NGS) technology, four classes of strategies for the detection of structural variants with NGS data have been reported, with each being based on patterns that are diagnostic of different classes of SV.

Read-depth or read-count methods assume a random distribution (e.g. Poisson distribution) of reads from short read sequencing. The divergence from this distribution is investigated to discover duplications and deletions. Regions with duplication will show higher read depth while those with deletion will result in lower read depth.
Split-read methods enable detection of insertions (including mobile element insertions) and deletions down to single base-pair resolution. The presence of a SV is identified from discontinuous alignment to the reference genome. A gap in the read marks a deletion and in the reference marks an insertion.
Read pair methods examine the length and orientation of paired-end reads from short read sequencing data. For example, read pairs further apart than expected indicate a deletion. Translocations, inversions and tandem duplications can likewise be discovered using read-pairs.
De novo sequence assembly may be applied with reads that are accurate enough. While, in practice, use of this method is limited by the length of sequence reads, long read based genome assemblies offer structural variation discovery for classes such as insertions that escape detection when using other methods.
