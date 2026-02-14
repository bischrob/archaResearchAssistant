# Research for 2. Data Foundations for Archaeology

- Date: 2026-02-14
- Question: Write a college-level textbook chapter in markdown for '2. Data Foundations for Archaeology'. Audience: undergraduate computer science students learning computational archaeology. Requirements: include sections 'Learning Objectives', 'Core Ideas', 'Worked Workflow', 'Case Study', 'Common Mistakes', 'Exercises', and 'Key Takeaways'. Include concrete technical detail, but keep explanations accessible. Explicitly cover this focus: Explain data models, relational structures, identifiers, metadata, chronology, uncertainty, and data quality with practical examples. Use only grounded RAG evidence and cite claims with citation tags like [C1].
- Search query used: computational archaeology textbook data foundations data models relational structures identifiers metadata chronology uncertainty data quality undergraduate computer science RAG evidence
- Model: gpt-5.1
- RAG results: 14

## Synthesized Draft

## 2. Data Foundations for Archaeology

### Learning Objectives

By the end of this chapter, you should be able to:

- Explain why data modeling choices at creation time strongly affect later reuse in archaeology. [C5][C8]  
- Describe basic data models (tabular, relational, graph‑like) and how they support complex, contextual archaeological data. [C2][C5][C8]  
- Explain the role of identifiers in linking archaeological data and improving data quality and reusability. [C3][C8][C13]  
- Define and illustrate metadata and why data centers and archives insist on “adequate metadata.” [C1][C11][C12][C13]  
- Discuss chronology, uncertainty, and how poor documentation in legacy data complicates interpretation. [C5][C8][C9]  
- Recognize common data quality dimensions and why validation and consistency matter for archaeological datasets. [C5][C8][C11][C3]  
- Apply these ideas in a simple, end‑to‑end workflow for preparing archaeological data for publication and reuse. [C5][C6][C11][C12]  

---

### Core Ideas

#### 2.1 Archaeological Data as “Slow”, Complex, Structured Data

Archaeological digital data are often created slowly over years and arrive in “large lumps of complex contextualized information,” rather than as continuous streams of “big data.” [C14] These “lumps” can include numeric measurements, text descriptions, images, geospatial data, and temporal information, and are best handled when they are “highly structured.” [C14] This makes data modeling a central concern for computational archaeology. [C5][C8]

Researchers often lack formal training in data management, and poor data modeling at the start of a project can impede later reuse and only becomes apparent during attempted reuse. [C5][C8] This chapter is about avoiding that trap.

---

#### 2.2 Data Models and Relational Structures

**Data modeling** is the organization and layout of data so that complex phenomena can be represented in a structured way. [C5][C8]

- Archaeological teams often begin with *flat tabular data* (e.g., spreadsheets). [C5]  
- However, “adequate modeling of complex phenomena, such as tooth eruption and wear, as simple, flat tabular data … is challenging and can impede data reuse.” [C5]  

A relational mindset helps: instead of one big table, think in terms of related entities (e.g., “specimens,” “contexts,” “sites”) connected by keys. Even if implemented in spreadsheets, the goal is to organize data in multiple linked tables rather than encoding everything in one flat sheet. [C5][C8]

In other domains, graph databases are used to store “type definitions, constraints, relationships between entities, and the mappings between the model and the underlying source systems,” providing “structured yet schema‑free” models that handle variable, exceptional structures and allow rapid evolution of the model. [C2] Archaeological data share similar needs for representing relationships and schema evolution, making graph‑like and relational ways of thinking useful even if you implement them in conventional tools. [C2][C14]

Geospatial and spatial‑temporal data are especially relevant in archaeology, and in other fields graph databases can store geospatial data alongside other kinds of data for “complex multidimensional querying across several domains.” [C10][C14] This underscores the value of data models that can combine spatial, temporal, and contextual relationships.

---

#### 2.3 Identifiers and Relational Thinking

Identifiers are central to relational data and to archaeological data quality and reuse.

Good data management practices explicitly foreground identifiers as “fundamental” for data quality and reusability. [C8] Identifier‑centric practices support a “more relational and contextual view” of datasets, rather than treating each dataset as isolated. [C8] Collaborative identifier practices in archaeology are specifically proposed as a way to promote data quality and reuse. [C3]

