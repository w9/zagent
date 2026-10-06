---
title: FASTA format
requested_title: FASTA format
revision_id: 1361618063
revision_timestamp: '2026-06-29T02:15:52Z'
url: https://en.wikipedia.org/w/index.php?oldid=1361618063
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

In bioinformatics and biochemistry, the FASTA format is a text-based format for representing either nucleotide sequences or amino acid (protein) sequences, in which nucleotides or amino acids are represented using single-letter codes.
The format allows for sequence names and comments to precede the sequences. It originated from the FASTA software package and has since become a near-universal standard in bioinformatics.
The simplicity of FASTA format makes it easy to manipulate and parse sequences using text-processing tools and scripting languages.

## Overview

A sequence begins with a greater-than character (">") followed by a description of the sequence (all in a single line). The lines immediately following the description line are the sequence representation, with one letter per amino acid or nucleic acid, and are typically no more than 80 characters in length.
For example:

### Original format

The original FASTA/Pearson format is described in the documentation for the FASTA suite of programs. It can be downloaded with any free distribution of FASTA (see fasta20.doc, fastaVN.doc, or fastaVN.me—where VN is the Version Number).
In the original format, a sequence was represented as a series of lines, each of which was no longer than 120 characters and usually did not exceed 80 characters. This probably was to allow for the preallocation of fixed line sizes in software: at the time most users relied on Digital Equipment Corporation (DEC) VT220 (or compatible) terminals which could display 80 or 132 characters per line. Most people preferred the bigger font in 80-character modes and so it became the recommended fashion to use 80 characters or less (often 70) in FASTA lines. Also, the width of a standard printed page is 70 to 80 characters (depending on the font). Hence, 80 characters became the norm.
The first line in a FASTA file started either with a ">" (greater-than) symbol or, less frequently, a ";" (semicolon) was taken as a comment. Subsequent lines starting with a semicolon would be ignored by software. Since the only comment used was the first, it quickly became used to hold a summary description of the sequence, often starting with a unique library accession number, and with time it has become commonplace to always use ">" for the first line and to not use ";" comments (which would otherwise be ignored).
Following the initial line (used for a unique description of the sequence) was the actual sequence itself in the standard one-letter character string. Anything other than a valid character would be ignored (including spaces, tabulators, asterisks, etc...). It was also common to end the sequence with an "*" (asterisk) character (in analogy with use in PIR formatted sequences) and, for the same reason, to leave a blank line between the description and the sequence. Below are a few sample sequences:

A multiple-sequence FASTA format, or multi-FASTA format, would be obtained by concatenating several single-sequence FASTA files in one file. This does not imply a contradiction with the format as only the first line in a FASTA file may start with a ";" or ">", forcing all subsequent sequences to start with a ">" in order to be taken as separate sequences (and further forcing the exclusive reservation of ">" for the sequence definition line). Thus, the examples above would be a multi-FASTA file if taken together.
Modern bioinformatics programs that rely on the FASTA format expect the sequence headers to be preceded by ">". The sequence is generally represented as "interleaved", or on multiple lines as in the above example, but may also be "sequential", or on a single line. Running different bioinformatics programs may require conversions between "sequential" and "interleaved" FASTA formats.

## Description line

The description line (defline) or header/identifier line, which begins with ">", gives a name and/or a unique identifier for the sequence, and may also contain additional information. In a deprecated practice, the header line sometimes contained more than one header, separated by a ^A (Control-A) character. In the original Pearson FASTA format, one or more comments, distinguished by a semi-colon at the beginning of the line, may occur after the header. Some databases and bioinformatics applications do not recognize these comments and follow the NCBI FASTA specification. An example of a multiple sequence FASTA file follows:

### NCBI identifiers

The NCBI defined a standard for the unique identifier used for the sequence (SeqID) in the header line.  This allows a sequence that was obtained from a database to be labelled with a reference to its database record.  The database identifier format is understood by the NCBI tools like makeblastdb and table2asn. The following list describes the NCBI FASTA defined format for sequence identifiers.

The vertical bars ("|") in the above list are not separators in the sense of the Backus–Naur form but are part of the format. Multiple identifiers can be concatenated, also separated by vertical bars.

## Sequence representation

Following the header line, the actual sequence is represented. Sequences may be protein sequences or nucleic acid sequences, and they can contain gaps or alignment characters (see sequence alignment). Sequences are expected to be represented in the standard IUB/IUPAC amino acid and nucleic acid codes, with these exceptions: lower-case letters are accepted and are mapped into upper-case; a single hyphen or dash can be used to represent a gap character; and in amino acid sequences, U and * are acceptable letters (see below). Numerical digits are not allowed but are used in some databases to indicate the position in the sequence. The nucleic acid codes supported are:

The amino acid codes supported (22 amino acids and 3 special codes) are:

## FASTA file

### Filename extension

There is no standard filename extension for a text file containing FASTA formatted sequences. The table below shows each extension and its respective meaning.

## Extensions

FASTQ format is a form of FASTA format extended to indicate information related to sequencing. It is created by the Sanger Centre in Cambridge.
A2M/A3M are a family of FASTA-derived formats used for sequence alignments. In A2M/A3M sequences, lowercase characters are taken to mean insertions, which are then indicated in the other sequences as the dot (".") character. The dots can be discarded for compactness without loss of information. As with typical FASTA files used in alignments, the gap ("-") is taken to mean exactly one position. A3M is similar to A2M, with the added rule that gaps aligned to insertions can too be discarded.

## Working with FASTA files

A plethora of user-friendly scripts are available from the community to perform FASTA file manipulations. Online toolboxes, such as FaBox or the FASTX-Toolkit within Galaxy servers, are also available. These can be used to segregate sequence headers/identifiers, rename them, shorten them, or extract sequences of interest from large FASTA files based on a list of wanted identifiers (among other available functions). A tree-based approach to sorting multi-FASTA files (TREE2FASTA) also exists based on the coloring and/or annotation of sequences of interest in the FigTree viewer. Additionally, the Bioconductor Biostrings package can be used to read and manipulate FASTA files in R.
Several online format converters exist to rapidly reformat multi-FASTA files to different formats (e.g. NEXUS, PHYLIP) for use with different phylogenetic programs, such as the converter available on phylogeny.fr.
