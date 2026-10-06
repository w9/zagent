---
title: Gene set enrichment analysis
requested_title: Gene set enrichment analysis
revision_id: 1368841655
revision_timestamp: '2026-08-11T11:07:42Z'
url: https://en.wikipedia.org/w/index.php?oldid=1368841655
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

Gene set enrichment analysis (GSEA) (also called functional enrichment analysis or pathway enrichment analysis) is a method to identify classes of genes or proteins that are over-represented in a large set of genes or proteins, and may have an association with different phenotypes (e.g. different organism growth patterns or diseases). The method uses statistical approaches to identify significantly enriched or depleted groups of genes. Transcriptomics technologies and proteomics results often identify thousands of genes, which are used for the analysis.
Researchers performing high-throughput experiments that yield sets of genes (for example, genes that are differentially expressed under different conditions) often want to retrieve a functional profile of that gene set, in order to better understand the underlying biological processes. This can be done by comparing the input gene set to each of the bins (terms) in the gene ontology – a statistical test can be performed for each bin to see if it is enriched for the input genes.

## Background

After the completion of the Human Genome Project, the problem of how to interpret and analyze it remained. In order to seek out genes associated with diseases, DNA microarrays were used to measure the amount of gene expression in different cells. Microarrays on thousands of different genes were carried out, and comparisons of the results of two different cell categories, e.g. normal cells versus cancerous cells.  However, this method of comparison is not sensitive enough to detect the subtle differences between the expression of individual genes, because diseases typically involve entire groups of genes. Multiple genes are linked to a single biological pathway, and so it is the additive change in expression within gene sets that leads to the difference in phenotypic expression. As stated in the original paper, "Gene Set Enrichment Analysis [was] designed to detect modest but coordinate changes in the expression of groups of functionally related genes".  By doing so, this method resolves the problem of the undetectable, small changes in the expression of single genes.

## Methods

Gene set enrichment analysis uses a priori gene sets that have been grouped together by their involvement in the same biological pathway, or by proximal location on a chromosome. A database of these predefined sets can be found at the Molecular signatures database (MSigDB). In GSEA, DNA microarrays, or now RNA-Seq, are still performed and compared between two cell categories, but instead of focusing on individual genes in a long list, the focus is put on a gene set. Researchers analyze whether the majority of genes in the set fall in the extremes of this list: the top and bottom of the list correspond to the largest differences in expression between the two cell types. If the gene set falls at either the top (over-expressed) or bottom (under-expressed), it is thought to be related to the phenotypic differences.
In the method that is typically referred to as standard GSEA, there are three steps involved in the analytical process. The general steps are summarized below:

Calculate the enrichment score (ES) that represents the amount to which the genes in the set are over-represented at either the top or bottom of the list. This score is a Kolmogorov–Smirnov-like statistic.
Estimate the statistical significance of the ES. This calculation is done by a phenotypic-based permutation test in order to produce a null distribution for the ES. The P value is determined by comparison to the null distribution.
Calculating significance this way tests for the dependence of the gene set on the diagnostic/phenotypic labels
Adjust for multiple hypothesis testing for when a large number of gene sets are being analyzed at one time. The enrichment scores for each set are normalized and a false discovery rate is calculated.
This can be described as:

P

h
i
t

(
S
,
i
)
=

∑

g

j

∈
S
,
j
≤
i

|

r

j

|

p

N

R

;

P

m
i
s
s

(
S
,
i
)
=

∑

g

j

∉
S
,
j
≤
i

1

N
−

N

H

;

N

R

=

∑

g

j

∈
S

|

r

j

|

p

;

E
S
=
P
(
S
,
i
)
=

P

h
i
t

(
S
,
i
)
−

P

m
i
s
s

(
S
,
i
)
=
m
a
x
(

|

P

h
i
t

(
S
,
i
)
−

P

m
i
s
s

(
S
,
i
)

|

)

Where

r

is the rank of the gene,

p

is the power usually set to 1 (if it were 0, it would be equivalent to the Kolmogorov–Smirnov test).

### Limitations and proposed alternatives

#### SEA

When GSEA was first introduced in 2003 some immediate concerns were raised regarding its methodology. These criticisms led to the use of the correlation-weighted Kolmogorov–Smirnov test, the normalized ES, and the false discovery rate calculation, all of which are the factors that currently define standard GSEA. However, GSEA has now also been criticized for the fact that its null distribution is superfluous, and too difficult to be worth calculating, as well as the fact that its Kolmogorov–Smirnov-like statistic is not as sensitive as the original. As an alternative, the method known as Simpler Enrichment Analysis (SEA), was proposed. This method assumes gene independence and uses a simpler approach to calculate t-test. However, it is thought that these assumptions are in fact too simplifying, and gene correlation cannot be disregarded.

#### SGSE