Identifiers enable:

- Linking related records across tables or files (e.g., linking a zooarchaeological specimen to its context record). [C8][C3]  
- Connecting datasets archived in data centers or domain‑specific archives, where the original source should be cited and tracked. [C1][C11][C12]  
- Tracking use of datasets over time, as data centers “track data access using automated tools” and maintain indices. [C1]  

A core lesson from data reuse work is that datasets “need to have adequate documentation and consistency to be widely usable,” and these qualities are intertwined with clear identifiers and well‑modeled relationships. [C13][C5][C8]

---

#### 2.4 Metadata: Data About Data

Data centers “add significant value to data sets through quality control procedures, ensuring adequate metadata, aggregating data from different sources, and providing online tools to explore, visualize … and download the data.” [C11] They also function as intermediaries that “prepare data for reuse by eliciting, organizing, storing, packaging and/or preserving data.” [C12]

Key metadata roles for archaeology include:

- Describing provenance (who collected the data, when, and how). [C11][C12][C13]  
- Documenting coding schemes (to avoid situations where “coding documentation often does not exactly match coded data”). [C5]  
- Enabling users to “examine the original data, and to easily combine the data with other data.” [C1][C11]  

Without metadata, archaeologists using legacy data face “data integrity concerns, and data documentation needs,” making it hard to judge the “dataset’s suitability for analysis.” [C9] Data publication models emphasize that “datasets need to have adequate documentation and consistency to be widely usable.” [C13]

---

#### 2.5 Chronology, Uncertainty, and Context

Archaeological datasets often embed chronological and contextual information that is crucial for interpretation but can be poorly modeled or documented.

In the “Other People’s Data” study, three researchers independently analyzed a zooarchaeological dataset and, despite “a similar initial approach,” arrived at “markedly different interpretive conclusions.” [C9] The study highlights “interpretive issues, data integrity concerns, and data documentation needs” when using legacy data. [C9] A major reason different interpretations arise is that underlying contextual information—including chronology and uncertainty—is not captured or expressed clearly enough in the data model and metadata. [C5][C8][C9]

Machine learning applications in archaeology depend on “highly structured and large datasets” to support robust interpretations. [C14] This makes it especially important to encode temporal and contextual variables (e.g., phases, relative sequences, and uncertainties) explicitly rather than leaving them implicit in narratives or undocumented codes. [C5][C8][C14]

---

#### 2.6 Data Quality and Validation

Data quality in archaeology has been studied in areas such as “archaeological survey data quality, durability, and use,” “data quality in zooarchaeological faunal identification,” and archaeobotany. [C3] Foundational work in data quality research and open data stresses that data quality involves more than accuracy and that quality assessment is challenging in the era of large and complex datasets. [C3]

Concrete, project‑level problems include:

- “Errors in coded data are difficult to notice, and coding documentation often does not exactly match coded data.” [C5]  
- Data in coded form, “even when documented,” can greatly multiply the effort required for reuse. [C5]  
- Many data modeling problems at the start of a project “impact data quality and only become apparent in later data reuse.” [C8]  

Recommended practices to improve data quality include:

- Validation practices to promote consistency and reduce errors. [C8]  
- Specifying data types (e.g., enforcing integer, decimal, or Boolean values where needed). [C8]  
- Using open and nonproprietary file formats. [C8]  

Data centers and archives also contribute to quality by applying editorial review, quality control, and standardization, similar to what journal publishers do for print media. [C11][C12][C13] Some repositories and platforms (e.g., those compared in discussions of the digital archaeological record) explicitly emphasize data management, preservation, and “flexible structure,” which depend on sound data quality practices. [C7]

---

### Worked Workflow: From Field Data to Reusable Dataset

This section walks through a simplified workflow for preparing an archaeological dataset for reuse, focusing on data models, identifiers, metadata, chronology, uncertainty, and quality.

#### Step 1: Plan for Data Publication and Reuse

Best practice begins *before* data collection. Principal investigators are urged to “plan for data publication so the preparation of the data for publication is simplified and low cost.” [C6] Planning for reuse means:

- Designing data models that reflect complex phenomena (not forcing everything into a single flat table). [C5][C8]  
- Anticipating that your dataset may be integrated with other datasets in data centers that perform quality control and aggregation. [C1][C11][C12]  

