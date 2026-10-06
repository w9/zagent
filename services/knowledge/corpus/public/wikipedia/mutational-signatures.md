---
title: Mutational signatures
requested_title: Mutational signatures
revision_id: 1365730613
revision_timestamp: '2026-07-24T02:59:01Z'
url: https://en.wikipedia.org/w/index.php?oldid=1365730613
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

Mutational signatures are characteristic combinations of mutation types arising from specific mutagenesis processes such as DNA replication infidelity, exogenous and endogenous genotoxin exposures, defective DNA repair pathways, and DNA enzymatic editing.
The term is used for two distinct concepts, often conflated: mutagen signatures and tumor signatures. Its original use, mutagen signature, referred to a pattern of mutations made in the laboratory by a known mutagen and not made by other mutagens – unique to the mutagen as a human signature is unique to the signer. Uniqueness allows the mutagen to be deduced from a cell's mutations  Later, the phrase referred to a pattern of mutations characteristic of a tumor type, although usually not unique to the tumor type nor to a mutagen. If a tumor mutational signature matches a unique mutagen mutational signature, it is valid to deduce the carcinogen exposure or mutagenesis process that occurred in the patient's distant past. Increasingly refined tumor signatures are becoming assignable to mutagen signatures.
Deciphering mutational signatures in cancer provides insight into the biological mechanisms involved in carcinogenesis and normal somatic mutagenesis. Mutational signatures have shown their applicability in cancer treatment and cancer prevention. Advances in the fields of oncogenomics have enabled the development and use of molecularly targeted therapy, but such therapies historically focused on inhibition of oncogenic drivers (e.g. EGFR gain-of-function mutation and EGFR inhibitor treatment in colorectal cancer). More recently, mutational signatures profiling has proven successful in guiding oncological management and use of targeted therapies (e.g. immunotherapy in mismatch repair deficient of diverse cancer types, platinum and PARP inhibitor to exploit synthetic lethality in homologous recombination deficient breast cancer).

## General concepts

### Mechanisms – overview

The biological mutagenesis mechanisms underlying mutational signatures (e.g. COSMIC Signatures 1 to 30) include, but are not limited to:

### Genomic data

Cancer mutational signatures analyses require genomic data from cancer genome sequencing with paired-normal DNA sequencing in order to create the tumor mutation catalog (mutation types and counts) of a specific tumor. Different types of mutations (e.g. single nucleotide variants, indels, structural variants) can be used individually or in combination to model mutational signatures in cancer.

#### Types of mutations: base substitutions

There are six classes of base substitution: C>A, C>G, C>T, T>A, T>C, T>G. The G>T substitution is considered equivalent to the C>A substitution because it is not possible to differentiate on which DNA strand (forward or reverse) the substitution initially occurred. Both the C>A and G>T substitutions are therefore counted as part of the "C>A" class. For the same reason the G>C, G>A, A>T, A>G and A>C mutations are counted as part of the "C>G", "C>T", "T>A", "T>C" and "T>G" classes respectively.
Taking the information from the 5' and 3' adjacent bases (also called flanking base pairs or trinucleotide context) lead to 96 possible mutation types (e.g. A[C>A]A, A[C>A]T, etc.). The mutation catalog of a tumor is created by categorizing each single nucleotide variant (SNV) (synonyms: base-pair substitution or substitution point mutation) in one of the 96 mutation types and counting the total number of substitutions for each of these 96 mutation types (see figure).

#### Tumor mutation catalog

Once the mutation catalog (e.g. counts for each of the 96 mutation types) of a tumor is obtained, there are two approaches to decipher the contributions of different mutational signatures to tumor genomic landscape:
The mutation catalog of the tumor is compared to a reference mutation catalogue, or mutational signatures reference dataset, such as the 21 Signatures of Mutational Processes in Human Cancer  from the Catalogue of Somatic Mutation In Cancer (COSMIC) database.
De novo mutational signatures modelling can be accomplished using statistical methods such as non-negative matrix factorization to identify potential novel mutational processes.
Identifying the contributions of diverse mutational signatures to carcinogenesis provides insight into tumor biology and can offer opportunities for targeted therapy.

#### Types of mutations: indels

Signature 3, seen in homologous recombination (HR) deficient tumour, is associated with increased burden of large indels (up to 50 nucleotides) with overlapping microhomology at the breakpoints. In such tumors, DNA double-strand breaks are repaired by the imprecise repair mechanisms of non-homologous end joining (NHEJ) or microhomology-mediated end joining (MMEJ) instead of high fidelity HR repair.
Signature 6, seen in tumors with microsatellite instability, also features enrichment of 1bp indels in nucleotide repeat regions.

#### Types of mutations: structural variants

