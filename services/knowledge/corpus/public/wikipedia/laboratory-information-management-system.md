---
title: Laboratory information management system
requested_title: Laboratory information management system
revision_id: 1369984301
revision_timestamp: '2026-08-18T11:57:33Z'
url: https://en.wikipedia.org/w/index.php?oldid=1369984301
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

A laboratory information management system (LIMS), sometimes referred to as a laboratory information system (LIS) or laboratory management system (LMS), is a software-based solution with features that support a modern laboratory's operations. They tend to be handled by inventory laboratory technicians. Key features include—but are not limited to—workflow and data tracking support, flexible architecture, and data exchange interfaces, which fully "support its use in regulated environments". The features and uses of a LIMS have evolved over the years from simple sample tracking to an enterprise resource planning tool that manages multiple aspects of  laboratory informatics.
There is no useful definition of the term "LIMS" as it is used to encompass a number of different laboratory informatics components.  The spread and depth of these components is highly dependent on the LIMS implementation itself. All LIMSs have a workflow component and some summary data management facilities but beyond that there are significant differences in functionality.
Historically the LIMyS, LIS, and process development execution system (PDES) have all performed similar functions.  The term "LIMS" has tended to refer to informatics systems targeted for environmental, research, or commercial analysis such as pharmaceutical or petrochemical work. "LIS" has tended to refer to laboratory informatics systems in the forensics and clinical markets, which often required special case management tools.  "PDES" has generally applied to a wider scope, including, for example, virtual manufacturing techniques, while not necessarily integrating with laboratory equipment.
In recent times LIMS functionality has spread even further beyond its original purpose of sample management. Assay data management, data mining, data analysis, and electronic laboratory notebook (ELN) integration have been added to many LIMS, enabling the realization of translational medicine completely within a single software solution. Additionally, the distinction between LIMS and LIS has blurred, as many LIMS now also fully support comprehensive case-centric clinical data.

## History

Up  until the late 1970s, the management of laboratory samples and the associated analysis and reporting were time-consuming manual processes often riddled with transcription errors. This gave some organizations impetus to streamline the collection of data and how it was reported.  Custom in-house solutions were developed by a few individual laboratories, while some enterprising entities sought to develop commercial reporting solutions in the form of special instrument-based systems.
In 1982 the first generation of LIMS was introduced in the form of a centralized minicomputer, which offered automated reporting tools. As the interest in these early LIMS grew, industry leaders like Gerst Gibbon of the Federal Energy Technology Center in Pittsburgh began planting the seeds through LIMS-related conferences. By 1988 the second-generation commercial offerings were tapping into relational databases to expand LIMS into more application-specific territory, and International LIMS Conferences were in full swing. As personal computers became more powerful and prominent, a third generation of LIMS emerged in the early 1990s. These new LIMS took advantage of  client/server architecture, allowing laboratories to implement better data processing and exchanges.
By 1995 the client/server tools allowed the processing of data anywhere on the network. Web-enabled LIMS were introduced the following year, enabling researchers to extend operations outside the laboratory. From 1996 to 2002 additional functionality was included, from wireless networking and georeferencing of samples, to the adoption of XML standards and Internet purchasing.
As of 2012, some LIMS have added additional characteristics such as clinical functionality, electronic laboratory notebook (ELN) functionality, as well a rise in the software as a service (SaaS) distribution model.

## Technology

### Operations

The LIMS is an evolving concept, with new features and functionality being added often. As laboratory demands change and technological progress continues, the functions of a LIMS will likely also change. Despite these changes, a LIMS tends to have a base set of functionality that defines it. That functionality can roughly be divided into five laboratory processing phases, with numerous software functions falling under each:
(1) the reception and log in of a sample and its associated customer data,
(2) the assignment, scheduling, and tracking of the sample and the associated analytical workload,
(3) the processing and quality control associated with the sample and the utilized equipment and inventory,
(4) the storage of data associated with the sample analysis,
(5) the inspection, approval, and compilation of the sample data for reporting and/or further analysis.
There are several pieces of core functionality associated with these laboratory processing phases that tend to appear in most LIMS:

#### Sample management

The core function of LIMS has traditionally been the management of samples. This typically is initiated when a sample is received in the laboratory, at which point the sample will be registered in the LIMS. Some LIMS will allow the customer to place an "order" for a sample directly to the LIMS at which point the sample is generated in an "unreceived" state. The processing could then include a step where the sample container is registered and sent to the customer for the sample to be taken and then returned to the lab. The registration process may involve accessioning the sample and producing barcodes to affix to the sample container. Various other parameters such as clinical or phenotypic information corresponding with the sample are also often recorded. The LIMS then tracks chain of custody as well as sample location. Location tracking usually involves assigning the sample to a particular freezer location, often down to the granular level of shelf, rack, box, row, and column. Other event tracking such as freeze and thaw cycles that a sample undergoes in the laboratory may be required.
Modern LIMS have implemented extensive configurability as each laboratory's needs for tracking additional data points can vary widely. LIMS vendors cannot typically make assumptions about what these data tracking needs are, and therefore vendors must create LIMS that are adaptable to individual environments. LIMS users may also have regulatory concerns to comply with such as CLIA, HIPAA, GLP, and FDA specifications, affecting certain aspects of sample management in a LIMS solution. One key to compliance with many of these standards is audit logging of all changes to LIMS data, and in some cases a full electronic signature system is required for rigorous tracking of field-level changes to LIMS data.