Aligning “data creation practices for the needs of wider community reuse from the start” reduces costly “cleanup and translation work” later. [C8]

#### Step 2: Choose a Structured Data Model

Suppose you are recording animal bones from an excavation:

- Instead of a single spreadsheet that mixes specimen data, context, site, and analyst information, you define separate tables (or sheets) for:
  - Contexts (with identifiers, stratigraphic relationships, dates, etc.)  
  - Specimens (each with a unique identifier, link to context, taxon, measurements, etc.)  
  - Analysts (identifier, name, lab, methods used)  

This aligns with the recommendation for “better data modeling” and the observation that modeling complex things like tooth wear as simple flat tables “is challenging and can impede data reuse.” [C5] It also supports a more relational and contextual view of data, which identifier‑centric practices promote. [C8]

If your data incorporate geospatial information (e.g., find spots, survey units), designing the model to handle spatial attributes will make it easier for later systems (including graph or spatial databases) to support “complex multidimensional querying across several domains.” [C10][C14]

#### Step 3: Design and Apply Identifiers

For each entity (site, context, specimen, analyst), you:

- Assign a unique identifier that is stable over time. [C8][C3]  
- Use these identifiers consistently in all tables, documentation, and eventual publications. [C1][C13]  

Collaborative identifier practices explicitly aim to “promote data quality and reuse,” as identifiers are “fundamental” to quality and reusability. [C8][C3] Using identifiers from shared schemes or repositories, when possible, also supports cross‑dataset linking once your data are in archives or data centers that aggregate from “different sources.” [C1][C11][C12]

#### Step 4: Capture Rich Metadata, Especially for Chronology and Methods

As you record data:

- Document the coding system for every categorical field (e.g., species codes, wear stages), and keep documentation synchronized with actual values to avoid mismatches. [C5]  
- Record how chronological information is determined (e.g., which dating methods, what uncertainties). While the cited texts do not prescribe a specific structure, they emphasize that poor modeling and documentation can cause major interpretive divergence later. [C5][C8][C9]  
- Ensure that metadata about collection, processing, and analysis are included, because later users rely on this to judge “dataset’s suitability for analysis” and to address “data documentation needs.” [C9][C13]  

Data centers and archives will rely on this metadata to perform editorial quality control and to provide documentation for reuse. [C11][C12][C13]

#### Step 5: Validate, Type, and Clean Data

Implement data quality measures during creation:

- Enforce appropriate data types (integer, decimal, Boolean, etc.) for each field. [C8]  
- Use validation rules to promote consistency and reduce obvious errors. [C8]  
- Periodically review data to detect coding problems, given that “errors in coded data are difficult to notice,” and documentation may not match actual codes if not carefully maintained. [C5]  

Because “adapting complex data ‘late in the game’ can be costly,” investing effort in validation and modeling early pays off by reducing cleanup later. [C8]

#### Step 6: Prepare for Archiving and Publication

When the project is complete (or at major milestones):

- Package data and metadata in open, nonproprietary formats, as recommended in good data management practice. [C8]  
- Deposit data in domain‑relevant archives or data centers rather than personal websites, since specialized centers:
  - Apply “quality control” and ensure “adequate metadata.” [C11]  
  - Aggregate data and provide tools to “explore, visualize … and download the data.” [C11]  
  - Track data access and maintain indices, supporting citation and impact tracking. [C1][C12]  

For archaeology, repositories and platforms for data management, publishing, and preservation (such as those compared in discussions of the “digital archaeological record”) are explicitly geared to provide data management, flexible structures, and preservation services. [C7]

Researchers advocating “data publication” stress that datasets should not be mere undocumented “dumps,” but should have “adequate documentation and consistency” and clear signals of quality. [C13] Peer‑review and editorial processes for data, analogous to those for articles, are part of this model. [C11][C13]

#### Step 7: Enable and Learn from Reuse

Encourage others to reuse your data by:

- Providing stable identifiers, rich metadata, and clear documentation of coding and chronology. [C8][C3][C5][C9][C13]  
- Citing your own and others’ data as you would cite publications, and insisting that citation services and institutions recognize data publications. [C1][C6][C9][C13]  

Experience with reusing data created by others “can build expectations about what constitutes ‘good data’,” and data reusers can apply these experiences to become better data creators, helping “jumpstart virtuous cycles” of better data creation and reuse. [C8]

