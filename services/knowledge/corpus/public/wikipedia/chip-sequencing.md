---
title: ChIP sequencing
requested_title: ChIP sequencing
revision_id: 1374647010
revision_timestamp: '2026-09-13T08:20:57Z'
url: https://en.wikipedia.org/w/index.php?oldid=1374647010
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

ChIP-sequencing, also known as ChIP-seq, is a method used to analyze protein interactions with DNA. ChIP-seq combines chromatin immunoprecipitation (ChIP) with massively parallel DNA sequencing to identify the binding sites of DNA-associated proteins. It can be used to map global binding sites precisely for any protein of interest. Previously, ChIP-on-chip was the most common technique utilized to study these protein–DNA relations.

## Uses

ChIP-seq is primarily used to determine how transcription factors and other chromatin-associated proteins influence phenotype-affecting mechanisms. Determining how proteins interact with DNA to regulate gene expression is essential for fully understanding many biological processes and disease states. This epigenetic information is complementary to genotype and expression analysis. ChIP-seq technology is currently seen primarily as an alternative to ChIP-chip which requires a hybridization array. This introduces some bias, as an array is restricted to a fixed number of probes. Sequencing, by contrast, is thought to have less bias, although the sequencing bias of different sequencing technologies is not yet fully understood.
Specific DNA sites in direct physical interaction with transcription factors and other proteins can be isolated by chromatin immunoprecipitation. ChIP produces a library of target DNA sites bound to a protein of interest. Massively parallel sequence analyses are used in conjunction with whole-genome sequence databases to analyze the interaction pattern of any protein with DNA, or the pattern of any epigenetic chromatin modifications. This can be applied to the set of ChIP-able proteins and modifications, such as transcription factors, polymerases and transcriptional machinery, structural proteins, protein modifications, and DNA modifications. As an alternative to the dependence on specific antibodies, different methods have been developed to find the superset of all nucleosome-depleted or nucleosome-disrupted active regulatory regions in the genome, like DNase-Seq and FAIRE-Seq.

## Workflow of ChIP-sequencing

### ChIP

ChIP is a powerful method to selectively enrich for DNA sequences bound by a particular protein in living cells. However, the widespread use of this method has been limited by the lack of a sufficiently robust method to identify all of the enriched DNA sequences. The ChIP wet lab protocol contains ChIP and hybridization. There are essentially five parts to the ChIP protocol that aid in better understanding the overall process of ChIP. In order to carry out the ChIP, the first step is cross-linking using formaldehyde and large batches of the DNA in order to obtain a useful amount. The cross-links are made between the protein and DNA, but also between RNA and other proteins. The second step is the process of chromatin fragmentation which breaks up the chromatin in order to get high quality DNA pieces for ChIP analysis in the end. These fragments should be cut to become under 500 base pairs each to have the best outcome for genome mapping.
The third step is called chromatin immunoprecipitation, which is what ChIP is short for. The ChIP process enhances specific crosslinked DNA-protein complexes using an antibody against the protein of interest followed by incubation and centrifugation to obtain the immunoprecipitation. The immunoprecipitation step also allows for the removal of non-specific binding sites. The fourth step is DNA recovery and purification, taking place by the reversed effect on the cross-link between DNA and protein to separate them and cleaning DNA with an extraction. The fifth and final step is the analyzation step of the ChIP protocol by the process of qPCR, ChIP-on-chip (hybrid array) or ChIP sequencing. Oligonucleotide adaptors are then added to the small stretches of DNA that were bound to the protein of interest to enable massively parallel sequencing. Through the analysis, the sequences can then be identified and interpreted by the gene or region to where the protein was bound.

### Sequencing

After size selection, all the resulting ChIP-DNA fragments are sequenced simultaneously using a genome sequencer. A single sequencing run can scan for genome-wide associations with high resolution, meaning that features can be located precisely on the chromosomes. ChIP-chip, by contrast, requires large sets of tiling arrays for lower resolution.
There are many new sequencing methods used in this sequencing step. Some technologies that analyze the sequences can use cluster amplification of adapter-ligated ChIP DNA fragments on a solid flow cell substrate to create clusters of approximately 1000 clonal copies each. The resulting high density array of template clusters on the flow cell surface is sequenced by a genome analyzing program. Each template cluster undergoes sequencing-by-synthesis in parallel using novel fluorescently labelled reversible terminator nucleotides. Templates are sequenced base-by-base during each read. Then, the data collection and analysis software aligns sample sequences to a known genomic sequence to identify the ChIP-DNA fragments.

## Quality control

ChIP-seq offers us a fast analysis, however, a quality control must be performed to make sure that the results obtained are reliable:

