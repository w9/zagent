---
title: Scientific workflow system
requested_title: Bioinformatics workflow management system
revision_id: 1369246739
revision_timestamp: '2026-08-13T20:00:53Z'
url: https://en.wikipedia.org/w/index.php?oldid=1369246739
retrieved: '2026-10-06'
license: CC BY-SA 4.0
license_url: https://creativecommons.org/licenses/by-sa/4.0/
attribution: Wikipedia contributors
---

A scientific workflow system is a specialized form of a workflow management system designed specifically to compose and execute a series of computational or data manipulation steps, or workflow, in a scientific application. Scientific workflow systems are generally developed for use by scientists from different disciplines like astronomy, earth science, and bioinformatics. All such systems are based on an abstract representation of how a computation proceeds in the form of a directed graph, where each node represents a task to be executed and edges represent either data flow or execution dependencies between different tasks. Each system typically provides a visual front-end, allowing the user to build and modify complex applications with little or no programming expertise.

## Applications

Distributed scientists can collaborate on conducting large scale scientific experiments and knowledge discovery applications using distributed systems of computing resources, data sets, and devices. Scientific workflow systems play an important role in enabling this vision.
More specialized scientific workflow systems provide a visual programming front end enabling users to easily construct their applications as a visual graph by connecting nodes together, and tools have also been developed to build such applications in a platform-independent manner. Each directed edge in the graph of a workflow typically represents a connection from the output of one application to the input of the next. A sequence of such edges may be called a pipeline.

## Scientific workflows

The simplest computerized scientific workflows are scripts that call in data, programs, and other inputs and produce outputs that might include visualizations and analytical results.  These may be implemented in programs such as R or MATLAB, using a scripting language such as Python with a command-line interface, or more recently using open-source web applications such as Jupyter Notebook.
There are many motives for differentiating scientific workflows from traditional business process workflows. These include:

providing an easy-to-use environment for individual application scientists themselves to create their own workflows.
providing interactive tools for the scientists enabling them to execute their workflows and view their results in real-time.
simplifying the process of sharing and reusing workflows between the scientists.
enabling scientists to track the provenance of the workflow execution results and the workflow creation steps.
By focusing on the scientists, the focus of designing scientific workflow system shifts away from the workflow scheduling activities, typically considered by grid computing environments for optimizing the execution of complex computations on predefined resources, to a domain-specific view of what data types, tools and distributed resources should be made available to the scientists and how can one make them easily accessible and with specific Quality of Service requirements
Scientific workflows are now recognized as a crucial element of the cyberinfrastructure, facilitating e-Science. Typically sitting on top of a middleware layer, scientific workflows are a means by which scientists can model, design, execute, debug, re-configure, and re-run their analysis and visualization pipelines. Part of the established scientific method is to create a record of the origins of a result, how it was obtained, experimental methods used, machine calibrations and parameters, etc. It is the same in e-Science, except provenance data are a record of the workflow activities invoked, services and databases accessed, data sets used, and so forth. Such information is useful for a scientist to interpret their workflow results and for other scientists to establish trust in the experimental result.

## Sharing workflows

Social networking communities such as myExperiment have been developed to facilitate sharing and collaborative development of scientific workflows. Galaxy provide collaborative mechanisms for editing and publication of workflow definitions and workflow results directly on the Galaxy installation.

## Analysis

A key assumption underlying all scientific workflow systems is that the scientists themselves will be able to use a workflow system to develop their applications based on visual flowcharting, logic diagramming, or, as a last resort, writing code to describe the workflow logic.  Powerful workflow systems make it easy for non-programmers to first sketch out workflow steps using simple flowcharting tools, and then hook in various data acquisition, analysis, and reporting tools.  For maximum productivity, details of the underlying programming code should normally be hidden.
Workflow analysis techniques can be used to analyze the properties of such workflows to verify certain properties before executing them. An example of a theoretical formal analysis framework for the verification and profiling of the control-flow aspects of scientific workflows and their data flow aspects for the Discovery Net system is described in the paper, "The design and implementation of a workflow analysis tool" by Curcin et al.
The authors note that introducing program analysis and verification into the workflow world requires detailed understanding of execution semantics of workflow language, including execution properties of nodes and arcs in the workflow graph, understanding functional equivalencies between workflow patterns,  and many other issues.  Doing such analysis is difficult, and addressing these issues requires building on formal methods used in computer science research (e.g. Petri nets) and building on these formal methods to develop user-level tools to reason about the properties of both workflows and workflow systems.  The lack of such tools in the past stopped automated workflow management solutions from maturing from nice-to-have academic toys to production-level tools used outside the narrow circle of early adopters and workflow enthusiasts.

## Notable systems

Notable scientific workflow systems include:

Anduril, bioinformatics and image analysis
Apache Airavata, a general purpose workflow management system
Apache Airflow, a general purpose workflow management system
Apache Taverna, widely used in bioinformatics, astronomy, biodiversity
BioBIKE, a cloud-based bioinformatics platform
Bioclipse, a graphical workbench, with a scripting environment that lets you perform complex actions as a kind of workflow.
Collective Knowledge, a Python-based general workflow and experiment crowdsourcing framework with JSON API and cross-platform package manager
Common Workflow Language, a community-developed YAML-based workflow language, supported by multiple engine implementations.
Cuneiform, a functional workflow language.
Clone Manager from Sci-Ed.
CLC bio, a bioinformatics analysis and workflow management platform from QIAGEN Digital Insights.
Discovery Net, one of the earliest examples of a scientific workflow system
Galaxy, initially targeted at genomics
GenePattern, a powerful scientific workflow system that provides access to hundreds of genomic analysis tools.
Kepler, a scientific workflow management system
KNIME, an open-source data analytics platform
Nextflow, a bioinformatic data analysis workflow system
OnlineHPC, online scientific workflow designer and high performance computing toolkit
Orange, open source data visualization and analysis
Pegasus, an open-source scientific workflow management system
Pipeline Pilot, graphical programming with many tools to address Cheminformatics workflows
Swift parallel scripting language, a scripting language with many of the capabilities of scientific workflow systems built-in.
UGENE provides a workflow management system that is installed on a local computer
VisTrails, a scientific workflow system developed in Python
More than 280 computational data analysis workflow systems have been identified, although the distinction between data analysis workflows and scientific workflows is fluid, as not all analysis workflow systems are used for scientific purposes.

### Comparisons between bioinformatics workflow systems

With a large number of bioinformatics workflow systems to choose from, it becomes difficult to understand and compare the features of the different workflow systems. There has been little work conducted in evaluating and comparing the systems from a bioinformatician's perspective, especially when it comes to comparing the data types they can deal with, the in-built functionalities that are provided to the user or even their performance or usability. Examples of existing comparisons include:

The paper "Scientific workflow systems-can one size fit all?", which provides a high-level framework for comparing workflow systems based on their control flow and data flow properties. The systems compared include Discovery Net, Taverna, Triana, Kepler as well as Yawl and BPEL.
The paper "Meta-workflows: pattern-based interoperability between Galaxy and Taverna" which provides a more user-oriented comparison between Taverna and Galaxy in the context of enabling interoperability between both systems.
The infrastructure paper "Delivering ICT Infrastructure for Biomedical Research" compares two workflow systems, Anduril and Chipster, in terms of infrastructure requirements in a cloud-delivery model.
The paper "A review of bioinformatic pipeline frameworks" attempts to classify workflow management systems based on three dimensions: "using an implicit or explicit syntax, using a configuration, convention or class-based design paradigm and offering a command line or workbench interface".
