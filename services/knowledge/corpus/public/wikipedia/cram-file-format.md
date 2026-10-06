---
title: CRAM (file format)
requested_title: CRAM (file format)
revision_id: 1349292472
revision_timestamp: '2026-04-16T17:24:05Z'
url: https://en.wikipedia.org/w/index.php?oldid=1349292472
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

Compressed Reference-oriented Alignment Map (CRAM) is a compressed columnar file format for storing biological sequences aligned to a reference sequence, initially devised by Markus Hsi-Yang Fritz et al.
CRAM was designed to be an efficient reference-based alternative to the Sequence Alignment Map (SAM) and Binary Alignment Map (BAM) file formats.  It optionally uses a genomic reference to describe differences between the aligned sequence fragments and the reference sequence, reducing storage costs.  Additionally each column in the SAM format is separated into its own blocks, improving compression ratio.  CRAM files typically vary from 30 to 60% smaller than BAM, depending on the data held within them.
Implementations of CRAM exist in htsjdk, htslib, JBrowse, and Scramble.
The file format specification is maintained by the Global Alliance for Genomics and Health (GA4GH) with the specification document available from the EBI cram toolkit page.

## File format

The basic structure of a CRAM file is a series of containers, the first of which holds a compressed copy of the SAM header.  Subsequent containers consist of a container Compression Header followed by a series of slices which in turn hold the alignment records themselves, formatted as a series of blocks.
CRAM file:

Container:

Slice:

CRAM constructs records from a set of data series, describing the components of an alignment.  The container Compression Header specifies which data series is encoded in which block, what codec will be used, and any codec specific meta-data (for example a table of Huffman symbol code lengths).  While data series can be mixed together within the same block, keeping them separate usually improves compression and provides the opportunity for efficient selective decoding where only some data types are required.
Selective access to a CRAM file is granted via the index (with file-name suffix ".crai").  On chromosome and position sorted data this indicates which region is covered by each slice.  On unsorted data the index may be used to simply fetch the Nth container.  Selective decoding may also be achieved using the Compression Header to skip specified data series if partial records are required.

## History

CRAM version 4.0 exists as a prototype in Scramble, initially demonstrated in 2015, but has yet to be adopted as a standard.