One other limitation to Gene Set Enrichment Analysis is that the results are very dependent on the algorithm that clusters the genes, and the number of clusters being tested. Spectral Gene Set Enrichment (SGSE) is a proposed, unsupervised test. The method's founders claim that it is a better way to find associations between MSigDB gene sets and microarray data. The general steps include:
1.    Calculating the association between principal components and gene sets.
2.    Using the weighted Z-method to calculate the association between the gene sets and the spectral structure of the data.

## Tools

GSEA uses complicated statistics, so it requires a computer program to run the calculations. GSEA has become standard practice, and there are many websites and downloadable programs that will provide the data sets and run the analysis.

### MOET

Multi-Ontology Enrichment Tool (MOET) is a web-based ontology analysis tool that provides functionality for multiple ontologies, including Disease, GO, Pathway, Phenotype, and Chemical entities (ChEBI) for multiple species, including rat, mouse, human, bonobo, squirrel, dog, pig, chinchilla, naked mole-rat and vervet (green monkey). It outputs a downloadable graph and a list of statistically overrepresented terms in the user's list of genes using hypergeometric distribution. MOET also displays the corresponding Bonferroni correction and odds ratio on the results page. It is simple to use, and results are provided with a few clicks in seconds; no software installations or programming skills are required. In addition, MOET is updated weekly, providing the user with the most recent data for analyses.

### NASQAR

NASQAR (Nucleic Acid SeQuence Analysis Resource) is an open source, web-based platform for high-throughput sequencing data analysis and visualization. GSEA can be run using the R-based clusterProfiler package.  NASQAR currently supports GO Term and KEGG Pathway enrichment with all organisms supported by an Org.Db database.

### PlantRegMap

The gene ontology (GO) annotation for 165 plant species and GO enrichment analysis is available.

### MSigDB

The Molecular Signatures Database hosts an extensive collection of annotated gene sets that can be used with most GSEA Software.

### Broad Institute

The Broad Institute website is in cooperation with MSigDB and has a downloadable GSEA software, as well a general tutorial.

### WebGestalt

WebGestalt  is a web based gene set analysis toolkit. It supports three well-established and complementary methods for enrichment analysis, including Over-Representation Analysis (ORA), Gene Set Enrichment Analysis (GSEA), and Network Topology-based Analysis (NTA). Analysis can be performed against 12 organisms and 321,251 functional categories using 354 gene identifiers from various databases and technology platforms.

### Enrichr

Enrichr is a gene set enrichment analysis tool for mammalian gene sets. It contains background libraries for transcription regulation, pathways and protein interactions, ontologies including GO and the human and mouse phenotype ontologies, signatures from cells treated with drugs, gene sets associated with human diseases, and expression of genes in different cells and tissues. The background libraries are from over 200 resources and contain over 450,000 annotated gene sets. The tool can be accessed through API and provides different ways to visualize the results.

### GeneSCF

GeneSCF is a real-time based functional enrichment tool with support for multiple organisms and is designed to overcome the problems associated with using outdated resources and databases. Advantages of using GeneSCF: real-time analysis, users do not have to depend on enrichment tools to get updated, easy for computational biologists to integrate GeneSCF with their NGS pipeline, it supports multiple organisms, enrichment analysis for multiple gene list using multiple source database in single run, retrieve or download complete GO terms/Pathways/Functions with associated genes as simple table format in a plain text file.

### DAVID

DAVID is the database for annotation, visualization and integrated discovery, a bioinformatics tool that pools together information from most major bioinformatics sources, with the aim of analyzing large gene lists in a high-throughput manner. DAVID goes beyond standard GSEA with additional functions like switching between gene and protein identifiers on the genome-wide scale, however, the annotations used by DAVID was not updated since October 2016 to Dec 2021, which can have a considerable impact on practical interpretation of results. However, A most recent update was performed in 2021

### Metascape

Metascape is a biologist-oriented gene-list analysis portal. Metascape integrates pathway enrichment analysis, protein complex analysis, and multi-list meta-analysis into one seamless workflow accessible through a significantly simplified user interface.  Metascape maintains analysis accuracy by updating its 40 underlying knowledgebases monthly. Metascape presents results using easy-to-interpret graphics, spreadsheets, and publication quality presentations, and is freely available.

### AmiGO 2

The Gene Ontology (GO) consortium has also developed their own online GO term enrichment tool,
allowing species-specific enrichment analysis versus the complete database, coarser-grained GO slims, or custom references.

### GREAT

Genomic region enrichment of annotations tool (GREAT) is a software which takes advantage of regulatory domains to better associate gene ontology terms to genes. Its primary purpose is to identify pathways and processes that are significantly associated with factor regulating activity. This method maps genes with regulatory regions through a hypergeometric test over genes, inferring proximal gene regulatory domains. It does this by using the total fraction of the genome associated with a given ontology term as the expected fraction of input regions associated with the term by chance. Enrichment is calculated by all regulatory regions, and several experiments were performed to validate GREAT, one of which being enrichment analyses done on 8 ChIP-seq datasets.

### FunRich

The Functional Enrichment Analysis (FunRich) tool is mainly used for the functional enrichment and network analysis of Omics data.