Non-redundant fraction: low-complexity regions should be removed as they are not informative and may interfere with mapping in the reference genome.
Fragments in peaks: ratio of reads that are located in peaks over reads that are located where there isn't a peak.

## Sensitivity

Sensitivity of this technology depends on the depth of the sequencing run (i.e. the number of mapped sequence tags), the size of the genome and the distribution of the target factor.
The sequencing depth is directly correlated with cost. If abundant binders in large genomes have to be mapped with high sensitivity, costs are high as an enormously high number of sequence tags will be required. This is in contrast to ChIP-chip in which the costs are not correlated with sensitivity.
Unlike microarray-based ChIP methods, the precision of the ChIP-seq assay is not limited by the spacing of predetermined probes. By integrating a large number of short reads, highly precise binding site localization is obtained. Compared to ChIP-chip, ChIP-seq data can be used to locate the binding site within few tens of base pairs of the actual protein binding site. Tag densities at the binding sites are a good indicator of protein–DNA binding affinity, which makes it easier to quantify and compare binding affinities of a protein to different DNA sites.

## Current research

STAT1 DNA association: ChIP-seq was used to study STAT1 targets in HeLa S3 cells which are clones of the HeLa line that are used for analysis of cell populations. The performance of ChIP-seq was then compared to the alternative protein–DNA interaction methods of ChIP-PCR and ChIP-chip.
Nucleosome Architecture of Promoters: Using ChIP-seq, it was determined that Yeast genes seem to have a minimal nucleosome-free promoter region of 150bp in which RNA polymerase can initiate transcription.
Transcription factor conservation: ChIP-seq was used to compare conservation of TFs in the forebrain and heart tissue in embryonic mice. The authors identified and validated the heart functionality of transcription enhancers, and determined that transcription enhancers for the heart are less conserved than those for the forebrain during the same developmental stage.
Genome-wide ChIP-seq: ChIP-sequencing was completed on the worm C. elegans to explore genome-wide binding sites of 22 transcription factors. Up to 20% of the annotated candidate genes were assigned to transcription factors. Several transcription factors were assigned to non-coding RNA regions and may be subject to developmental or environmental variables. The functions of some of the transcription factors were also identified. Some of the transcription factors regulate genes that control other transcription factors. These genes are not regulated by other factors. Most transcription factors serve as both targets and regulators of other factors, demonstrating a network of regulation.
Inferring regulatory network: ChIP-seq signal of Histone modification were shown to be more correlated with transcription factor motifs at promoters in comparison to RNA level. Hence author proposed that using histone modification ChIP-seq would provide more reliable inference of gene-regulatory networks in comparison to other methods based on expression.
ChIP-seq offers an alternative to ChIP-chip. STAT1 experimental ChIP-seq data have a high degree of similarity to results obtained by ChIP-chip for the same type of experiment, with greater than 64% of peaks in shared genomic regions. Because the data are sequence reads, ChIP-seq offers a rapid analysis pipeline as long as a high-quality genome sequence is available for read mapping and the genome doesn't have repetitive content that confuses the mapping process. ChIP-seq also has the potential to detect mutations in binding-site sequences, which may directly support any observed changes in protein binding and gene regulation.

## Computational analysis

As with many high-throughput sequencing approaches, ChIP-seq generates extremely large data sets, for which appropriate computational analysis methods are required. To predict DNA-binding sites from ChIP-seq read count data, peak calling methods have been developed. One of the most popular methods is MACS which empirically models the shift size of ChIP-Seq tags, and uses it to improve the spatial resolution of predicted binding sites. MACS is optimized for higher resolution peaks, while another popular algorithm, SICER is programmed to call for broader peaks, spanning over kilobases to megabases in order to search for broader chromatin domains. SICER is more useful for histone marks spanning gene bodies. A mathematical more rigorous method BCP (Bayesian Change Point) can be used for both sharp and broad peaks with faster computational speed, see benchmark comparison of ChIP-seq peak-calling tools by Thomas et al. (2017).
Another relevant computational problem is differential peak calling, which identifies significant differences in two ChIP-seq signals from distinct biological conditions. Differential peak callers segment two ChIP-seq signals and identify differential peaks using Hidden Markov Models. Examples for two-stage differential peak callers are ChIPDiff and ODIN.
To reduce spurious sites from ChIP-seq, multiple experimental controls can be used to detect binding sites from an IP experiment. Bay2Ctrls adopts a Bayesian model to integrate the DNA input control for the IP, the mock IP and its corresponding DNA input control to predict binding sites from the IP. This approach is particularly effective for complex samples such as whole model organisms. In addition, the analysis indicates that for complex samples mock IP controls substantially outperform DNA input controls probably due to the active genomes of the samples.
