# 03 Methods Toolkit

- Date: 2026-02-14
- Question: Summarize the core computational methods in archaeology for undergraduates: databases, GIS, network analysis, simulation, and machine learning, with practical examples.
- Search query used: computational archaeology databases GIS network analysis simulation machine learning core methods in archaeology for undergraduates practical examples databases GIS spatial analysis social network analysis agent based models simulations predictive modeling machine learning classification clustering
- Model: gpt-5.1
- RAG results count: 12

## Synthesized Notes

The context you provided does not contain information about archaeological databases, GIS, simulation, or machine learning, and only gives partial technical detail for network analysis and clustering workflows. Because I must rely strictly on the supplied context, I cannot produce a complete, accurate summary of “the core computational methods in archaeology” across all those topics.

Within the limits of the context, I can briefly summarize what is actually covered:

1. **Network analysis in archaeology**

   - Network approaches in archaeology draw on graph theory, social network analysis, and complexity science to study relationships among individuals and groups and their outcomes at multiple social scales. [C8]
   - The focus is on actors (e.g., individuals, communities, nations) represented as nodes, and their ties (e.g., communication, economic transactions, kinship) represented as edges. [C2]
   - Social network analysis compares actors based on their relationships rather than just their attributes, treating ties as channels for flows of material and immaterial resources, which both enable and constrain behavior. [C2]
   - At the level of a whole network, key descriptive measures include:
     - number of nodes and links  
     - maximum distance between two nodes (the “diameter”) measured as the number of links on the shortest path  
     - average path length between nodes. [C1]
   - Network methods in archaeology have expanded rapidly and are used to investigate how network structure and positions relate to material culture, culture, and long‑term social dynamics. [C8]

2. **Cluster analysis and related multivariate methods (as seen in an archaeological case study)**

   - In a study of Mississippian sites, chemical compositional data (summarized by principal components) are clustered using methods such as k‑means and k‑medoids to define compositional “cores” and subgroups (e.g., Core A, B, C; Core A1, A2). [C6] [C7] [C11] [C12]
   - The workflow includes:
     - Performing principal components analysis (PCA) on variables, retaining principal components that explain a large proportion of variance (e.g., PCs 1–12 accounting for 90% of variability). [C6]
     - Running k‑means clustering on PCA scores, then computing group membership probabilities for each cluster solution. [C6]
     - Splitting data into lists by cluster assignment, recombining them, and generating tables of membership probabilities by sample and core group (e.g., membership probabilities for Core A, Core B, Core C for each sample). [C6] [C11]
     - Using k‑medoids clustering to refine groups (e.g., Core A1 vs Core A2), then checking that a second iteration yields 100% of samples staying in their original cluster, which is interpreted as evidence of a strong cluster solution. [C7]
     - Visualizing group structure by plotting samples on principal component axes (e.g., PC1 vs PC2), colored and shaped by group (Core A, Core A1, Core A2) and adding confidence ellipses. [C7]

Because there is no information in the provided context on archaeological databases, GIS, simulation (including agent‑based modeling in archaeology), or machine learning applications in archaeology, I cannot summarize those methods or give archaeological examples of them without going beyond the supplied sources.

## Used Citations

- C1: Networks as Proxies: a relational Approach towards Economic Complexity in the Pre-Modern Period (2015); Authors: Preiser-Kapeller J; Citekey: Preiser-Kapeller2015-nv; DOI: ; Source: pdfs/preiser-kapeller2015-NetworksAsProxies-ARelationalApproachTowardsEconomicComplexityInPre-modernPeriod.pdf
- C2: Evaluating Adaptive Network Strategies with Geochemical Sourcing Data: A Case Study from the Kuril Islands (2013); Authors: Gjesfjeld E, Colby Phillips S; Citekey: Gjesfjeld2013-iv; DOI: ; Source: pdfs/gjesfjeld2013-EvaluatingAdaptiveNetworkStrategiesGeochemicalSourcingData-ACaseStudyKurilIslands.pdf
- C6: Multilayer Network Relationships and Culture Contact in Mississippian West-central Illinois, A.D. 1200 - 1450 (2019); Authors: Upton AJ; Citekey: Upton2019-yg; DOI: ; Source: pdfs/upton2019-MultilayerNetworkRelationshipsCultureContactInMississippianWest-centralIllinois,A.d.1200-1450.pdf
- C7: Multilayer Network Relationships and Culture Contact in Mississippian West-central Illinois, A.D. 1200 - 1450 (2019); Authors: Upton AJ; Citekey: Upton2019-yg; DOI: ; Source: pdfs/upton2019-MultilayerNetworkRelationshipsCultureContactInMississippianWest-centralIllinois,A.d.1200-1450.pdf
- C8: Finding a Place for Networks in Archaeology (2019); Authors: Peeples MA; Citekey: Peeples2019-ay; DOI: 10.1007/s10814-019-09127-8; Source: pdfs/peeples2019-FindingAPlaceNetworksInArchaeology.pdf
- C11: Multilayer Network Relationships and Culture Contact in Mississippian West-central Illinois, A.D. 1200 - 1450 (2019); Authors: Upton AJ; Citekey: Upton2019-yg; DOI: ; Source: pdfs/upton2019-MultilayerNetworkRelationshipsCultureContactInMississippianWest-centralIllinois,A.d.1200-1450.pdf
- C12: Multilayer Network Relationships and Culture Contact in Mississippian West-central Illinois, A.D. 1200 - 1450 (2019); Authors: Upton AJ; Citekey: Upton2019-yg; DOI: ; Source: pdfs/upton2019-MultilayerNetworkRelationshipsCultureContactInMississippianWest-centralIllinois,A.d.1200-1450.pdf