### FuncAssociate

The FuncAssociate tool enables Gene Ontology and custom enrichment analyses. It allows inputting ordered sets as well as weighted gene space files for background.

### InterMine

Instances of InterMine automatically provide enrichment analysis  for uploaded sets of genes and other biological entities.

### ToppGene suite

ToppGene is a one-stop portal for gene list enrichment analysis and candidate gene prioritization based on functional annotations and protein interactions network.  Developed and maintained by the Division of Biomedical Informatics at Cincinnati Children's Hospital Medical Center.

### QuSAGE

Quantitative Set Analysis for Gene Expression (QuSAGE) is a computational method for gene set enrichment analysis. QuSAGE improves power by accounting for inter-gene correlations and quantifies gene set activity with a complete probability density function (PDF). From this PDF, P values and confidence intervals can be easily extracted. Preserving the PDF also allows for post-hoc analysis (e.g., pair-wise comparisons of gene set activity) while maintaining statistical traceability. The applicability of QuSAGE has been extended to longitudinal studies by adding functionality for general linear mixed models. QuSAGE was used by the NIH/NIAID to identify baseline transcriptional signatures that were associated with human influenza vaccination responses. QuSAGE is available as a R/Bioconductor package.

### Blast2GO

Blast2GO is a bioinformatics platform for functional annotation and analysis of genomic datasets.  This tool allows to perform gene set enrichment analysis, among other functions.

### g:Profiler

g:Profiler is a toolset for finding biological categories enriched in gene lists, conversions between gene identifiers and mappings to their orthologs. g:Profiler relies on Ensembl as a primary data source and follows their quarterly release cycle while updating the other data sources simultaneously. g:Profiler supports close to 500 species and strains, including vertebrates, plants, fungi, insects and parasites.

## Applications

### Genome-wide association studies

Single-nucleotide polymorphisms, or SNPs, are single base mutations that may be associated with diseases. One base change has the potential to affect the protein that results from that gene being expressed; however, it also has the potential to have no effect at all. Genome-wide association studies (GWAS) are comparisons between healthy and disease genotypes to try to find SNPs that are overrepresented in the disease genomes, and might be associated with that condition. Before GSEA, the accuracy of genome-wide SNP association studies was severely limited by a high number of false positives. The theory that the SNPs contributing to a disease tend to be grouped in a set of genes that are all involved in the same biological pathway, is what the GSEA-SNP method is based on. This application of GSEA does not only aid in the discovery of disease-associated SNPs, but helps illuminate the corresponding pathways and mechanisms of the diseases.

### Spontaneous preterm birth

Gene set enrichment methods led to the discovery of new suspect genes and biological pathways related to spontaneous preterm births. Exome sequences from women who had experienced SPTB were compared to those from females from the 1000 Genome Project, using a tool that scored possible disease-causing variants. Genes with higher scores were then run through different programs to group them into gene sets based on pathways and ontology groups. This study found that the variants were significantly clustered in sets related to several pathways, all suspects in SPTB.

### Cancer cell profiling

Gene set enrichment analysis can be used to understand the changes that cells undergo during carcinogenesis and metastasis. In a study, microarrays were performed on renal cell carcinoma metastases, primary renal tumors, and normal kidney tissue, and the data was analyzed using GSEA. This analysis showed significant changes of expression in genes involved in pathways that have not been previously associated with the progression of renal cancer. From this study, GSEA has provided potential new targets for renal cell carcinoma therapy.

### Schizophrenia

GSEA can be used to help understand the molecular mechanisms of complex disorders. Schizophrenia is a largely heritable disorder, but is also very complex, and the onset of the disease involves many genes interacting within multiple pathways, as well the interaction of those genes with environmental factors. For instance, epigenetic changes, like DNA methylation, are affected by the environment, but are also inherently dependent on the DNA itself. DNA methylation is the most well-studied epigenetic change, and was recently analyzed using GSEA in relation to schizophrenia-related intermediate phenotypes. Researchers ranked genes for their correlation between methylation patterns and each of the phenotypes. They then used GSEA to look for an enrichment of genes that are predicted to be targeted by microRNAs in the progression of the disease.

### Depression

GSEA can help provide molecular evidence for the association of biological pathways with diseases. Previous studies have shown that long-term depression symptoms are correlated with changes in immune response and inflammatory pathways. Genetic and molecular evidence was sought to support this. Researchers took blood samples from sufferers of depression, and used genome-wide expression data, along with GSEA to find expression differences in gene sets related to inflammatory pathways. This study found that those people who rated with the most severe depression symptoms also had significant expression differences in those gene sets, and this result supports the association hypothesis.

### Microbiome research

Gene set enrichment analysis has been adapted for microbiome studies through taxon set enrichment analysis (TSEA) and microbe set enrichment analysis (MSEA). Instead of analyzing gene sets, these approaches tests for enrichment of predefined sets of microbial species or genera enabling interpretation of microbial community shifts in terms of higher-level taxonomy or functional roles.
