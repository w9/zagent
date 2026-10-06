---
title: Exome sequencing
requested_title: Exome sequencing
revision_id: 1377450320
revision_timestamp: '2026-09-29T12:56:07Z'
url: https://en.wikipedia.org/w/index.php?oldid=1377450320
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

Exome sequencing, also known as whole exome sequencing (WES), is a genomic technique for sequencing all of the protein-coding regions of genes in a genome (known as the exome). It consists of two steps: the first step is to select only the subset of DNA that encodes proteins. These regions are known as exons—humans have about 180,000 exons, constituting about 1% of the human genome, or approximately 30 million base pairs. The second step is to sequence the exonic DNA using any high-throughput DNA sequencing technology.
The goal of this approach is to identify genetic variants that alter protein sequences, and to do this at a much lower cost than whole-genome sequencing. Since these variants can be responsible for both Mendelian and common polygenic diseases, such as Alzheimer's disease, whole exome sequencing has been applied both in academic research and as a clinical diagnostic.

## Motivation and comparison to other approaches

Exome sequencing is especially effective in the study of rare Mendelian diseases, because it is an efficient way to identify the genetic variants in all of an individual's genes. These diseases are most often caused by very rare genetic variants that are only present in a tiny number of individuals; by contrast, techniques such as SNP arrays can only detect shared genetic variants that are common to many individuals in the wider population. Furthermore, because severe disease-causing variants are much more likely (but by no means exclusively) to be in the protein coding sequence, focusing on this 1% costs far less than whole genome sequencing but still detects a high yield of relevant variants.
In the past, clinical genetic tests were chosen based on the clinical presentation of the patient (i.e. focused on one gene or a small number known to be associated with a particular syndrome), or surveyed only certain types of variation (e.g. comparative genomic hybridization) but provided definitive genetic diagnoses in fewer than half of all patients. Exome sequencing is now increasingly used to complement these other tests: both to find mutations in genes already known to cause disease as well as to identify novel genes by comparing exomes from patients with similar features.

## Technical methodology

### Step 1: Target-enrichment strategies

Target-enrichment methods allow one to selectively capture genomic regions of interest from a DNA sample prior to sequencing. Several target-enrichment strategies have been developed since the original description of the direct genomic selection (DGS) method in 2005.
Though many techniques have been described for targeted capture, only a few of these have been extended to capture entire exomes. The first target enrichment strategy to be applied to whole exome sequencing was the array-based hybrid capture method in 2007, but in-solution capture has gained popularity in recent years.

#### Array-based capture

Microarrays contain single-stranded oligonucleotides with sequences from the human genome to tile the region of interest fixed to the surface. Genomic DNA is sheared to form double-stranded fragments. The fragments undergo end-repair to produce blunt ends and adaptors with universal priming sequences are added. These fragments are hybridized to oligos on the microarray.
Unhybridized fragments are washed away and the desired fragments are eluted. The fragments are then amplified using PCR.
Roche NimbleGen was first to take the original DGS technology and adapt it for next-generation sequencing. They developed the Sequence Capture Human Exome 2.1M Array to capture ~180,000 coding exons. This method is both time-saving and cost-effective compared to PCR based methods. The Agilent Capture Array and the comparative genomic hybridization array are other methods that can be used for hybrid capture of target sequences.  Limitations in this technique include the need for expensive hardware as well as a relatively large amount of DNA.

#### In-solution capture

To capture genomic regions of interest using in-solution capture, a pool of custom oligonucleotides (probes) is synthesized and hybridized in solution to a fragmented genomic DNA sample. The probes (labeled with beads) selectively hybridize to the genomic regions of interest after which the beads (now including the DNA fragments of interest) can be pulled down and washed to clear excess material. The beads are then removed and the genomic fragments can be sequenced allowing for selective DNA sequencing of genomic regions (e.g., exons) of interest.
This method was developed to improve on the hybridization capture target-enrichment method. In solution capture (as opposed to hybrid capture) there is an excess of probes to target regions of interest over the amount of template required. The optimal target size is about 3.5 megabases and yields excellent sequence coverage of the target regions. The preferred method is dependent on several factors including: number of base pairs in the region of interest, demands for reads on target, equipment in house, etc.

