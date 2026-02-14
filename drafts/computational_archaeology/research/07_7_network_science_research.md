# Research for 7. Network Science for Past Societies

- Date: 2026-02-14
- Question: Write a concise but substantive college-level textbook chapter in markdown for '7. Network Science for Past Societies'. Audience: undergraduate computer science students learning computational archaeology. Include sections: Learning Objectives, Core Ideas, Worked Workflow, Case Study, Common Mistakes, Exercises, Key Takeaways. Focus: Cover graph representations, centrality, community structure, diffusion, temporal networks, and archaeological interpretation caveats. Use only grounded RAG evidence and cite claims with [C#].
- Search query used: network science past societies computational archaeology graph representations centrality community structure diffusion temporal networks archaeological interpretation caveats undergraduate textbook chapter
- Model: gpt-5.1
- RAG results: 10

## Synthesized Draft

# 7. Network Science for Past Societies

## Learning Objectives

By the end of this chapter, you should be able to:

- Describe what network data are and how they are represented in formats such as edge lists and adjacency matrices in archaeological research.[C2]  
- Distinguish common network types used in archaeology, including directed, weighted, similarity, and two‑mode networks.[C2]  
- Explain core centrality measures (degree, eigenvector, betweenness) and why their stability matters for archaeological interpretation.[C5][C7]  
- Recognize how network science is being applied to material culture, movement, spatial proximity, visibility, and publication networks in archaeology.[C2][C6][C8][C9]  
- Understand the idea of longitudinal (temporal) network data in archaeological contexts.[C2]  
- Identify key methodological challenges, including incomplete data, tentative network boundaries, and interpretation caveats when projecting from sampled to “real” past networks.[C5][C7][C8]  

---

## Core Ideas

### Networks and Network Science in Archaeology

Network science in archaeology draws on graph theory, social network analysis, and complexity science to study relationships among entities (sites, people, artifacts, places) and how these relationships structure past societies.[C8][C9] Archaeological network research is methodologically and theoretically diverse and has expanded rapidly in recent years.[C8][C9]

Network science is positioned within archaeology as a way to explore questions about how network structure and positions relate to attributes and outcomes at multiple social scales.[C8] Archaeologists use formal network analyses to investigate long‑term dynamics of social networks and their relationships to culture.[C8][C9]

### Network Data and Representations

Network data describe relationships (edges) among entities (nodes).[C2] Archaeological network data can be stored and exchanged in multiple graph‑theoretic formats:[C2]

- **Edge list**: a list of pairs (or tuples) of nodes indicating which nodes are connected.[C2]  
- **Adjacency list**: for each node, a list of nodes to which it is connected.[C2]  
- **Adjacency matrix**: a matrix where rows and columns correspond to nodes and entries encode whether (and possibly how strongly) they are connected.[C2]  
- **Incidence matrix**: a matrix linking nodes to edges, useful particularly for more complex or bipartite structures.[C2]  

Additional node and edge attributes (e.g., site type, ceramic counts, tie strength) can be associated with these structures.[C2]

### Types of Networks

Archaeological research uses a variety of network types:[C2]

- **Simple networks**: undirected, unweighted graphs where edges indicate the presence or absence of a relationship.[C2]  
- **Directed networks**: edges have direction, indicating asymmetric relationships (e.g., flow from one node to another).[C2]  
- **Signed and weighted networks**: edges can be assigned weights (strengths) or signs (e.g., positive/negative relationships).[C2]  
- **Two‑mode (affiliation) networks**: link two distinct classes of nodes, such as sites and artifact types or sites and ceramic styles.[C2]  
- **Similarity networks**: edges represent similarity in attributes (e.g., similarity of ceramic assemblages between sites).[C2]  
- **Ego‑networks**: focus on one node (ego) and its immediate connections.[C2]  
- **Multilayer networks**: combine several types of relationships or interaction modes in a joint framework.[C2]  

Archaeologists also distinguish **longitudinal (temporal) network data**, which track changes in network structure over time.[C2]

### Archaeological Network Domains

Network science has been applied across multiple archaeological domains:[C2][C6]

- **Material culture networks**: relationships defined by similarities or connections in artifact or ceramic assemblages.[C2]  
- **Movement networks**: models of routes or flows, such as travel or exchange paths.[C2]  
- **Spatial proximity networks**: connections based on geographic closeness between sites or features.[C2]  
- **Visibility networks**: networks created from lines of sight among locations.[C2]  
- **Archaeological publication networks**: networks of publications, authors, or citations used to study trends in archaeological research.[C2]  

This breadth reflects the “many and varied” applications of network science in archaeology.[C2][C8][C9]

### Centrality and Its Stability

Centrality measures quantify aspects of how “important” or “central” nodes are within a network.[C5][C7] Archaeological work has emphasized three commonly used measures:[C5][C7]

- **Degree centrality**: based on the number of ties a node has.[C5][C7]  
- **Eigenvector centrality**: considers both the number and the centrality of a node’s neighbors.[C5][C7]  
- **Betweenness centrality**: measures how often a node lies on paths between other nodes.[C5][C7]  

A key methodological issue in archaeology is that many networks are constructed from incomplete or imperfect data: network boundaries are often tentative and nodes or sites can vary considerably in their attributes and assemblages.[C5][C7] To address this, archaeological research has used bootstrap procedures to evaluate how sampling affects the stability of these centrality measures.[C5][C7]

The goal is to determine whether the observed archaeological network graph can be treated as a sample of a larger, inaccessible network that includes unknown or missing sites.[C5][C7] If centrality values remain stable across many resampled networks, researchers argue that interpretations drawn from the observed network may be cautiously projected to a broader, “real” network.[C5][C7]

### Temporal Networks

Longitudinal network data capture how networks evolve over time.[C2] In archaeology, this often means reconstructing networks at successive temporal slices based on dated materials or stratigraphic contexts and then comparing structures across those slices.[C1][C2][C3][C4][C10] The explicit discussion of longitudinal network data in archaeological network manuals highlights the importance of integrating time into network analyses.[C2]

---

## Worked Workflow: From Archaeological Data to Network Analysis

This section outlines a generic workflow using concepts and practices described in archaeological network research.[C2][C5][C7][C8][C9]

### 1. Define Research Questions and Network Scope

Archaeologists begin by formulating questions about past relationships, such as those tying together sites via similarities in material culture, movement pathways, or spatial relationships.[C2][C6][C8] The spatial and temporal scope of the network must be specified, even though boundaries are often tentative.[C5][C7]

### 2. Assemble and Structure Network Data

Archaeological datasets can include site‑level provenience and assemblage composition (e.g., counts of ceramic types by structure or stratum), as seen in tabulations of structures, strata, and ceramic categories in regional studies.[C3][C4][C10] These data can be transformed into:

- **Nodes**: sites, structures, or other entities (e.g., DANGER CAVE, HOGUP CAVE, individual structures in villages).[C3][C4][C10]  
- **Edges**: relationships such as similarities in assemblage composition or co‑occurrence of artifact types.[C2][C3][C4][C10]  

Data are encoded in network formats such as edge lists or adjacency matrices with associated node and edge attributes.[C2]

### 3. Choose Network Type and Representation

Based on the question and data structure, archaeologists select:[C2]

- A simple, directed, weighted, similarity, two‑mode, or multilayer representation.  
- Appropriate data formats (edge list, adjacency list, adjacency matrix, or incidence matrix) and attribute tables to preserve relevant information.[C2]  

### 4. Exploratory Network Analysis

Exploratory network analysis involves using a suite of methods to characterize network structure and node positions.[C2] Common steps include:

- Visualizing network graphs, sometimes placing nodes in geographic coordinates to compare abstract structure with spatial layout.[C7]  
- Calculating centrality measures (degree, eigenvector, betweenness) to identify structurally prominent nodes.[C5][C7]  
- Examining distributions of ties, clustering, and other global or local patterns as part of exploratory analysis.[C2]  

### 5. Assess Centrality Stability and Sampling Issues

Given incomplete archaeological data, archaeologists employ resampling (bootstrap) procedures to evaluate how sampling uncertainty influences centrality measures.[C5][C7] By repeatedly sampling subsets of nodes or edges and recalculating centralities, they assess whether node rankings remain stable under different sampled networks.[C5][C7]

If degree, eigenvector, and betweenness centralities are stable across a range of sampled networks, interpretations of the archaeological network can more plausibly be extended to an inferred larger network.[C5][C7] If not, centrality‑based interpretations are treated with greater caution.[C5][C7]

### 6. Contextual Interpretation

Network structures and metrics are then interpreted in light of archaeological theory and contextual evidence.[C8][C9] Researchers consider:

- How positions and structures might reflect patterns of interaction, movement, or shared material culture.[C2][C6][C8]  
- How temporal information (e.g., stratified contexts, dated materials) informs changes in networks over time.[C1][C2][C3][C4][C10]  
- To what extent formal network results address broader debates on network theory, culture, and long‑term social dynamics.[C8][C9]  

Throughout, archaeologists remain aware of limitations arising from data quality, sampling, and the abstraction of complex social phenomena into graph models.[C5][C7][C8][C9]

---

## Case Study: Centrality and Sampling in Hunter‑Gatherer Networks

Research on hunter‑gatherer archaeological data has explored methodological problems and potential solutions in network analysis.[C5][C7] In this work, networks were constructed for archaeological cultures (e.g., Epi‑Jomon and Okhotsk), with nodes representing sites and edges representing inferred relationships among them.[C7]

Visualizations show network graphs both in abstract layout and with nodes placed in geographic position.[C7] Node size is scaled in proportion to degree centrality, making more highly connected sites visually prominent.[C7]

A central aim of this case study is to understand how incomplete sampling and uncertain network boundaries affect centrality estimates.[C5][C7] Archaeological networks are considered imperfect because:

- Network boundaries are often tentative.  
- Sites vary considerably in their attributes and assemblages.[C5][C7]  

To address this, the study applies a **bootstrap procedure**: many resampled versions of the network are generated, and three centrality measures—degree, eigenvector, and betweenness—are recalculated for each sample.[C5][C7] This method follows broader research on centrality stability and is used to evaluate how robust archaeological centrality measures are to missing data.[C5][C7]

If measurements for key nodes remain relatively stable across bootstrapped samples, then it becomes more reasonable to conceptualize the observed archaeological network as a **sample of a larger, inaccessible network** that includes unknown or missing sites.[C5][C7] Under these circumstances, interpretations drawn from the archaeological network can be tentatively projected to that larger real‑world network.[C5][C7]

This case study illustrates:

- How centrality is operationalized and visualized in archaeological networks.[C5][C7]  
- Why sampling and boundary issues are especially critical in archaeology.[C5][C7]  
- How statistical resampling can partially address these concerns and provide a basis for evaluating the reliability of network interpretations.[C5][C7]  

---

## Common Mistakes and Caveats in Archaeological Network Interpretation

Archaeological network science faces a set of recurring challenges and potential pitfalls:

1. **Over‑confidence in Incomplete Networks**  
   Archaeological networks are often based on imperfect samples with tentative boundaries and substantial variability among sites.[C5][C7] Treating such networks as complete can lead to over‑confident claims about central or peripheral nodes.

2. **Ignoring Centrality Stability**  
   Without evaluating stability through procedures such as bootstrapping, centrality measures may be sensitive to which sites or ties happen to be preserved or sampled.[C5][C7] Failing to assess this can produce misleading interpretations of node importance.

3. **Uncritical Projection to “Real” Networks**  
   Projecting results from a sampled archaeological network to an inferred larger “real” network is only justified when centrality and other measures show reasonable stability across alternative sampled graphs.[C5][C7] Ignoring this condition weakens inferential claims.

4. **Neglecting Temporal Dimensions**  
   Network manuals emphasize longitudinal data as a distinct category, yet archaeological studies can sometimes treat networks as static when temporal information actually exists.[C2] This can obscure changes in relationships over time.

5. **Conflating Different Network Types and Meanings**  
   Archaeological practice distinguishes material culture, movement, spatial proximity, visibility, and publication networks, each encoding different kinds of relationships.[C2][C6][C8][C9] Interpreting these networks as if they all represent the same underlying social processes can be problematic.

6. **Insufficient Integration with Theory and Context**  
   Although network science in archaeology engages with broader discussions on network theory, culture, and social dynamics, there remain “daunting challenges” in formal exploration.[C8] Overly technical analyses without theoretical grounding can limit interpretive value.

---

## Exercises

1. **Network Data Formats**  
   Given a hypothetical set of sites and inferred connections among them, represent the same network as:  
   a) an edge list,  
   b) an adjacency list, and  
   c) an adjacency matrix.  
   Discuss how each format might facilitate different analytical operations, drawing on distinctions among formats described for archaeological network data.[C2]

