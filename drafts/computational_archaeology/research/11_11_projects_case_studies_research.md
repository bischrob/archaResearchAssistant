# Research for 11. Student Projects and Case Studies

- Date: 2026-02-14
- Question: Write a concise but substantive college-level textbook chapter in markdown for '11. Student Projects and Case Studies'. Audience: undergraduate computer science students learning computational archaeology. Include sections: Learning Objectives, Core Ideas, Worked Workflow, Case Study, Common Mistakes, Exercises, Key Takeaways. Focus: Provide project blueprints integrating ML, GIS, network science, ABM, and reproducible documentation for college courses. Use only grounded RAG evidence and cite claims with [C#].
- Search query used: computational archaeology student projects case studies machine learning GIS network science agent based modeling ABM reproducible workflows teaching undergraduate courses textbook chapter
- Model: gpt-5.1
- RAG results: 10

## Synthesized Draft

# 11. Student Projects and Case Studies

## Learning Objectives

By the end of this chapter, you should be able to:

- Describe how GIS and network science have been integrated in archaeological research designs and identify where they fit in a broader computational toolkit.[C8][C9]  
- Interpret basic outputs from multivariate analyses (e.g., PCA, cluster analysis, Mahalanobis distance) in ceramic and compositional studies and recognize their role in project design.[C1][C3][C5][C6][C7]  
- Outline a workflow for building a GIS‑informed network model for archaeological regions, including the use of centrality measures.[C8][C9][C10]  
- Recognize common statistical pitfalls in cluster-based provenance and grouping studies and plan projects that avoid them.[C4][C5][C7]  
- Design course‑level project blueprints that emphasize transparent methods and interpretable models grounded in archaeological questions.[C8][C9][C10]  

## Core Ideas

Network science and GIS have become central to how archaeologists model connectivity, movement, and spatial structure.[C8][C9] GIS has been described as an indispensable tool in archaeology, with a well‑documented history and diverse applications, including regional analyses that feed directly into network models.[C8] Network science in archaeology provides formal tools to represent relations—such as material exchange, movement, and spatial proximity—as networks, and to analyze them with measures and models drawn from network theory.[C9]

Within material culture studies, multivariate statistics are used to explore structure in compositional or attribute datasets. Principal components analysis (PCA) and cluster analysis have been applied to ceramic assemblages and PIXE (particle-induced X‑ray emission) databases to identify groups and potential outliers.[C1][C2][C3][C5][C6][C7] Mahalanobis distance is used in these contexts to evaluate the strength of statistically defined groups and probabilities of group membership.[C1][C5][C7]

Case studies in network archaeology demonstrate how regional networks can be modeled and evaluated. One study of the Calakmul region outlines a methodology that couples GIS analyses with social network analysis (SNA), ending with a set of centrality measures used to interpret the resulting network model.[C8] Another study on Mississippian West‑central Illinois uses multilayer networks and randomized graph models (including Erdős–Rényi random networks) to evaluate ceramic industry economic networks across time, visualizing these as graph layouts and geographic network graphs and comparing observed network statistics against randomized baselines.[C10]

These examples collectively highlight key project design principles for computational archaeology in coursework: explicit research questions, careful data preparation, methodologically transparent workflows (from GIS to SNA and multivariate statistics), and systematic evaluation of results using diagnostic metrics and randomized comparisons.[C1][C3][C5][C7][C8][C9][C10]

## Worked Workflow: GIS‑Informed Network Project

This section outlines a generic, course‑level workflow that mirrors the Calakmul network modeling approach and broader trends in archaeological network science.[C8][C9]

### 1. Define the Research Problem

Begin with a regional question that can be expressed in terms of connectivity—for example, how sites in a given region might have been connected through movement, exchange, or visibility. The Calakmul project explicitly centers on creating a network model of the Calakmul region and frames GIS and SNA as complementary methodological pillars.[C8]

### 2. Build a GIS Base

Construct a GIS database for the study area, including site locations and relevant environmental or infrastructural features (e.g., terrain, possible routes). The Calakmul methodology chapter summarizes archaeological GIS history and notes that GIS has become an indispensable tool, with a variety of analyses available for building such regional models.[C8] The project design should specify which GIS analyses (e.g., those described as “various GIS analyses” in the Calakmul study) will be used to derive potential connections between sites.[C8]

### 3. Derive Network Edges from GIS

Use GIS‑based analyses to infer which pairs of locations are potentially connected. In the Calakmul framework, the GIS work provides the foundation for a network model “centred on the Calakmul region,” with the GIS analyses explicitly feeding the later network construction.[C8] While the detailed list of analyses is not in the excerpt, the structure is clear: GIS provides spatial relationships that are translated into a network representation.

### 4. Construct the Network

Represent sites as nodes and GIS‑derived relationships as edges. The Calakmul project then introduces network methodology and SNA, presenting an overview of centrality measures that will be used to complement the GIS results.[C8] This step aligns with broader network science in archaeology, where different types of relations (movement, material culture, spatial proximity, etc.) are formalized as networks.[C9]

### 5. Apply Network Measures

Compute centrality measures (as outlined in the Calakmul methodology) to characterize nodes in terms of their role within the network.[C8] In the broader network archaeology landscape, such measures are key to answering questions about the relative importance of sites and relationships.[C9]

### 6. Evaluate and Compare Networks

Use network randomization and visualization to interpret and validate the model. The Mississippian multilayer network study computes network statistics on observed networks and compares them with distributions obtained from 5,000 Erdős–Rényi random graphs, plotting the observed statistic as a red line against a histogram of randomized results.[C10] This randomization approach is used for both pre‑ and post‑migration ceramic industry economic networks and can be adapted in coursework to teach students how to assess whether observed structure differs from random expectation.[C10]

### 7. Document the Workflow

Methodological chapters in both the Calakmul and network science references clearly articulate their steps and analytical choices.[C8][C9] Course projects should mirror this structure by requiring written documentation of each step: problem definition, data sources, GIS analyses, network construction, measures used, and evaluation procedures. This supports transparency and reproducibility at the course level, even if full code or data sharing is not specified in the excerpts.

## Case Study: Ceramic Networks and Compositional Grouping

This case study combines multivariate analysis and network thinking conceptually via ceramics and compositional datasets.

### Multivariate Grouping in Ceramic Studies

In a study of Parowan pottery, PCA was used to analyze ceramic samples. Plots of principal components (PC1 vs. PC2 and PC1 vs. PC3) display ceramic types and sites—such as Parowan Valley, Baker, Mukwitch, and Sevier—mapped into multivariate space to examine relationships between sites and types.[C6] These PCA plots provide an exploratory view of structure in the data, which can motivate clustering and grouping decisions.[C6]

Cluster analysis methods, including Ward’s algorithm and the average link algorithm, were then applied to the same dataset to identify compositional groups among ceramic sherds.[C1][C4][C5] A dendrogram produced with Ward’s algorithm displays samples (cases) and the distances at which they join clusters.[C1][C5] A separate dendrogram produced with the average link algorithm similarly groups cases based on distances.[C4] These analyses exemplify how students can move from PCA to hierarchical clustering within a project.

To evaluate the strength of identified clusters, Mahalanobis distance was computed for each sample relative to the proposed groups.[C1][C5] Initially, samples with extremely low probabilities of group membership (P < 0.1) were removed to refine groups.[C5] However, when Mahalanobis distances were recalculated, some groups showed unexpectedly low membership probabilities even in “tighter” configurations, prompting methodological doubts and discussion.[C4][C5]

### Cluster Analysis in PIXE Compositional Data

In a separate study of turquoise and Olivella ornaments, PIXE database measurements (expressed as normalized oxides) were clustered using Ward’s and average link algorithms.[C2][C3][C7] Dendrograms illustrate the results of Ward’s cluster analysis on normalized oxides and on log‑transformed normalized oxides, as well as the average link cluster analysis on normalized oxides.[C2][C3] Two outliers were identified in a cursory inspection and removed, leaving 38 cases for cluster analysis.[C7] Particular attention was given to specific cases (e.g., geological and archaeological samples and a sample from the Florence Junction Project) when interpreting the resulting clusters.[C7]

Mahalanobis distance was also attempted as a group evaluation metric in this study, but its use was constrained by data limitations. The calculation requires at least two more samples than measured variables; to satisfy this requirement, Mn (an element with the least variation) was removed from consideration, allowing group probabilities to be assessed for only a two‑cluster solution.[C7] High returned probabilities led the author to express caution and to avoid relying solely on principal component scores (e.g., the first principal component) as the only variable in Mahalanobis distance calculations.[C7] Instead, the dataset was interpreted primarily from the cluster analyses.[C7]

### Toward Network Interpretation

Although the ceramic and PIXE studies focus on group identification rather than explicit network construction, they provide project templates for building node attributes or relationships for later network analysis. For example, distinct compositional groups or shared membership across sites can be used in course projects to derive relational ties between sites or assemblages, which are then modeled as networks in line with broader material culture networks discussed in network science for archaeology.[C6][C7][C9] A course project can therefore link these multivariate techniques to the network methods outlined for archaeological networks.[C9][C10]

## Common Mistakes

Drawing on the ceramic and PIXE studies and network modeling examples, several methodological pitfalls are evident:

1. **Over‑interpreting cluster outputs without robust evaluation.** In the Parowan ceramic study, recalculating Mahalanobis distances after removing low‑probability samples resulted in unexpectedly low membership probabilities for remaining samples, revealing that apparently “tight” clusters could be statistically weak.[C4][C5] Students should avoid assuming that visually coherent dendrogram clusters are necessarily robust.

2. **Violating statistical assumptions for Mahalanobis distance.** The turquoise and Olivella PIXE study notes that Mahalanobis distance requires at least two more samples than measured variables; this constraint forced the removal of Mn and limited analysis to a two‑cluster solution.[C7] Using the metric outside these constraints or with overly high dimensionality can yield misleading probabilities.

3. **Relying on a single principal component as a proxy variable.** In the same PIXE study, the author explicitly chose not to use the first principal component as the sole variable in Mahalanobis distance calculations, expressing concern about this oversimplification and instead focusing on cluster analyses.[C7] Course projects should emphasize that dimensionality reduction (e.g., PCA) is not a cure‑all and that subsequent statistical steps must be justified.

4. **Under‑documenting methodology.** The Calakmul network study explicitly divides its methodology into sections for GIS and SNA, with clear overviews and an outline of the centrality measures used.[C8] If students skip this structured methodological documentation, it becomes difficult to assess or reproduce their analyses.

5. **Ignoring the need for comparative baselines in network analysis.** The Mississippian multilayer network study uses randomization via Erdős–Rényi random graphs (5,000 iterations) to create distributions of network statistics and then compares observed values against these distributions.[C10] Course projects that only report raw network metrics without any reference distribution cannot easily distinguish meaningful structure from what might arise by chance.

## Exercises

1. **Designing a GIS‑to‑Network Pipeline**  
   Using the Calakmul methodology as a guide, sketch a project plan (1–2 pages) for a hypothetical region. Your plan should:
   - Define a regional connectivity question (e.g., movement or site interaction).[C8]  
   - Specify which GIS analyses you would run to detect potential connections among sites.[C8]  
   - Describe how you would translate GIS outputs into a network and which centrality measures you would use to interpret that network.[C8][C9]  

2. **Cluster Analysis Critique**  
   Based on the Parowan ceramic and turquoise/Olivella PIXE examples, write a short critique (1–2 pages) that:
   - Compares how Ward’s and average link cluster analyses are used in these studies.[C1][C2][C3][C4][C5]  
   - Explains the role of Mahalanobis distance in evaluating clusters and how its use was limited by data constraints.[C1][C5][C7]  
   - Proposes at least two guidelines for deciding when to trust cluster‑derived groups in your own projects.[C4][C5][C7]  

3. **Randomization in Network Evaluation**  
   Using the Mississippian multilayer network study as inspiration, outline how you would apply network randomization to a simple material culture network:
   - Describe the observed network (e.g., nodes as sites, edges as shared ceramic styles).[C10]  
   - Specify which network statistic you would randomize and how many Erdős–Rényi random graphs you would generate.[C10]  
   - Explain how you would interpret the position of your observed statistic relative to the random distribution.[C10]  

4. **From PCA to Network Attributes**  
   Using the PCA plots of Parowan ceramics as an example, explain how principal component scores or cluster assignments could be turned into node attributes in a network of sites or assemblages.[C6] Discuss how such attributes could be used in interpreting centrality measures in later network analysis.[C8][C9]

## Key Takeaways

- GIS has become an indispensable part of archaeological methodology and is used to derive spatial relationships that can be translated into network models, as illustrated in the Calakmul region study.[C8]  
- Network science in archaeology focuses on representing various kinds of archaeological relations—including movement networks, material culture networks, and spatial proximity networks—as networks that can be analyzed with formal tools and centrality measures.[C9]  
- Multivariate methods such as PCA and hierarchical clustering (Ward’s and average link) are central to compositional and ceramic studies, as seen in Parowan pottery and turquoise/Olivella PIXE analyses; they help identify groups, outliers, and structure in complex datasets.[C1][C2][C3][C5][C6][C7]  
- Mahalanobis distance is a powerful but constrained tool for evaluating cluster strength and group membership probabilities; it requires adequate sample‑to‑variable ratios and careful interpretation, as both ceramic case studies emphasize.[C1][C5][C7]  
- Network evaluation in archaeology benefits from randomization: comparing observed network statistics to distributions from random graphs (e.g., Erdős–Rényi) allows researchers to assess whether observed structures in ceramic economic networks and multilayer networks are likely to be meaningful.[C10]  
- Well‑designed student projects in computational archaeology should emphasize clear research questions, structured methodological documentation (GIS, multivariate statistics, SNA), explicit evaluation of analytical choices, and awareness of common pitfalls in clustering and network analysis.[C4][C5][C7][C8][C9][C10]

## Citation Map

- C1: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C2: citekey=Jardine2007-br; title=Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond; year=2007; doi=None
- C3: citekey=Jardine2007-br; title=Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond; year=2007; doi=None
- C4: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C5: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C6: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C7: citekey=Jardine2007-br; title=Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond; year=2007; doi=None
- C8: citekey=Andrew_undated-xe; title=Developing a Network Model for the Calakmul Region; year=None; doi=None
- C9: citekey=Brughmans2023-uj; title=Network Science in Archaeology; year=2023; doi=None
- C10: citekey=Upton2019-yg; title=Multilayer Network Relationships and Culture Contact in Mississippian West-central Illinois, A.D. 1200 - 1450; year=2019; doi=None