### Step 2: Sequencing

There are many Next Generation Sequencing sequencing platforms available, postdating classical Sanger sequencing methodologies. Other platforms include Roche 454 sequencer and Life Technologies SOLiD systems, the Life Technologies Ion Torrent and Illumina's Illumina Genome Analyzer II (defunct) and subsequent Illumina MiSeq, HiSeq, and NovaSeq series instruments, all of which can be used for massively parallel exome sequencing.  These 'short read' NGS systems are particularly well suited to analyse many relatively short stretches of DNA sequence, as found in human exons.

## Comparison with other technologies

There are multiple technologies available that identify genetic variants. Each technology has advantages and disadvantages in terms of technical and financial factors. Two such technologies are microarrays and whole-genome sequencing.

### Microarray-based genotyping

Microarrays use hybridization probes to test the prevalence of known DNA sequences, thus they cannot be used to identify unexpected genetic changes. In contrast, the high-throughput sequencing technologies used in exome sequencing directly provide the nucleotide sequences of DNA at the thousands of exonic loci tested. Hence, WES addresses some of the present limitations of hybridization genotyping arrays.
Although exome sequencing is more expensive than hybridization-based technologies on a per-sample basis, its cost has been decreasing due to the falling cost and increased throughput of whole genome sequencing.

### Whole-genome sequencing

Exome sequencing is only able to identify those variants found in the coding region of genes which affect protein function.  It is not able to identify the structural and non-coding variants associated with the disease, which can be found using other methods such as whole genome sequencing. There remains 99% of the human genome that is not covered using exome sequencing, and exome sequencing allows sequencing of portions of the genome over at least 20 times as many samples compared to whole genome sequencing. For translation of identified rare variants into the clinic, sample size and the ability to interpret the results to provide a clinical diagnosis indicates that with the current knowledge in genetics, there are reports of exome sequencing being used for assisting diagnosis. The cost of exome sequencing is typically lower than whole genome sequencing.

## Data analysis

The statistical analysis of the large quantity of data generated from sequencing approaches is a challenge. Even by only sequencing the exomes of individuals, a large quantity of data and sequence information is generated which requires a significant amount of data analysis. Challenges associated with the analysis of this data include changes in programs used to align and assemble sequence reads. Various sequencing technologies also have different error rates and generate various read-lengths which can pose challenges in comparing results from different sequencing platforms.
False positive and false negative findings are associated with genomic resequencing approaches and are critical issues. A few strategies have been developed to improve the quality of exome data such as:

Comparing the genetic variants identified between sequencing and array-based genotyping
Comparing the coding SNPs to a whole genome sequenced individual with the disorder
Comparing the coding SNPs with Sanger sequencing of HapMap individuals
Rare recessive disorders may not have single nucleotide polymorphisms (SNPs) in public databases such as dbSNP. More common recessive phenotypes would be more likely to have disease-causing variants reported in dbSNP. For example, the most common cystic fibrosis variant has an allele frequency of about 3% in most populations. Screening out such variants might erroneously exclude such genes from consideration. Genes for recessive disorders are usually easier to identify than dominant disorders because the genes are less likely to have more than one rare nonsynonymous variant. The system that screens common genetic variants relies on dbSNP which may not have accurate information about the variation of alleles. Using lists of common variation from a study exome or genome-wide sequenced individual would be more reliable. A challenge in this approach is that as the number of exomes sequenced increases, dbSNP will also increase in the number of uncommon variants. It will be necessary to develop thresholds to define the common variants that are unlikely to be associated with a disease phenotype.
Genetic heterogeneity and population ethnicity are also major limitations as they may increase the number of false positive and false negative findings which will make the identification of candidate genes more difficult. Of course, it is possible to reduce the stringency of the thresholds in the presence of heterogeneity and ethnicity, however this will reduce the power to detect variants as well. Using a genotype-first approach to identify candidate genes might also offer a solution to overcome these limitations.
Unlike common variant analysis, the analysis of rare variants in whole-exome sequencing studies evaluates variant sets rather than single variants. Functional annotations predict the effect or function of rare variants and help prioritize rare functional variants. Incorporating these annotations can effectively boost the power of genetic association of rare variants analysis of whole genome sequencing studies. Some methods and tools have been developed to perform functionally-informed rare variant association analysis by incorporating functional annotations to empower analysis in whole exome sequencing studies.