Homologous recombination deficiency leads to Signature 3 substitution pattern, but also to increase burden of structural variants. In the absence of homologous recombination, non-homologous end joining leads to large structural variants such as chromosomal translocations, chromosomal inversions and copy number variants.

## Mutational signatures

A brief description of selected mutational processes and their associated mutational signatures in cancer will be included in the sections below. Some signatures are ubiquitous across diverse cancer types (e.g. Signature 1) while some others tend to associate with specific cancers (e.g. Signature 9 and lymphoid malignancies).
Some mutational signatures feature strong transcriptional-bias with substitutions preferentially affecting one of the DNA strands, either the transcribed or untranscribed strand (Signatures 5, 7, 8, 10, 12, 16).

### Age-related mutagenesis

Signature 1 features a predominance of C>T transition (genetics) in the Np[C>T]G trinucleotide contexts and correlates with the age of patient at time of cancer diagnosis. The underlying proposed biological mechanism is the spontaneous deamination of 5-methylcytosine.
Signature 5 has a predominance of T>C substitutions in the ApTpN trinucleotide context with transcriptional strand bias.

### Homologous recombination deficiency

Signature 3 displays high mutation counts of multiple mutation classes and is associated with germline and somatic (biology) BRCA1 and BRCA2 mutations in several cancer types (e.g. breast, pancreatic, ovarian, prostate). This signature results from DNA double-strand break repair deficiency (or homologous recombination deficiency). Signature 3 is associated with high burden of indels with microhomology at the breakpoints.

### APOBEC enzymes

APOBEC3 family of cytidine deaminase enzymes respond to viral infections by editing viral genome, but the enzymatic activity of APOBEC3A and APOBEC3B has also been found to cause unwanted host genome editing and may even participate to oncogenesis in human papillomavirus-related cancers.
Signature 2 and Signature 13 are enriched for C>T and C>G substitutions and are thought to arise from cytidine deaminase activity of the AID/APOBEC enzymes family.
A germline deletion polymorphism involving APOBEC3A and APOBEC3B is associated with high burden of Signature 2 and Signature 13 mutations. This polymorphism is considered to be of moderate penetrance (two-fold above background risk) for breast cancer risk. The exact roles and mechanisms underlying APOBEC-mediated genome editing are not yet fully delineated, but activation-induced cytidine deaminase(AID)/APOBEC complex is thought to be involved in host immune response to viral infections and lipid metabolism.
Both Signature 2 and Signature 13 feature cytosine to uracil substitutions due to cytidine deaminases. Signature 2 has a higher proportion of C[T>C]N substitutions and Signature 13 a higher proportion of T[C>G]N substitutions. APOBEC3A and APOBEC3B-mediated mutagenesis preferentially involve the lagging DNA strand during replication.

### Mismatch repair deficiency

Four COSMIC mutational signatures have been associated with DNA mismatch repair deficiency and found in tumors with microsatellite instability: Signature 6, 15, 20 and 26. Loss of function MLH1, MSH2, MSH6 or PMS2 genes cause defective DNA mismatch repair.

### DNA proofreading

Signature 10 has a transcriptional bias and is enriched for C>A substitutions in the TpCpT context as well as T>G substitutions in the TpTpTp context. Signature 10 is associated with altered function of DNA polymerase epsilon, which result in deficient DNA proofreading activity. Both germline and somatic POLE (gene) exonuclease domain mutations are associated with Signature 10.

### Base excision repair

Somatic enrichment for transversion mutations (G:C>T:A) has been associated with base excision repair (BER) deficiency and linked to defective MUTYH, a DNA glycosylase, in colorectal cancer. Direct DNA oxidation damage leads to the creation of 8-Oxoguanine, which if remains un-repaired, will lead to incorporation of adenine instead of cytosine during DNA replication. MUTYH encodes the mutY adenine glycosylase enzyme which excise the mismatched adenine from 8-Oxoguanine:adenine base pairing, therefore enabling DNA repair mechanisms involving OGG1 (Oxoguanine glycosylase) and NUDT1 (Nudix hydrolase 1, also known as MTH1, MutT homolog 1) to remove the damaged 8-Oxoguanine.

### Exposures to exogenous genotoxins

Selected exogenous genotoxins/carcinogens and their mutagen-induced DNA damage and repair mechanisms have been linked to specific molecular signatures.

#### Ultraviolet radiation (UV)

