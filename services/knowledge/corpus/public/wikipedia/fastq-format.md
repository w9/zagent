---
title: FASTQ format
requested_title: FASTQ format
revision_id: 1368840807
revision_timestamp: '2026-08-11T11:02:03Z'
url: https://en.wikipedia.org/w/index.php?oldid=1368840807
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

FASTQ format is a text-based format for storing both a biological sequence (usually nucleotide sequence) and its corresponding quality scores. Both the sequence letter and quality score are each encoded with a single ASCII character for brevity.
It was originally developed at the Wellcome Trust Sanger Institute to bundle a FASTA formatted sequence and its quality data, but has become the de facto standard for storing the output of high-throughput sequencing instruments such as the Illumina Genome Analyzer.

## Format

A FASTQ file has four line-separated fields per sequence:

Field 1 begins with a '@' character and is followed by a sequence identifier and an optional description (like a FASTA title line).
Field 2 is the raw sequence letters.
Field 3 begins with a '+' character and is optionally followed by the same sequence identifier (and any description) again.
Field 4 encodes the quality values for the sequence in Field 2, and must contain the same number of symbols as letters in the sequence.
A FASTQ file containing a single sequence might look like this:

@SEQ_ID
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65

The byte representing quality runs from 0x21 (lowest quality; '!' in ASCII) to 0x7e (highest quality; '~' in ASCII).
Here are the quality value characters in left-to-right increasing order of quality (ASCII):

!"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~

The original Sanger FASTQ files split long sequences and quality strings over multiple lines, as is typically done for FASTA files. Accounting for this makes parsing more complicated due to the choice of "@" and "+" as markers (as these characters can also occur in the quality string). Multi-line FASTQ files (and consequently multi-line FASTQ parsers) are less common now that the majority of sequencing carried out is short-read Illumina sequencing, with typical sequence lengths of around 100bp.

### Illumina sequence identifiers

Sequences from the Illumina software use a systematic identifier:

Versions of the Illumina pipeline since 1.4 appear to use #NNNNNN instead of #0 for the multiplex ID, where NNNNNN is the sequence of the multiplex tag.
With Casava 1.8 the format of the '@' line has changed:

Note that more recent versions of Illumina software output a sample number (defined by the order of the samples in the sample sheet) in place of an index sequence when an index sequence is not explicitly specified for a sample in the sample sheet. For example, the following header might appear in a FASTQ file belonging to the first sample of a batch of samples:

### NCBI Sequence Read Archive

FASTQ files from the INSDC Sequence Read Archive often include a description, e.g.

In this example there is an NCBI-assigned identifier, and the description holds the original identifier from Solexa/Illumina (as described above) plus the read length. Sequencing was performed in paired-end mode (~500bp insert size), see SRR001666. The default output format of fastq-dump produces entire spots, containing any technical reads and typically single or paired-end biological reads.

Modern usage of FASTQ almost always involves splitting the spot into its biological reads, as described in submitter-provided metadata:

When present in the archive, fastq-dump can attempt to restore read names to original format. NCBI does not store original read names by default:

In the example above, the original read names were used rather than the accessioned read name. NCBI accessions runs and the reads they contain. Original read names, assigned by sequencers, are able to function as locally unique identifiers of a read, and convey exactly as much information as a serial number. The ids above were algorithmically assigned based upon run information and geometric coordinates. Early SRA loaders parsed these ids and stored their decomposed components internally. NCBI stopped recording read names because they are frequently modified from the vendors' original format in order to associate some additional information meaningful to a particular processing pipeline, and this caused name format violations that resulted in a high number of rejected submissions. Without a clear schema for read names, their function remains that of a unique read id, conveying the same amount of information as a read serial number. See various SRA Toolkit issues for details and discussions.
Also note that fastq-dump converts this FASTQ data from the original Solexa/Illumina encoding to the Sanger standard (see encodings below). This is because the SRA serves as a repository for NGS information, rather than format. The various *-dump tools are capable of producing data in several formats from the same source. The requirements for doing so have been dictated by users over several years, with the majority of early demand coming from the 1000 Genomes Project.

## Variations

### Quality

A quality value Q is an integer mapping of p (i.e., the probability that the corresponding base call is incorrect). Two different equations have been in use.  The first is the standard Sanger variant to assess reliability of a base call, otherwise known as Phred quality score:

Q

sanger

=
−
10

log

10

⁡
p

The Solexa pipeline (i.e., the software delivered with the Illumina Genome Analyzer) earlier used a different mapping, encoding the odds p/(1-p) instead of the probability p:

Q

solexa-prior to v.1.3

=
−
10

log

10

⁡

p

1
−
p

Although both mappings are asymptotically identical at higher quality values, they differ at lower quality levels (i.e., approximately p > 0.05, or equivalently, Q < 13).

At times there has been disagreement about which mapping Illumina actually uses. The user guide (Appendix B, page 122) for version 1.4 of the Illumina pipeline states that: "The scores are defined as ⁠

Q
=
10
⋅

