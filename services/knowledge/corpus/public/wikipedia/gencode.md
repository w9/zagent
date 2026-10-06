---
title: GENCODE
requested_title: GENCODE
revision_id: 1365332047
revision_timestamp: '2026-07-21T19:10:37Z'
url: https://en.wikipedia.org/w/index.php?oldid=1365332047
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

GENCODE is a scientific project in genome research and part of the ENCODE (ENCyclopedia Of DNA Elements) scale-up project.
The GENCODE consortium was initially formed as part of the pilot phase of the ENCODE project to identify and map all protein-coding genes within the ENCODE regions (approx. 1% of Human genome). Given the initial success of the project, GENCODE now aims to build an "Encyclopedia of genes and genes variants".
The result will be a set of annotations including all protein-coding loci with alternatively transcribed variants, non-coding loci with transcript evidence, and pseudogenes.

## Current progress

GENCODE is currently progressing towards its goals in Phase 2 of the project.
The most recent release of the Human geneset annotations is Gencode 36, with a freeze date of December 2020. This release utilises the latest GRCh38 human reference genome assembly.
The latest release for the mouse geneset annotations is Gencode M25, also with a freeze date December 2020.
Since September 2009, GENCODE has been the human gene set used by the Ensembl project and each new GENCODE release corresponds to an Ensembl release.

## History

2003 September
The project was designed with three phases - Pilot, Technology development and Production phase.
The pilot stage of the ENCODE project aimed to investigate in great depth, computationally and experimentally, 44 regions totaling 30 Mb of sequence representing approximately 1% of the human genome. As part of this stage, the GENCODE consortium was formed to identify and map all protein-coding genes within the ENCODE regions. It was envisaged that the results of the first two phases will be used to determine the best path forward for analysing the remaining 99% of the human genome in a cost-effective and comprehensive production phase.
2005 April
The first release of the annotation of the 44 ENCODE regions was frozen on 29 April 2005 and was used in the first ENCODE Genome Annotation Assessment Project (E-GASP) workshop. GENCODE Release 1 contained 416 known loci, 26 novel (coding DNA sequence) CDS loci, 82 novel transcript loci, 78 putative loci, 104 processed pseudogenes and 66 unprocessed pseudogenes.
2005 October
A second version (release 02) was frozen on 14 October 2005, containing updates following discoveries from experimental validations using RACE and RT-PCR techniques. GENCODE Release 2 contained 411 known loci, 30 novel CDS loci, 81 novel transcript loci, 83 putative loci, 104 processed pseudogenes and 66 unprocessed pseudogenes.
2007 June
The conclusions from the pilot project were published in June 2007. The findings highlighted the success of the pilot project to create a feasible platform and new technologies to characterise functional elements in the human genome, which paves the way for opening research into genome-wide studies.
2007 October
New funding was part of NHGRI's endeavour to scale-up the ENCODE Project to a production phase on the entire genome along with additional pilot-scale studies.
2012 September
In September 2012, The GENCODE consortium published a major paper discussing the results from a major release – GENCODE Release 7, which was frozen in December 2011.
2018
In 2018, one of the latest additions to the GENCODE project was the CRISPR/Cas9 track on human and model organism assemblies. CRISPR is a genome editing technique that uses sequences of RNA that successfully bind to the region edited with high specificity. The new track was designed to assist in the search for appropriate guide sentences by listing potential binding sites for the CRISPR/Cas9 complex that are next to transcribed regions, or within 200 bp of one. For each site, the track provides possible guide sequences along with a collection of predicted efficiency and specificity scores for those guide sequences. It also provides information about potential off-targets, grouped by the number of missmatches between the off-target and the guide.
2020
Among other achievements, it has been completed the first pass manual annotation of the mouse reference genome, it has started a cooperation with RefSeq and Uniprot reference annotation databases toward achieving annotation convergence, and the annotation of lncRNAs has been improved via the discovery of novel loci and novel transcripts at existing loci. Also, given the COVID-19 pandemic during 2020, there has been an urge to support research responding to the situation, so GENCODE has reviewed and improved the annotation for a set of protein-coding genes associated with SARSCoV-2 infection.

## Key Participants

The key participants of the GENCODE project have remained relatively consistent throughout its various phases, with the Wellcome Trust Sanger Institute now leading the overall efforts of the project.
A summary of key participating institutions of each phase is listed below:

### Participants, PIs and CO-PIs

Source:

Paul Flicek (Lead PI), EMBL European Bioinformatics Institute, Cambridge, UK
Roderic Guigo (PI), Centre de Regulació Genòmica (CRG), Barcelona, Catalonia, Spain
Manolis Kellis (PI), Massachusetts Institute of Technology (MIT), Cambridge, MA, USA
Mark B. Gerstein (PI), Yale University, New Haven, CT, USA
Benedict Paten (PI), University of California, Santa Cruz, CA, USA
Michael Tress, Spanish National Cancer Research Centre (CNIO), Madrid, Spain
Jyoti Choudhary, Institute of Cancer Research (ICR), London, UK

## Key Statistics

Since its inception, GENCODE has released 36 versions of the Human gene set annotations (excluding minor updates).
The key summary statistics of the most recent GENCODE Human gene set annotation (Release 49) is shown below:

Through advancements in sequencing technologies (such as RT-PCR-seq), increased coverage from manual annotations (HAVANA group), and improvements to automatic annotation algorithms using Ensembl, the accuracy and completeness of GENCODE annotations have been continuously refined through its iteration of releases.
A comparison of key statistics from 3 major GENCODE releases until 2014 is shown below. It is evident that although the coverage, in terms of total number of genes discovered, is steady increasing, the number of protein-coding genes has actually decreased. This is mostly attributed to new experimental evidence obtained using Cap Analysis Gene Expression (CAGE) clusters, annotated PolyA sites, and peptide hits.