#### Instrument and application integration

Modern LIMS offer an increasing amount of integration with laboratory instruments and applications. A LIMS may create control files that are "fed" into the instrument and direct its operation on some physical item such as a sample tube or sample plate. The LIMS may then import instrument results files to extract data for quality control assessment of the operation on the sample. Access to the instrument data can sometimes be regulated based on chain of custody assignments or other security features if need be.
Modern LIMS products now also allow for the import and management of raw assay data results. Modern targeted assays such as qPCR and deep sequencing can produce tens of thousands of data points per sample. Furthermore, in the case of drug and diagnostic development as many as 12 or more assays may be run for each sample. In order to track this data, a LIMS solution needs to be adaptable to many different assay formats at both the data layer and import creation layer, while maintaining a high level of overall performance. Some LIMS products address this by simply attaching assay data as BLOBs to samples, but this limits the utility of that data in data mining and downstream analysis.

#### Electronic data exchange

The exponentially growing volume of data created in laboratories, coupled with increased business demands and focus on profitability, have pushed LIMS vendors to increase attention to how their LIMS handles electronic data exchanges. Attention must be paid to how an instrument's input and output data is managed, how remote sample collection data is imported and exported, and how mobile technology integrates with the LIMS. The successful transfer of data files in spreadsheets and other formats is a pivotal aspect of the modern LIMS. In fact, the transition "from proprietary databases to standardized database management systems such as MySQL" has arguably had one of the biggest impacts on how data is managed and exchanged in laboratories. In addition to mobile and database electronic data exchange, many LIMS support real-time data exchange with Electronic Health Records used in core hospital or clinic operations.

#### Additional functions

Aside from the key functions of sample management, instrument and application integration, and electronic data exchange, there are numerous additional operations that can be managed in a LIMS. This includes but is not limited to:

Audit management
Fully track and maintain an audit trail
Barcode handling
Assign one or more data points to a barcode format; read and extract information from a barcode
Chain of custody
Assign roles and groups that dictate access to specific data records and who is managing them
Compliance
Follow regulatory standards that affect the laboratory
Customer relationship management
Handle the demographic information and communications for associated clients
Document management
Process and convert data to certain formats; manage how documents are distributed and accessed
Instrument calibration and maintenance
Schedule important maintenance and calibration of lab instruments and keep detailed records of such activities
Inventory and equipment management
Measure and record inventories of vital supplies and laboratory equipment
Manual and electronic data entry
Provide fast and reliable interfaces for data to be entered by a human or electronic component
Method management
Provide one location for all laboratory process and procedure (P&P) and methodology to be housed and managed as well as connecting each sample handling step with current instructions for performing the operation
Personnel and workload management
Organize work schedules, workload assignments, employee demographic information, training, and financial information
Quality assurance and control
Gauge and control sample quality, corrective and preventive action (CAPA), data entry standards, and workflow
Reports
Create and schedule reports in a specific format; schedule and distribute reports to designated parties
Time tracking
Calculate and maintain processing and handling times on chemical reactions, workflows, and more
Traceability
Show audit trail and/or chain of custody of a sample
Workflows
Track a sample, a batch of samples, or a "lot" of batches through its lifecycle

### Client-side options

A LIMS has utilized many architectures and distribution models over the years. As technology has changed, how a LIMS is installed, managed, and utilized has also changed with it. The following represents architectures which have been utilized at one point or another.

#### Thick-client

A thick-client LIMS is a more traditional client/server architecture, with some of the system residing on the computer or workstation of the user (the client) and the rest on the server. The LIMS software is installed on the client computer, which does all of the data processing. Later it passes information to the server, which has the primary purpose of data storage. Most changes, upgrades, and other modifications will happen on the client side.
This was one of the first architectures implemented into a LIMS, having the advantage of providing higher processing speeds (because processing is done on the client and not the server). Additionally, thick-client systems have also provided more interactivity and customization, though often at a greater learning curve. The disadvantages of client-side LIMS include the need for more robust client computers and more time-consuming upgrades, as well as a lack of base functionality through a web browser. The thick-client LIMS can become web-enabled through an add-on component.
Although there is a claim of improved security through the use of a thick-client LIMS, this is based on the misconception that "only users with the client application installed on their PC can access server side information". This secrecy-of-design reliance is known as security through obscurity and ignores an adversary's ability to mimic client-server interaction through, for example, reverse engineering, network traffic interception, or simply purchasing a thick-client license. Such a view is in contradiction of the "Open Design" principle of the National Institute of Standards and Technology's Guide to General Server Security which states that "system security should not depend on the secrecy of the implementation or its components", which can be considered as a reiteration of Kerckhoffs's principle.

