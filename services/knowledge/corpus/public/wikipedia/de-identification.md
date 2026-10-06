---
title: De-identification
requested_title: De-identification
revision_id: 1369637766
revision_timestamp: '2026-08-16T05:22:16Z'
url: https://en.wikipedia.org/w/index.php?oldid=1369637766
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

De-identification is the process used to prevent someone's personal identity from being revealed.  For example, data produced during human subject research might be de-identified to preserve the privacy of research participants. Biological data may be de-identified in order to comply with HIPAA regulations that define and stipulate patient privacy laws.
When applied to metadata or general data about identification, the process is also known as data anonymization. Common strategies include deleting or masking personal identifiers, such as personal name, and suppressing or generalizing quasi-identifiers, such as date of birth. The reverse process of using de-identified data to identify individuals is known as data re-identification. Successful re-identifications cast doubt on de-identification's effectiveness. A systematic review of fourteen distinct re-identification attacks found "a high re-identification rate […] dominated by small-scale studies on data that was not de-identified according to existing standards".
De-identification is adopted as one of the main approaches toward data privacy protection. It is commonly used in fields of communications, multimedia, biometrics, big data, cloud computing, data mining, internet, social networks, and audio–video surveillance.

## Examples

### In designing surveys

When surveys are conducted, such as a census, they collect information about a specific group of people. To encourage participation and to protect the privacy of survey respondents, the researchers attempt to design the survey in a way that when people participate in a survey, it will not be possible to match any participant's individual response(s) with any data published.

### Before using information

When an online shopping website wants to know its users' preferences and shopping habits, it decides to retrieve customers' data from its database and do analysis on them. The personal data information include personal identifiers which were collected directly when customers created their accounts. The website needs to pre-handle the data through de-identification techniques before analyzing data records to avoid violating their customers' privacy.

## Anonymization

Anonymization refers to irreversibly severing a data set from the identity of the data contributor in a study to prevent any future re-identification, even by the study organizers under any condition. De-identification may also include preserving identifying information which can only be re-linked by a trusted party in certain situations. There is a debate in the technology community on whether data that can be re-linked, even by a trusted party, should ever be considered de-identified.

## Techniques

Common strategies of de-identification are masking personal identifiers and generalizing quasi-identifiers. Pseudonymization is the main technique used to mask personal identifiers from data records, and k-anonymization is usually adopted for generalizing quasi-identifiers.

### Pseudonymization

Pseudonymization is performed by replacing real names with a temporary ID. It deletes or masks personal identifiers to make individuals unidentified. This method makes it possible to track the individual's record over time, even though the record will be updated. However, it can not prevent the individual from being identified if some specific combinations of attributes in the data record indirectly identify the individual.

### k-anonymization

k-anonymization defines attributes that indirectly points to the individual's identity as quasi-identifiers (QIs) and deal with data by making at least k individuals have some combination of QI values. QI values are handled following specific standards. For example, the k-anonymization replaces some original data in the records with new range values and keep some values unchanged. New combination of QI values prevents the individual from being identified and also avoid destroying data records.

## Applications

Research into de-identification is driven mostly for protecting health information. Some libraries have adopted methods used in the healthcare industry to preserve their readers' privacy.
In big data, de-identification is widely adopted by individuals and organizations. With the development of social media, e-commerce, and big data, de-identification is sometimes required and often used for data privacy when users' personal data are collected by companies or third-party organizations who will analyze it for their own personal usage.
In smart cities, de-identification may be required to protect the privacy of residents, workers and visitors. Without strict regulation, de-identification may be difficult because sensors can still collect information without consent.

### Data De-identification

PHI (Protected Health Information) can be present in various data and each format need specific techniques and tools for de-identify it:

For Text de-identification is using rule based and NLP (Natural language processing) approaches.
Pdf de-identification is based on text de-identification, also required in most cases OCR and specific techniques for hide PHI in PDF.
DICOM de-identification required to clean metadata, pixel data, encapsulated documents.

## Limits

Whenever a person participates in genetics research, the donation of a biological specimen often results in the creation of a large amount of personalized data. Such data is uniquely difficult to de-identify.
Anonymization of genetic data is particularly difficult because of the huge amount of genotypic
information in biospecimens, the ties that specimens often have to medical history, and the advent of modern bioinformatics tools for data mining. There have been demonstrations that data for individuals in aggregate collections of genotypic data sets can be tied to the identities of the specimen donors.
Some researchers have suggested that it is not reasonable to ever promise participants in genetics research that they can retain their anonymity, but instead, such participants should be taught the limits of using coded identifiers in a de-identification process.

## De-identification laws in the United States of America

In May 2014, the United States President's Council of Advisors on Science and Technology found de-identification "somewhat useful as an added safeguard" but not "a useful basis for policy" as "it is not robust against near‐term future re‐identification methods".
The HIPAA Privacy Rule provides mechanisms for using and disclosing health data responsibly without the need for patient consent. These mechanisms center on two HIPAA de-identification standards – Safe Harbor and the Expert Determination Method. Safe harbor relies on the removal of specific patient identifiers (e.g. name, phone number, email address, etc.), while the Expert Determination Method requires knowledge and experience with generally accepted statistical and scientific principles and methods to render information not individually identifiable.

### Safe harbor

The safe harbor method uses a list approach to de-identification and has two requirements:

The removal or generalization of 18 elements from the data.
That the Covered Entity or Business Associate does not have actual knowledge that the residual information in the data could be used alone, or in combination with other information, to identify an individual. Safe Harbor is a highly prescriptive approach to de-identification. Under this method, all dates must be generalized to year and zip codes reduced to three digits. The same approach is used on the data regardless of the context. Even if the information is to be shared with a trusted researcher who wishes to analyze the data for seasonal variations in acute respiratory cases and, thus, requires the month of hospital admission, this information cannot be provided; only the year of admission would be retained.

### Expert Determination

Expert Determination takes a risk-based approach to de-identification that applies current standards and best practices from the research to determine the likelihood that a person could be identified from their protected health information. This method requires that a person with appropriate knowledge of and experience with generally accepted statistical and scientific principles and methods render the information not individually identifiable. It requires:

That the risk is very small that the information could be used alone, or in combination with other reasonably available information, by an anticipated recipient to identify an individual who is a subject of the information;
Documents the methods and results of the analysis that justify such a determination.

### Research on decedents

The key law about research in electronic health record data is HIPAA Privacy Rule. This law allows use of electronic health record of deceased subjects for research (HIPAA Privacy Rule (section 164.512(i)(1)(iii))).