---

### Case Study: Legacy Zooarchaeological Data and Modeling Pitfalls

A published study examined “other people’s data” by having three researchers independently analyze a decades‑old, orphaned zooarchaeological dataset. [C9]

#### Context

- The dataset was legacy data, not originally prepared for broad reuse. [C9]  
- Researchers sought to determine its “suitability for analysis” and then compared their analytical approaches and results. [C9]  

#### Observed Issues

The study reports:

- Even with a similar initial approach, the three researchers produced “markedly different interpretive conclusions.” [C9]  
- This divergence highlighted:
  - Interpretive issues  
  - Data integrity concerns  
  - Data documentation needs [C9]  

These problems are exactly those expected when:

- Data modeling and organization were not designed with future reuse in mind. [C5][C8][C9]  
- Metadata and coding documentation were inadequate or inconsistent. [C5][C9][C13]  
- Chronological and contextual information required for interpretation was underspecified in machine‑readable form. [C5][C8][C9]  

#### Lessons for Data Foundations

The authors argue for “greater professional recognition for data dissemination,” and they explicitly favor “models of ‘data publication’ over ‘data sharing’ or ‘data archiving’.” [C9] Their argument rests on the idea that:

- Data publication implies editorial processes, documentation standards, and signals of quality, akin to traditional publication. [C13][C11]  
- Simply archiving data without robust modeling and metadata does not address interpretive and quality issues. [C9][C13]  

For computer science students, this case illustrates how technical design choices (identifiers, relational structure, explicit handling of chronology and uncertainty) and documentation are not merely implementation details; they directly affect the scientific inferences that can be drawn from data. [C5][C8][C9][C13]

---

### Common Mistakes

Drawing from the cited literature, several recurrent problems in archaeological data foundations are visible:

1. **Treating Data as Flat Spreadsheets Only**

   - Attempting to model “complex phenomena, such as tooth eruption and wear” as simple flat tables “is challenging and can impede data reuse.” [C5]  
   - This often leads to overloaded columns, ambiguous codes, and difficulty linking records across contexts.

2. **Ignoring Identifiers or Using Ad Hoc Codes**

   - Identifier practices are “fundamental” to data quality and reuse. [C8]  
   - Without stable, documented identifiers, it is difficult to build relational or contextual views of datasets, or to integrate across datasets. [C3][C8][C1]

3. **Weak or Missing Metadata**

   - Legacy datasets frequently lack sufficient documentation, leading to “data integrity concerns” and “data documentation needs.” [C9]  
   - Data publication advocates emphasize that datasets “need to have adequate documentation and consistency to be widely usable.” [C13]

4. **Poor Coding and Validation**

   - “Errors in coded data are difficult to notice,” and documentation often does not exactly match coded values. [C5]  
   - Lack of validation and data typing (e.g., failing to specify integers, decimals, or Booleans) increases error rates and cleanup costs. [C8]

5. **Late, Costly Cleanup (“Late in the Game” Fixes)**

   - “Adapting complex data ‘late in the game’ can be costly,” and many modeling problems only become apparent in reuse. [C8]  
   - This is particularly problematic for “slow data” in archaeology that took years to create. [C14]

6. **Data “Dumps” Instead of Curated Publications**

   - Data sharing advocates caution that sharing should be more than “dumps of raw and undocumented data on the Web.” [C13]  
   - Without editorial review, quality control, and metadata, data may be technically available but effectively unusable. [C11][C12][C13]

---

### Exercises

1. **Identify Modeling Flaws**

   You are given a hypothetical spreadsheet with columns: `Site`, `Context`, `BoneID`, `SpeciesCode`, `AgeStage`, `StratLevel`, `Notes`.  
   - List at least three ways this flat structure could “impede data reuse” for complex phenomena. [C5]  
   - Propose additional tables (entities) and identifiers you would introduce to make the data more relational and reusable. [C5][C8]

2. **Design an Identifier Scheme**

   For a small excavation project recording contexts, samples, and artifacts:
   - Sketch an identifier scheme (naming conventions and relationships) that would support linking these entities and later reuse. [C8][C3]  
   - Explain how your scheme would help a data center aggregate your dataset with others and track usage. [C1][C11][C12]