2. **Network Types in Archaeological Contexts**  
   For each of the following research focuses, identify which network type (simple, directed, weighted, similarity, two‑mode, multilayer) and which domain (material culture, movement, spatial proximity, visibility, publication) would be most appropriate, explaining your choice based on the typology provided in network science manuals:[C2][C6][C8][C9]  
   - Similarity in ceramic technology across multiple village sites.  
   - Potential travel routes among settlements in a region.  
   - Lines of sight between hilltop structures.

3. **Centrality Stability Thought Experiment**  
   Consider a small archaeological network where some peripheral sites may have been lost to erosion. Using the description of bootstrap procedures and centrality stability, outline a strategy to test whether degree and betweenness centrality rankings for major sites are robust.[C5][C7] Specify what data you would resample and how you would interpret stable vs. unstable results.

4. **Longitudinal Network Design**  
   Using the idea of longitudinal network data and the existence of stratified or temporally differentiated assemblages in regional studies, design a conceptual plan for constructing at least two time‑sliced networks for a region.[C1][C2][C3][C4][C10] Describe how you would compare these temporal networks to explore changes in interaction or similarity.

5. **Critical Evaluation of Network Boundaries**  
   Drawing on the recognition that network boundaries are often tentative and that sites vary substantially in their assemblages, develop a short critique (1–2 paragraphs) of a hypothetical study that claims to have completely mapped all interaction in a region with a single static network.[C5][C7] Identify at least three specific concerns related to sampling, boundaries, and interpretation.