Signature 7 has a predominance of C>T substitutions at sites of adjacent pyrimidines (adjacent C or T), with a particularly diagnostic subset being the CC>TT dinucleotide mutation. This pattern arises because the major UV-induced DNA photoproducts join two adjacent pyrimidines; the photoproduct is typically the cyclobutane pyrimidine dimer (CPD). Specificity for C>T appears to be due to the million-fold acceleration of C deamination when it is part of a CPD, with the resulting uracil acting as T. CPDs are repaired via transcription-coupled nucleotide excision repair, causing a strong bias for C>T substitutions enriched on the untranscribed DNA strand. The regions of a tumor suppressor protein that are mutationally inactivated in sunlight-related skin cancers are the same as in cancers of organs not exposed to sunlight, but the nucleotide mutated is often shifted a few bases to a site where a CPD could form. Ultraviolet radiation exposure is therefore the proposed underlying mutagenic mechanism of this signature. UV also illustrates a subtlety in interpreting a tumor signature as a mutagen signature: only three-quarters of mutations induced by UV in the laboratory are UV signature mutations because UV also triggers cellular oxidative processes. Therefore even if all mutations in a tumor were caused by UV from sunlight, one quarter of the mutations are expected to not be UV signature mutations. A second carcinogen needn't be invoked to explain those mutations, but a second mutational process is required. Identification of a UV signature in a tumor of unknown primary site is clinically important as it suggests a diagnosis of metastatic skin cancer and has important treatment implications.

#### Alkylating agents

Signature 11 was identified in tumors previously exposed to Temozolamide, an alkylating agent. This signature is enriched for C>T substitutions on guanine bases due to transcription-coupled nucleotide excision repair. A strong transcriptional strand-bias is present in this signature.

#### Tobacco

Both Signature 4 (tobacco smoking, lung cancer) and Signature 29 (tobacco chewing, gingivo-buccal oral squamous cell carcinoma) display transcriptional strand-bias and enrichment for C>A substitutions, but their respective composition and patterns (proportion of each mutation types) differ slightly.
The proposed underlying mechanism of Signature 4 is the removal of DNA adducts (tobacco benzo(a)pyrene covalently bounded to guanine) by the transcription-coupled nucleotide excision repair (NER) machinery.

### Immunoglobulin gene hypermutation

Signature 9 has been identified in chronic lymphocytic leukemia and malignant B-cell lymphoma and feature enrichment for T>G transversion events. It is thought to result from error-prone polymerase η (POLH gene)-associated mutagenesis.
Recently, polymerase η error-prone synthesis signature has been linked to non-hematological cancers (e.g. skin cancer) and was hypothesized to contribute to YCG motif mutagenesis and could partly explain the increase TC dinucleotides substitutions.

## History

During the 1990s, Curtis Harris at the US National Cancer Institute and Bert Vogelstein at the Johns Hopkins Oncology Center in Baltimore reviewed data showing that different types of cancer had their own unique suite of mutations in p53, which were likely to have been caused by different agents, such as the chemicals in tobacco smoke or ultraviolet light from the sun. With the advent of next-generation sequencing, Michael Stratton saw the potential for the technology to revolutionize our understanding of the genetic changes inside individual tumors, setting the Wellcome Sanger Institute's huge banks of DNA-sequencing machines in motion to read every single letter of DNA in a tumor. By 2009, Stratton and his team had produced the first whole cancer genome sequences. These were detailed maps showing all the genetic changes and mutations that had occurred within two individual cancers—a melanoma from the skin and a lung tumor. The melanoma and lung cancer genomes were powerful proof that the fingerprints of specific culprits could be seen in cancers with one major cause. These tumors still contained many mutations that could not be explained by ultraviolet light or tobacco smoking. The detective work became a lot more complicated for cancers with complex, multiple or even completely unknown origins. By way of analogy, imagine a forensic scientist dusting for fingerprints at a murder scene. The forensic scientist might strike it lucky and find a set of perfect prints on a windowpane or door handle that match a known killer. However, they are much more likely to uncover a mish-mash of fingerprints belonging to a whole range of folk—from the victim and potential suspects to innocent parties and police investigators—all laid on top of each other on all sorts of surfaces. This is very similar to cancer genomes where multiple mutational patterns are commonly overlaid one over another making the data incomprehensible. Fortunately, a PhD student of Stratton's, Ludmil Alexandrov came up with a way of mathematically solving the problem. Alexandrov demonstrated that mutational patterns from individual mutagens found in a tumor can be distinguished from one another using a mathematical approach called blind source separation. The newly disentangled patterns of mutations were termed mutational signatures. In 2013, Alexandrov and Stratton published the first computational framework for deciphering mutational signatures from cancer genomics data. Subsequently, they applied this framework to more than seven thousand cancer genomes creating the first comprehensive map of mutational signatures in human cancer. Currently, more than one hundred mutational signatures have been identified across the repertoire of human cancer. In April 2022 58 new mutational signatures were described. With the emergence of novel DNA-damage-mapping methods, it becomes possible to study the etiology of mutational signatures by comparing them to respective trinucleotide-context-resolved patterns of DNA damage induced by chemical exposures or occurring naturally.

## Note list