## Ethical implications

New technologies in genomics have changed the way researchers approach both basic and translational research. With approaches such as exome sequencing, it is possible to significantly enhance the data generated from individual genomes which has put forth a series of questions on how to deal with the vast amount of information. Should the individuals in these studies be allowed to have access to their sequencing information? Should this information be shared with insurance companies? This data can lead to unexpected findings and complicate clinical utility and patient benefit. This area of genomics still remains a challenge and researchers are looking into how to address these questions.

## Applications of exome sequencing

By using exome sequencing, fixed-cost studies can sequence samples to much higher depth than could be achieved with whole genome sequencing. This additional depth makes exome sequencing well suited to several applications that need reliable variant calls.

### Rare variant mapping in complex disorders

Current association studies have focused on common variation across the genome, as these are the easiest to identify with our current assays. However, disease-causing variants of large effect have been found to lie within exomes in candidate gene studies, and because of negative selection, are found in much lower allele frequencies and may remain untyped in current standard genotyping assays. Whole genome sequencing is a potential method to assay novel variant across the genome. However, in complex disorders (such as autism), a large number of genes are thought to be associated with disease risk. This heterogeneity of underlying risk means that very large sample sizes are required for gene discovery, and thus whole genome sequencing is not particularly cost-effective. This sample size issue is alleviated by the development of novel advanced analytic methods, which effectively map disease genes despite the genetic mutations are rare at variant level. In addition, variants in coding regions have been much more extensively studied and their functional implications are much easier to derive, making the practical applications of variants within the targeted exome region more immediately accessible.
Exome sequencing in rare variant gene discovery remains a very active and ongoing area of research, and there is growing evidence that a significant burden of risk is observed across sets of genes. The exome sequencing has been reported rare variants in KRT82 gene in the autoimmune disorder Alopecia Areata.

### Discovery of Mendelian disorders

In Mendelian disorders of large effect, findings thus far suggest one or a very small number of variants within coding genes underlie the entire condition. Because of the severity of these disorders, the few causal variants are presumed to be extremely rare or novel in the population, and would be missed by any standard genotyping assay. Exome sequencing provides high coverage variant calls across coding regions, which are needed to separate true variants from noise. A successful model of Mendelian gene discovery involves the discovery of de novo variants using trio sequencing, where parents and proband are genotyped.

#### Case studies