---

## Key Takeaways

- Network science in archaeology uses formal models from graph theory, social network analysis, and complexity science to study relationships and structures in past societies, contributing to debates on network theory, culture, and long‑term social dynamics.[C8][C9]  
- Archaeological networks rely on structured data representations such as edge lists, adjacency lists, adjacency matrices, and incidence matrices, with rich node and edge attributes.[C2]  
- Multiple network types—simple, directed, weighted, similarity, two‑mode, ego, multilayer, and longitudinal—are distinguished and applied across material culture, movement, spatial proximity, visibility, and publication domains.[C2][C6][C8][C9]  
- Centrality measures (degree, eigenvector, betweenness) are widely used but must be assessed for stability via resampling methods because archaeological networks are often incomplete, with tentative boundaries and heterogeneous sites.[C5][C7]  
- When centrality metrics remain stable across sampled networks, interpretations about the structure and key nodes of an archaeological network can be more plausibly extended to a larger, inaccessible “real” network that includes unknown sites.[C5][C7]  
- Longitudinal (temporal) network data and explicit consideration of time are important for understanding how networks and social relationships change in the archaeological record.[C1][C2][C3][C4][C10]  
- Successful archaeological network analysis requires attention to data limitations, explicit handling of sampling and boundaries, and integration with broader theoretical and contextual interpretations.[C5][C7][C8][C9]