Version 7 (December 2010 freeze, GRCh37) - Ensembl 62
Version 10 (July 2011 freeze, GRCh37) - Ensembl 65
Version 20 (April 2014 freeze, GRCh38) - Ensembl 76

## Methodology

Putative loci can be verified by wet-lab experiments and computational predictions are analysed manually.
Currently, to ensure a set of annotation covers the complete genome rather than just the regions that have been manually annotated, a merged data set is created using manual annotations from HAVANA, together with automatic annotations from the Ensembl automatically annotated gene set. This process also adds unique full-length CDS predictions from the Ensembl protein coding set into manually annotated genes, to provide the most complete and up-to-date annotation of the genome possible.

### Automatic annotation (Ensembl)

Ensembl transcripts are products of the Ensembl automatic gene annotation system (a collection of gene annotation pipelines), termed the Ensembl gene build. All Ensembl transcripts are based on experimental evidence and thus the automated pipeline relies on the mRNAs and protein sequences deposited into public databases from the scientific community.

### Manual Annotation (HAVANA group)

There are several analysis groups in the GENCODE consortium that run pipelines that aid the manual annotators in producing models in unannotated regions, and to identify potential missed or incorrect manual annotation, including completely missing loci, missing alternative isoforms, incorrect splice sites and incorrect biotypes. These are fed back to the manual annotators using the AnnoTrack tracking system. Some of these pipelines use data from other ENCODE subgroups including RNASeq data, histone modification and CAGE and Ditag data. RNAseq data is an important new source of evidence, but generating complete gene models from it is a difficult problem. As part of GENCODE, a competition was run to assess the quality of predictions produced by various RNAseq prediction pipelines (Refer to RGASP below). To confirm uncertain models, GENCODE also has an experimental validation pipeline using RNA sequencing and RACE.

### Assessing quality

For GENCODE 7, transcript models are assigned a high or low level of support based on a new method developed to score the quality of transcripts.

## Usage/Access

The current GENCODE Human gene set version (GENCODE Release 20) includes annotation files (in GTF and GFF3 formats), FASTA files and METADATA files associated with the GENCODE annotation on all genomic regions (reference-chromosomes/patches/scaffolds/haplotypes). The annotation data is referred on reference chromosomes and stored in separated files which include: Gene annotation, PolyA features annotated by HAVANA, (Retrotransposed) pseudogenes predicted by the Yale & UCSC pipelines, but not by HAVANA, long non-coding RNAs, and tRNA structures predicted by tRNA-Scan.
Some examples of the lines in the GTF format are shown below:

The columns within the GENCODE GTF file formats are described below.
Format description of GENCODE GTF file. TAB-separated standard GTF columns

Description of key-value pairs in 9th column of the GENCODE GTF file (format: key "value")

### Biodalliance Genome Browser

Also, the GENCODE website contains a Genome Browser for human and mouse where you can reach any genomic region by giving the chromosome number and start-end position (e.g. 22:30,700,000..30,900,000), as well as by ENS transcript id (with/without version), ENS gene id (with/without version) and gene name. The browser is powered by Biodalliance.

## Challenges

### Definition of a "gene"

The definition of a "gene" has never been a trivial issue, with numerous definitions and notions proposed throughout the years since the discovery of the human genome. First, genes were conceived in the 1900s as discrete units of heredity, then it was thought as the blueprint for protein synthesis, and in more recent times, it was being defined as genetic code that is transcribed into RNA. Although the definition of a gene has evolved greatly over the last century, it has remained a challenging and controversial subject for many researchers. With the advent of the ENCODE/GENCODE project, even more problematic aspects of the definition have been uncovered, including alternative splicing (where a series of exons are separated by introns), intergenic transcriptions, and the complex patterns of dispersed regulation, together with non-genic conservation and the abundance of noncoding RNA genes. As GENCODE endeavours to build an encyclopaedia of genes and gene variants, these problems presented a mounting challenge for the GENCODE project to come up with an updated notion of a gene.

## Human Genome Project

The Human Genome Project was an international research effort to determine the sequence of the human genome and identify the genes that it contains. The Project was coordinated by the National Institutes of Health and the U.S. Department of Energy. Additional contributors included universities across the United States and international partners in the United Kingdom, France, Germany, Japan, and China. The Human Genome Project formally began in 1990 and was completed in 2003, 2 years ahead of its original schedule.

## Sub Projects

### Ensembl

Ensembl is part of the GENCODE project.

### lncRNA Expression Microarray Design

A key research area of the GENCODE project was to investigate the biological significance of long non-coding RNAs (lncRNA). To better understand the lncRNA expression in Humans, a sub project was created by GENCODE to develop custom microarray platforms capable of quantifying the transcripts in the GENCODE lncRNA annotation. A number of designs have been created using the Agilent Technologies eArray system, and these designs are available in a standard custom Agilent format.

### RGASP

The RNA-seq Genome Annotation Assessment Project (RGASP) project is designed to assess the effectiveness of various computational methods for high quality RNA-sequence data analysis. The primary goals of RGASP are to provide an unbiased evaluation for RNA-seq alignment, transcript characterisation (discovery, reconstruction and quantification) software, and to determine the feasibility of automated genome annotations based on transcriptome sequencing.
RGASP is organised in a consortium framework modelled after the EGASP (ENCODE Genome Annotation Assessment Project) gene prediction workshop, and two rounds of workshops have been conducted to address different aspects of RNA-seq analysis as well as changing sequencing technologies and formats. One of the main discoveries from rounds 1 & 2 of the project was the importance of read alignment on the quality of gene predictions produced. Hence, a third round of RGASP workshop is currently being conducted (in 2014) to focus primarily on read mapping to the genome.