A study published in September 2009 discussed a proof of concept experiment to determine if it was possible to identify causal genetic variants using exome sequencing. They sequenced four individuals with Freeman–Sheldon syndrome (FSS) (OMIM 193700), a rare autosomal dominant disorder known to be caused by a mutation in the gene MYH3. Eight HapMap individuals were also sequenced to remove common variants in order to identify the causal gene for FSS. After exclusion of common variants, the authors were able to identify MYH3, which confirms that exome sequencing can be used to identify causal variants of rare disorders. This was the first reported study that used exome sequencing as an approach to identify an unknown causal gene for a rare mendelian disorder.
Subsequently, another group reported successful clinical diagnosis of a suspected Bartter syndrome patient of Turkish origin. Bartter syndrome is a renal salt-wasting disease. Exome sequencing revealed an unexpected well-conserved recessive mutation in a gene called SLC26A3 which is associated with congenital chloride diarrhea (CLD). This molecular diagnosis of CLD was confirmed by the referring clinician. This example provided proof of concept of the use of whole-exome sequencing as a clinical tool in evaluation of patients with undiagnosed genetic illnesses. This report is regarded as the first application of next generation sequencing technology for molecular diagnosis of a patient.
A second report was conducted on exome sequencing of individuals with a mendelian disorder known as Miller syndrome (MIM#263750), a rare disorder of autosomal recessive inheritance. Two siblings and two unrelated individuals with Miller syndrome were studied. They looked at variants that have the potential to be pathogenic such as non-synonymous mutations, splice acceptor and donor sites and short coding insertions or deletions.  Since Miller syndrome is a rare disorder, it is expected that the causal variant has not been previously identified. Previous exome sequencing studies of common single nucleotide polymorphisms (SNPs) in public SNP databases were used to further exclude candidate genes. After exclusion of these genes, the authors found mutations in DHODH that were shared among individuals with Miller syndrome. Each individual with Miller syndrome was a compound heterozygote for the DHODH mutations which were inherited as each parent of an affected individual was found to be a carrier.
This was the first time exome sequencing was shown to identify a novel gene responsible for a rare mendelian disease. This finding demonstrated that exome sequencing has the potential to locate causative genes in complex diseases. Targeted capture and massively parallel sequencing is a strategy that can detect variants causing protein-coding changes in individual human genomes with high sensitivity and specificity.

### Clinical diagnostics

Exome sequencing can be used to diagnose the genetic cause of disease in a patient. Identification of the underlying disease gene mutation(s) can have major implications for diagnostic and therapeutic approaches, can guide prediction of disease natural history, and makes it possible to test at-risk family members. There are many factors that make exome sequencing superior to single gene analysis including the ability to identify mutations in genes that were not tested due to an atypical clinical presentation or the ability to identify clinical cases where mutations from different genes contribute to the different phenotypes in the same patient.
Having diagnosed a genetic cause of a disease, this information may guide the selection of appropriate treatment. The first time this strategy was performed successfully in the clinic was in the treatment of an infant with inflammatory bowel disease. A number of conventional diagnostics had previously been used, but the results could not explain the infant's symptoms. Analysis of exome sequencing data identified a mutation in the XIAP gene. Knowledge of this gene's function guided the infant's treatment, leading to a bone marrow transplantation which cured the child of disease.
Researchers have used exome sequencing to identify the underlying mutation for a patient with Bartter Syndrome and congenital chloride diarrhea. Bilgular's group also used exome sequencing and identified the underlying mutation for a patient with severe brain malformations, stating "[These findings] highlight the use of whole exome sequencing to identify disease loci in settings in which traditional methods have proved challenging... Our results demonstrate that this technology will be particularly valuable for gene discovery in those conditions in which mapping has been confounded by locus heterogeneity and uncertainty about the boundaries of diagnostic classification, pointing to a bright future for its broad application to medicine".
Researchers at University of Cape Town, South Africa used exome sequencing to discover the genetic mutation of CDH2 as the underlying cause of a genetic disorder known as arrhythmogenic right ventricle cardiomyopathy (ARVC)‚ which increases the risk of heart disease and cardiac arrest. [1]

### Commercial costs

Multiple companies have offered exome sequencing to consumers. Knome was the first company to offer exome sequencing services to consumers, at a cost of several thousand dollars. Later, 23andMe ran a pilot WES program that was announced in September 2011 and was discontinued in 2012. Consumers could obtain exome data at a cost of $999. The company provided raw data, and did not offer analysis.
In November 2012, DNADTC, a division of Gene by Gene started offering exomes at 80X coverage and introductory price of $695. This price per DNADTC web site is currently $895. In October 2013, BGI announced a promotion for personal whole exome sequencing at 50X coverage for $499.
In June 2016 Genos was able to achieve an even lower price of $399 with a CLIA-certified 75X consumer exome sequenced from saliva.
A 2018 review of 36 studies found the cost for exome sequencing to range from $555 USD to $5,169 USD, with a diagnostic yield ranging from 3% to 79% depending on patient groups.