## Citation Map

- C1: citekey=McCloskey2018-ir; title=Tree-ring chronological analysis of Ancestral Puebloan transitions in the Flagstaff Area; year=2018; doi=None
- C2: citekey=Brughmans2023-uj; title=Network Science in Archaeology; year=2023; doi=None
- C3: citekey=McDonald1994-cg; title=A Spatial and Temporal Examination of Prehistoric Interaction in the Eastern Great Basin and on the Northern Colorado Plateau; year=1994; doi=None
- C4: citekey=McDonald1994-cg; title=A Spatial and Temporal Examination of Prehistoric Interaction in the Eastern Great Basin and on the Northern Colorado Plateau; year=1994; doi=None
- C5: citekey=Gjesfjeld2015-hw; title=Network Analysis of Archaeological Data from Hunter-Gatherers: Methodological Problems and Potential Solutions; year=2015; doi=10.1007/s10816-014-9232-9
- C6: citekey=Brughmans2023-uj; title=Network Science in Archaeology; year=2023; doi=None
- C7: citekey=Gjesfjeld2015-hw; title=Network Analysis of Archaeological Data from Hunter-Gatherers: Methodological Problems and Potential Solutions; year=2015; doi=10.1007/s10816-014-9232-9
- C8: citekey=Peeples2019-ay; title=Finding a Place for Networks in Archaeology; year=2019; doi=10.1007/s10814-019-09127-8
- C9: citekey=Peeples2024-er; title=Introduction; year=2024; doi=None
- C10: citekey=McDonald1994-cg; title=A Spatial and Temporal Examination of Prehistoric Interaction in the Eastern Great Basin and on the Northern Colorado Plateau; year=1994; doi=None