#### Thin-client

A thin-client LIMS is a more modern architecture which offers full application functionality accessed through a device's web browser. The actual LIMS software resides on a server (host) which feeds and processes information without saving it to the user's hard disk. Any necessary changes, upgrades, and other modifications are handled by the entity hosting the server-side LIMS software, meaning all end-users see all changes made. To this end, a true thin-client LIMS will leave no "footprint" on the client's computer, and only the integrity of the web browser need be maintained by the user. The advantages of this system include significantly lower cost of ownership and fewer network and client-side maintenance expenses. However, this architecture has the disadvantage of requiring real-time server access, a need for increased network throughput, and slightly less functionality. A sort of hybrid architecture that incorporates the features of thin-client browser usage with a thick client installation exists in the form of a web-based LIMS.
Some LIMS vendors are beginning to rent hosted, thin-client solutions as "software as a service" (SaaS). These solutions tend to be less configurable than on-premises solutions and are therefore considered for less demanding implementations such as laboratories with few users and limited sample processing volumes.
Another implementation of the thin client architecture is the maintenance, warranty, and support (MSW) agreement. Pricing levels are typically based on a percentage of the license fee, with a standard level of service for 10 concurrent users being approximately 10 hours of support and additional customer service, at a roughly $200 per hour rate. Though some may choose to opt out of an MSW after the first year, it is often more economical to continue the plan in order to receive updates to the LIMS, giving it a longer life span in the laboratory.

#### Web-enabled

A web-enabled LIMS architecture is essentially a thick-client architecture with an added web browser component. In this setup, the client-side software has additional functionality that allows users to interface with the software through their device's browser. This functionality is typically limited only to certain functions of the web client. The primary advantage of a web-enabled LIMS is the end-user can access data both on the client side and the server side of the configuration. As in a thick-client architecture, updates in the software must be propagated to every client machine. However, the added disadvantages of requiring always-on access to the host server and the need for cross-platform functionality mean that additional overhead costs may arise.

#### Web-based

A web-based LIMS architecture is a hybrid of the thick- and thin-client architectures. While much of the client-side work is done through a web browser, the LIMS may also require the support of desktop software installed on the client device. The end result is a process that is apparent to the end-user through a web browser, but perhaps not so apparent as it runs thick-client-like processing in the background. In this case, web-based architecture has the advantage of providing more functionality through a more friendly web interface. The disadvantages of this setup are more sunk costs in system administration and reduced functionality on mobile platforms.

### Configurability

LIMS implementations are notorious for often being lengthy and costly. This is partly due to the diversity of requirements within each lab, but also to the inflexible nature of most LIMS products for adapting to these widely varying requirements. Newer LIMS solutions are beginning to emerge that take advantage of modern techniques in software design that are inherently more configurable and adaptable — particularly at the data layer — than prior solutions. This means not only that implementations are much faster, but also that the costs are lower and the risk of obsolescence is minimized.

## Distinction between a LIMS and a LIS

Until recently, the LIMS and Laboratory Information System (LIS) have exhibited a few key differences, making them noticeably separate entities.
A LIMS traditionally has been designed to process and report data related to batches of samples from biology labs, water treatment facilities, drug trials, and other entities that handle complex batches of data. A LIS has been designed primarily for processing and reporting data related to individual patients in a clinical setting.
A LIMS may need to satisfy good manufacturing practice (GMP) and meet the reporting and audit needs of the regulatory bodies and research scientists in many different industries. A LIS, however, must satisfy the reporting and auditing needs of health service agencies e.g. the hospital accreditation agency, HIPAA in the US, or other clinical medical practitioners.
A LIMS is most competitive in group-centric settings (dealing with "batches" and "samples") that often deal with mostly anonymous research-specific laboratory data, whereas a LIS is usually most competitive in patient-centric settings (dealing with "subjects" and "specimens") and clinical labs. An LIS is regulated as a medical device by the FDA, and the companies that produce the software are therefore liable for defects. Due to this, a LIS can not be customized by the client.

## Standards

A LIMS covers standards such as 21 CFR Part 11 from the Food and Drug Administration (United States), ISO/IEC 17025,
ISO 15189, ISO 20387, Good Clinical Practice (GCP), Good Laboratory Practice (GLP), Good Manufacturing Practice (GMP), FDA Food Safety Modernization Act (FSMA), HACCP, and ISBER Best Practices.