3. **Metadata Checklist**

   Create a metadata checklist for an archaeological dataset intended for publication in a domain data center:
   - Include at least: provenance, coding schemes, spatial reference information, temporal coverage, methods, and file formats. [C1][C11][C12][C13]  
   - Explain how each metadata element supports quality control and reuse.

4. **Legacy Data Evaluation**

   Imagine you receive a decades‑old zooarchaeological dataset with minimal documentation.  
   - Describe a step‑by‑step approach to assessing its “suitability for analysis,” drawing on the issues of data integrity and documentation raised in the legacy study. [C9]  
   - Identify which missing pieces of information would most threaten your ability to interpret chronology and context reliably. [C5][C8][C9]

5. **Validation Rules Design**

   For an artifact table with fields: `ArtifactID`, `ContextID`, `Length_mm`, `Width_mm`, `IsComplete`, `MaterialCode`:
   - Specify data types and basic validation rules for each field, in line with good practices like data typing and validation to promote consistency. [C8][C5]  
   - Explain how these rules help reduce errors that later data editors would otherwise have to correct. [C5][C8]

---

### Key Takeaways

- Archaeological data are “slow” and complex “lumps” of structured, contextual information; effective computational work depends on solid data models. [C14][C5][C8]  
- Poor data modeling at creation time often goes unnoticed until reuse, when it can severely “impede data reuse” and require costly cleanup. [C5][C8]  
- Identifiers are fundamental to data quality and reusability and support a relational, contextual view of datasets and cross‑dataset integration. [C8][C3][C1]  
- Adequate metadata—especially about coding, chronology, methods, and provenance—is essential; without it, legacy data exhibit integrity and documentation problems that undermine interpretation. [C9][C11][C12][C13][C5]  
- Data quality is more than accuracy: it includes consistency, appropriate typing, validation, and fit for reuse, and is addressed through early modeling, validation, and the editorial practices of data centers and archives. [C3][C5][C8][C11][C12][C13]  
- Data publication, with explicit quality control and documentation, is advocated over uncurated “dumps,” and is central to making archaeological data a first‑class scholarly output. [C9][C13][C11][C6]

## Citation Map

- C1: citekey=Costello2009-jz; title=Motivating Online Publication of Data; year=2009; doi=10.1525/bio.2009.59.5.9
- C2: citekey=Robinson2015-un; title=Graph Databases: New Opportunities for Connected Data; year=2015; doi=None
- C3: citekey=Kansa2022-pw; title=Promoting data quality and reuse in archaeology through collaborative identifier practices; year=2022; doi=10.1073/pnas.2109313118
- C5: citekey=Kansa2014-pj; title=Publishing and Pushing: Mixing Models for Communicating Research Data in Archaeology; year=2014; doi=10.2218/ijdc.v9i1.301
- C6: citekey=Costello2009-jz; title=Motivating Online Publication of Data; year=2009; doi=10.1525/bio.2009.59.5.9
- C7: citekey=Clarke2015-ax; title=The Digital Dilemma: Preservation and the Digital Archaeological Record; year=2015; doi=10.7183/2326-3768.3.4.313
- C8: citekey=Kansa2022-pw; title=Promoting data quality and reuse in archaeology through collaborative identifier practices; year=2022; doi=10.1073/pnas.2109313118
- C9: citekey=Atici2013-el; title=Other People’s Data: A Demonstration of the Imperative of Publishing Primary Data; year=2013; doi=10.1007/s10816-012-9132-9
- C10: citekey=Robinson2015-un; title=Graph Databases: New Opportunities for Connected Data; year=2015; doi=None
- C11: citekey=Costello2009-jz; title=Motivating Online Publication of Data; year=2009; doi=10.1525/bio.2009.59.5.9
- C12: citekey=Faniel2011-ue; title=Beyond the Data Deluge: A Research Agenda for Large-Scale Data Sharing and Reuse; year=2011; doi=10.2218/ijdc.v6i1.172
- C13: citekey=Kansa2013-me; title=We All Know That a 14 Is a Sheep: Data Publication and Professionalism in Archaeological Communication; year=2013; doi=10.1353/ema.2013.0007
- C14: citekey=Bickler2021-ko; title=Machine learning arrives in archaeology; year=2021; doi=10.1017/aap.2021.6