log

10

⁡

p

1
−
p

⁠  [sic], where p is the probability of a base call corresponding to the base in question". In retrospect, this entry in the manual appears to have been an error. The user guide (What's New, page 5) for version 1.5 of the Illumina pipeline lists this description instead: "Important Changes in Pipeline v1.3  [sic]. The quality scoring scheme has changed to the Phred [i.e., Sanger] scoring scheme, encoded as an ASCII character by adding 64 to the Phred value. A Phred score of a base is:

Q

phred

=
−
10

log

10

⁡
e

, where e is the estimated probability of a base being wrong.

### Encoding

Sanger format can encode a Phred quality score from 0 to 93 using ASCII 33 to 126 (although in raw read data the Phred quality score rarely exceeds 60, higher scores are possible in assemblies or read maps). Also used in SAM format. Coming to the end of February 2011, Illumina's newest version (1.8) of their pipeline CASAVA  will directly produce fastq in Sanger format, according to the announcement on seqanswers.com forum.
Element Biosciences AVITI reads are encoded following the Sanger convention: Phred quality scores from 0 to 93 are encoded using ASCII 33 to 126. Raw reads typically exhibit base quality scores in the range of [0, 55].
PacBio HiFi reads, which are typically stored in SAM/BAM format, use the Sanger convention: Phred quality scores from 0 to 93 are encoded using ASCII 33 to 126.  Raw PacBio subreads use the same convention but typically assign a placeholder base quality (Q0) to all bases in the read.
Oxford Nanopore Duplex reads, called using the dorado basecaller are typically stored in SAM/BAM format. After changing to a 16-bit internal quality representation, the reported base quality limit is q50 (S).
Solexa/Illumina 1.0 format can encode a Solexa/Illumina quality score from -5 to 62 using ASCII 59 to 126 (although in raw read data Solexa scores from -5 to 40 only are expected)
Starting with Illumina 1.3 and before Illumina 1.8, the format encoded a Phred quality score from 0 to 62 using ASCII 64 to 126 (although in raw read data Phred scores from 0 to 40 only are expected).
Starting in Illumina 1.5 and before Illumina 1.8, the Phred scores 0 to 2 have a slightly different meaning. The values 0 and 1 are no longer used and the value 2, encoded by ASCII 66 "B", is used also at the end of reads as a Read Segment Quality Control Indicator. The Illumina manual (page 30) states the following: If a read ends with a segment of mostly low quality (Q15 or below), then all of the quality values in the segment are replaced with a value of 2 (encoded as the letter B in Illumina's text-based encoding of quality scores)... This Q2 indicator does not predict a specific error rate, but rather indicates that a specific final portion of the read should not be used in further analyses. Also, the quality score encoded as "B" letter may occur internally within reads at least as late as pipeline version 1.6, as shown in the following example:
@HWI-EAS209_0006_FC706VJ:5:58:5894:21141#ATCACG/1
TTAATTGGTAAATAAATCTCCTAATAGCTTAGATNTTACCTTNNNNNNNNNNTAGTTTCTTGAGATTTGTTGGGGGAGACATTTTTGTGATTGCCTTGAT
+HWI-EAS209_0006_FC706VJ:5:58:5894:21141#ATCACG/1
efcfffffcfeefffcffffffddf`feed]`]_Ba_^__[YBBBBBBBBBBRTT\]][]dddd`ddd^dddadd^BBBBBBBBBBBBBBBBBBBBBBBB

An alternative interpretation of this ASCII encoding has been proposed. Also, in Illumina runs using PhiX controls, the character 'B' was observed to represent an "unknown quality score". The error rate of 'B' reads was roughly 3 phred scores lower the mean observed score of a given run.

Starting in Illumina 1.8, the quality scores have basically returned to the use of the Sanger format (Phred+33).
For raw reads, the range of scores will depend on the technology and the base caller used, but will typically be up to 41 for recent Illumina chemistry. Since the maximum observed quality score was previously only 40, various scripts and tools break when they encounter data with quality values larger than 40. For processed reads, scores may be even higher. For example, quality values of 45 are observed in reads from Illumina's Long Read Sequencing Service (previously Moleculo).

SSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSS.....................................................
..........................XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX......................
...............................IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII......................
.................................JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ.....................
LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL....................................................
NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN...........................................
EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP
!"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~
|                         |    |        |              |               |                     |
33                        59   64       73             88             104                   126
0........................26...31.......40
-5....0........9.............................40
0........9.............................40
3.....9..............................41
0.2......................26...31........41
0..................20........30........40........50
0..................20........30........40........50...55
0..................20........30........40........50..........................................93

S - Sanger        Phred+33,  raw reads typically (0, 40)
X - Solexa        Solexa+64, raw reads typically (-5, 40)
I - Illumina 1.3+ Phred+64,  raw reads typically (0, 40)
J - Illumina 1.5+ Phred+64,  raw reads typically (3, 41)
with 0=unused, 1=unused, 2=Read Segment Quality Control Indicator (bold)
(Note: See discussion above).
L - Illumina 1.8+ Phred+33,  raw reads typically (0, 41)
N - Nanopore      Phred+33,  Duplex reads typically (0, 50)
E - ElemBio AVITI Phred+33,  raw reads typically (0, 55)
P - PacBio        Phred+33,  HiFi reads typically (0, 93)

### Color space

For SOLiD data, the format is modified to a color space FASTQ sequence (CSFASTQ), where bases in the sequence are combined with the numbers 0, 1, 2, and 3, indicating how bases are modified relative to the previous base in the sequence (0: no change; 1: transition; 2: non-complementary transversion; 3: complementary transversion). This format matched the different sequencing chemistry used by SOLiD sequencers. Initial representations only used nucleotide bases at the start of the sequence, but later versions included bases embedded at periodic intervals to improve basecalling and mapping accuracy.
The quality values for CSFASTQ are identical to those of the Sanger format. Alignment tools differ in their preferred version of the quality values: some include a quality score (set to 0, i.e. '!') for the leading nucleotide, others do not. The sequence read archive includes this quality score.

### FAST5 and HDF5 evolutions

The FAST4 format was invented as a derivative of the FASTQ format where each of the 4 bases (A,C,G,T) had separate probabilities stored. It was part of the Swift basecaller, an open source package for primary data analysis on next-gen sequence data "from images to basecalls".
The FAST5 format was invented as an extension of the FAST4 format. The FAST5 files are Hierarchical Data Format 5 (HDF5) files with a specific schema defined by Oxford Nanopore Technologies (ONT).

### Simulation

FASTQ read simulation has been approached by several tools.
A comparison of those tools can be seen here.

### Compression

#### General compressors

General-purpose tools such as Gzip and bzip2 regard FASTQ as a plain text file and result in suboptimal compression ratios. NCBI's Sequence Read Archive encodes metadata using the LZ-77 scheme.
General FASTQ compressors typically compress distinct fields (read names, sequences, comments, and quality scores) in a FASTQ file separately; these include DSRC and DSRC2, FQC, LFQC, Fqzcomp, and Slimfastq.

#### Reads

Having a reference genome around is convenient because then instead of storing the nucleotide sequences themselves, one can just align the reads to the reference genome and store the positions (pointers) and mismatches; the pointers can then be sorted according to their order in the reference sequence and encoded, e.g., with run-length encoding. When the coverage or the repeat content of the sequenced genome is high, this leads to a high compression ratio.
Unlike the SAM/BAM formats, FASTQ files do not specify a reference genome. Alignment-based FASTQ compressors supports the use of either user-provided or de novo assembled reference: LW-FQZip uses a provided reference genome and Quip, Leon, k-Path and KIC perform de novo assembly using a de Bruijn graph-based approach.
Explicit read mapping and de novo assembly are typically slow. Reordering-based FASTQ compressors first cluster reads that share long substrings and then independently compress reads in each cluster after reordering them or assembling them into longer contigs, achieving perhaps the best trade-off between the running time and compression rate. SCALCE is the first such tool, followed by Orcom and Mince. BEETL uses a generalized Burrows–Wheeler transform for reordering reads, and HARC achieves better performance with hash-based reordering. AssemblTrie instead assembles reads into reference trees with as few total number of symbols as possible in the reference.
Benchmarks for these tools are available.

#### Quality values

Quality values account for about half of the required disk space in the FASTQ format (before compression), and therefore the compression of the quality values can significantly reduce storage requirements and speed up analysis and transmission of sequencing data. Both lossless and lossy compression are recently being considered in the literature. For example, the algorithm QualComp performs lossy compression with a rate (number of bits per quality value) specified by the user. Based on rate-distortion theory results, it allocates the number of bits so as to minimize the MSE (mean squared error) between the original (uncompressed) and  the reconstructed (after compression) quality values. Other algorithms for compression of quality values include SCALCE and Fastqz. Both are lossless compression algorithms that provide an optional controlled lossy transformation approach. For example, SCALCE reduces the alphabet size based on the observation that “neighboring” quality values are similar in general. For a benchmark, see.
As of the HiSeq 2500 Illumina gives the option to output qualities that have been coarse grained into quality bins. The binned scores are computed directly from the empirical quality score table, which is itself tied to the hardware, software and chemistry that were used during the sequencing experiment.

## File extension

There is no standard file extension for a FASTQ file, but .fq and .fastq are commonly used.

## Format converters

Biopython version 1.51 onwards (interconverts Sanger, Solexa and Illumina 1.3+)
EMBOSS version 6.1.0 patch 1 onwards (interconverts Sanger, Solexa and Illumina 1.3+)
BioPerl version 1.6.1 onwards (interconverts Sanger, Solexa and Illumina 1.3+)
BioRuby version 1.4.0 onwards (interconverts Sanger, Solexa and Illumina 1.3+)
BioJava version 1.7.1 onwards (interconverts Sanger, Solexa and Illumina 1.3+)
