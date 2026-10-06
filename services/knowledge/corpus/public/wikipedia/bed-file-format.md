---
title: BED (file format)
requested_title: BED (file format)
revision_id: 1244776555
revision_timestamp: '2024-09-09T03:34:46Z'
url: https://en.wikipedia.org/w/index.php?oldid=1244776555
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

The BED (Browser Extensible Data) format is a text file format used to store genomic regions as coordinates and associated annotations. The data are presented in the form of columns separated by spaces or tabs. This format was developed during the Human Genome Project and then adopted by other sequencing projects. As a result of this increasingly wide use, this format had already become a de facto standard in bioinformatics before a formal specification was written.
One of the advantages of this format is the manipulation of coordinates instead of nucleotide sequences, which optimizes the power and computation time when comparing all or part of genomes. In addition, its simplicity makes it easy to manipulate and read (or parsing) coordinates or annotations using word processing and scripting languages such as Python, Ruby, or Perl or more specialized tools such as BEDTools.

## History

The end of the 20th century saw the emergence of the first projects to sequence complete genomes. Among these projects, the Human Genome Project was the most ambitious at the time, aiming to sequence for the first time a genome of several gigabases. This required the sequencing centres to carry out major methodological development in order to automate the processing of sequences and their analyses. Thus, many formats were created, such as FASTQ, GFF, and BED. However, no official specifications were published at the time, which affected some formats such as FASTQ when sequencing projects multiplied at the beginning of the 21st century.
Its wide use within genome browsers has made it possible to define this format in a relatively stable way as this description is used by many tools.

## Format

Initially the BED format did not have any official specification. Instead, the description provided by the UCSC Genome Browser has been widely used as a reference.
A formal BED specification was published in 2021 under the auspices of the Global Alliance for Genomics and Health.

### Description

A BED file consists of a minimum of three columns to which nine optional columns can be added for a total of twelve columns. The first three columns contain the names of chromosomes or scaffolds, the start, and the end coordinates of the sequences considered. The next nine columns contain annotations related to these sequences. These columns must be separated by spaces or tabs, the latter being recommended for reasons of compatibility between programs. Each row of a file must have the same number of columns. The order of the columns must be respected: if columns of high numbers are used, the columns of intermediate numbers must be filled in.

### Header

A BED file can optionally contain a header. However, there is no official description of the format of the header. It may contain one or more lines and be signified by different words or symbols, depending on its functional role or simply descriptive. Thus, a header line can begin with these words or symbol:

"browser": functional header used by the UCSC Genome Browser to set options related to it,
"track": functional header used by genome browsers to specify display options related to it,
"#": descriptive header to add comments such as the name of each column.

### Coordinate system

Unlike the coordinate system used by other standards such as GFF, the system used by the BED format is zero-based for the coordinate start and one-based for the coordinate end. Thus, the nucleotide with the coordinate 1 in a genome will have a value of 0 in column 2 and a value of 1 in column 3.
A thousand-base BED interval with the following start and end:

chr7    0    1000

would convert to the following 1-based "human" genome coordinates, as used by a genome browser such as UCSC:

chr7    1    1000

This choice is justified by the method of calculating the lengths of the genomic regions considered, this calculation being based on the simple subtraction of the end coordinates (column 3) by those of the start (column 2):

x

e
n
d

−

x

s
t
a
r
t

. When the coordinate system is based on the use of 1 to designate the first position, the calculation becomes slightly more complex:

x

e
n
d

−

x

s
t
a
r
t

+
1

. This slight difference can have a relatively large impact in terms of computation time when data sets with several thousand to hundreds of thousands of lines are used.
Alternatively, we can view both coordinates as zero-based, where the end position is non-inclusive. In other words, the zero-based end position denotes the index of the first position after the feature. For the example above, the zero-based end position of 1000 marks the first position after the feature including positions 0 through 999.

### Examples

Here is a minimal example:

chr7    127471196    127472363
chr7    127472363    127473530
chr7    127473530    127474697

Here is a typical example with nine columns from the UCSC Genome Browser. The first three lines are settings for the UCSC Genome Browser and are unrelated to the data specified in BED format:

browser position chr7:127471196-127495720
browser hide all
track name="ItemRGBDemo" description="Item RGB demonstration" visibility=2 itemRgb="On"
chr7    127471196    127472363    Pos1    0    +    127471196    127472363    255,0,0
chr7    127472363    127473530    Pos2    0    +    127472363    127473530    255,0,0
chr7    127473530    127474697    Pos3    0    +    127473530    127474697    255,0,0
chr7    127474697    127475864    Pos4    0    +    127474697    127475864    255,0,0
chr7    127475864    127477031    Neg1    0    -    127475864    127477031    0,0,255
chr7    127477031    127478198    Neg2    0    -    127477031    127478198    0,0,255
chr7    127478198    127479365    Neg3    0    -    127478198    127479365    0,0,255
chr7    127479365    127480532    Pos5    0    +    127479365    127480532    255,0,0
chr7    127480532    127481699    Neg4    0    -    127480532    127481699    0,0,255

## File extension

There is currently no standard file extension for BED files, but the ".bed" extension is the most frequently used. The number of columns sometimes is noted in the file extension, for example: ".bed3", ".bed4", ".bed6", ".bed12".

## Usage

The use of BED files has spread rapidly with the emergence of new sequencing techniques and the manipulation of larger and larger sequence files. The comparison of genomic sequences or even entire genomes by comparing the sequences themselves can quickly require significant computational resources and become time-consuming. Handling BED files makes this work more efficient by using coordinates to extract sequences of interest from sequencing sets or to directly compare and manipulate two sets of coordinates.
To perform these tasks, various programs can be used to manipulate BED files, including but not limited to the following:

Genome browsers: from BED files allows the visualization and extraction of sequences of mammalian genomes currently sequenced (e.g. the function Manage Custom Tracks in UCSC Genome Browser).
Galaxy: web-based platform.
Command-line tools:
BEDTools: program allowing the manipulation of coordinate sets and the extraction of sequences from a BED file.
BEDOPS: a suite of tools for fast boolean operations on BED files.
BedTk: a faster alternative to BEDTools for a limited and specialized sub-set of operations.
covtobed: a tool to convert a BAM file into a BED coverage track.

## .genome Files

BEDtools also uses .genome files to determine chromosomal boundaries and ensure that padding operations do not extend past chromosome boundaries. Genome files are formatted as shown below, a two-column tab-separated file with one-line header.

chrom   size
chr1    248956422
chr2    242193529
chr3    198295559
chr4    190214555
chr5    181538259
chr6    170805979
chr7    159345973
...
