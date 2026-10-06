---
title: Variant Call Format
requested_title: Variant Call Format
revision_id: 1373132868
revision_timestamp: '2026-09-04T05:46:37Z'
url: https://en.wikipedia.org/w/index.php?oldid=1373132868
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

The Variant Call Format or VCF is a standard text file format used in bioinformatics for storing gene sequence or DNA sequence  variations. The format was developed in 2010 for the 1000 Genomes Project and has since been used by other large-scale genotyping and DNA sequencing projects. VCF is a common output format for variant calling programs due to its relative simplicity and scalability. Many tools have been developed for editing and manipulating VCF files, including VCFtools, which was released in conjunction with the VCF format in 2011, and BCFtools, which was included as part of SAMtools until being split into an independent package in 2014.
The standard is currently in version 4.5, although the 1000 Genomes Project has developed its own specification for structural variations such as duplications, which are not easily accommodated into the existing schema.
Additional file formats have been developed based on VCF, including genomic VCF (gVCF). gVCF is an extended format which includes additional information about "blocks" that match the reference and their qualities.

## Example

## The VCF header

The header begins the file and provides metadata describing the body of the file. Header lines are denoted as starting with #. Special keywords in the header are denoted with ##. Recommended keywords include fileformat, fileDate and reference.
The header contains keywords that optionally semantically and syntactically describe the fields used in the body of the file, notably INFO, FILTER, and FORMAT (see below).
In practice, VCF headers often contain substantial metadata added by upstream software, such as reference genome information, contig definitions, filter descriptions, sample declarations, provenance fields, and custom INFO or FORMAT tags. This metadata is important for validation and interpretation.

## The columns of a VCF

The body of VCF follows the header, and is tab separated into 8 mandatory columns and an unlimited number of optional columns that may be used to record other information about the sample(s). When additional columns are used, the first optional column is used to describe the format of the data in the columns that follow.

## Common INFO fields

Arbitrary keys are permitted, although the following sub-fields are reserved (albeit optional):

Any other info fields are defined in the .vcf header.

## Common FORMAT fields

Any other format fields are defined in the .vcf header.

## Binary VCF

Binary VCF or BCF files are binary, BGZF compressed variations of VCF files. BCF files allow fast and efficient indexed queries through tools like Tabix once an index file has been created.
