# Research for 5. Machine Learning in Archaeology

- Date: 2026-02-14
- Question: Write a concise but substantive college-level textbook chapter in markdown for '5. Machine Learning in Archaeology'. Audience: undergraduate computer science students learning computational archaeology. Include sections: Learning Objectives, Core Ideas, Worked Workflow, Case Study, Common Mistakes, Exercises, Key Takeaways. Focus: Focus on supervised/unsupervised ML, feature engineering, evaluation, bias, explainability, and archaeological use-cases. Use only grounded RAG evidence and cite claims with [C#].
- Search query used: machine learning archaeology computational archaeology supervised learning unsupervised learning feature engineering model evaluation bias explainability archaeological case study RAG retrieval grounded evidence
- Model: gpt-5.1
- RAG results: 10

## Synthesized Draft

## 5. Machine Learning in Archaeology

### Learning Objectives

By the end of this chapter, you should be able to:

- Distinguish supervised, unsupervised, and exploratory multivariate methods in archaeological datasets, using cluster analysis and principal components as exemplars.[C1][C2][C3][C5][C6][C10]  
- Describe feature engineering steps such as normalization and log transformation for geochemical data and explain why they matter.[C2][C3]  
- Interpret cluster-analysis outputs (dendrograms, distance measures) and basic group-evaluation metrics such as Mahalanobis distance in archaeological studies.[C1][C2][C3][C5][C6][C10]  
- Recognize common sources of bias and data-quality problems in archaeological machine-learning workflows, including sample preparation issues and mixed provenance.[C5][C6]  
- Critically assess how clustering and related methods have been used to study pottery and ornament exchange networks.[C1][C2][C3][C5][C6][C10]  

---

### Core Ideas

#### 5.1 Archaeological Data and Machine Learning

Archaeological projects often generate large, multivariate datasets, such as:

- Chemical compositions of pottery sherds.[C1][C5][C6][C10]  
- PIXE (Particle-Induced X-ray Emission) elemental/oxide measurements of ornaments.[C2][C3]  

These datasets are characterized by many variables (e.g., oxides, elements) per sample and are typically analyzed with multivariate statistical/machine-learning tools such as principal components analysis (PCA) and cluster analysis.[C1][C2][C3][C5][C6][C10]

#### 5.2 Supervised vs. Unsupervised Learning in Context

- **Unsupervised learning** aims to discover structure without pre-labeled classes. Archaeological examples include:  
  - Cluster analysis with Ward’s algorithm applied to pottery compositions to identify compositional groups.[C1][C5][C6][C10]  
  - Average-link cluster analysis on normalized and log-transformed oxide data from PIXE measurements of ornaments.[C2][C3]  

  In these cases, samples (e.g., sherds, ornaments) are clustered based on similarity in geochemical or oxide feature space, with distances visualized in dendrograms.[C1][C2][C3][C5][C6][C10]

- **Supervised learning** would require labeled training data (e.g., known production sources or types) and models that predict those labels; the provided contexts focus instead on evaluation and interpretation of groups suggested by unsupervised methods rather than on predictive classification per se.[C1][C2][C3][C5][C6][C10]

#### 5.3 Feature Engineering for Archaeological Data

Feature engineering shapes how algorithms “see” archaeological materials. Examples in the context include:

- **Normalization of oxides** in the PIXE database before cluster analysis, which standardizes compositional variables and is explicitly mentioned as the basis for Ward’s and average-link clustering results.[C2][C3]  
- **Log transformation of normalized oxides** to create an alternative feature representation, again followed by Ward’s and average-link cluster analysis.[C3]  

These transformations change the scale and distribution of features (e.g., oxides) and can alter the resulting cluster structure and distances in dendrograms.[C2][C3]

For pottery, principal component plots are constructed from geochemical measurements (with bulk rock omitted in the example), providing new orthogonal features (principal components) that summarize variation across sites and types of ceramics.[C10]

#### 5.4 Evaluation, Distances, and Group Strength

Archaeological cluster analysis often needs a quantitative assessment of group quality:

- **Ward’s algorithm and average-link clustering** output groupings visualized as dendrograms with a distance axis.[C1][C2][C3][C5][C6][C10]  
- **Mahalanobis distance** is used to evaluate the strength of proposed groups in the pottery study. After an initial clustering, Mahalanobis distances and corresponding probabilities of group membership are computed for each sample.[C1][C5]  

  The researcher then:

  - Eliminated samples with extremely low probabilities of belonging to any group (P < 0.1) to attempt “tighter” groups.[C5]  
  - Recalculated Mahalanobis distances and probabilities, observing that probabilities did not increase and sometimes decreased sharply even for samples that had previously shown high probabilities.[C5][C6]  

This illustrates that group evaluation via Mahalanobis distance can reveal instability or poor fit of clusters, prompting re-examination of both data and assumptions.[C5][C6]

#### 5.5 Bias, Data Quality, and Archaeological Interpretation

The unexpected behavior of Mahalanobis probabilities in the pottery analysis led to explicit consideration of possible causes:

- The “near-total” digestion of samples might have been inadequate, potentially obscuring chemically distinct compositional groups.[C6]  
- Sherds in the sample may have been constructed from multiple clay sources or temper materials, creating mixed or overlapping compositions that do not align cleanly with single-group assumptions.[C6]  
- As a result, stable and clearly separated compositional groups may not be present or may be more complex than simple clustering suggests.[C5][C6]  

These points highlight that:

- Data-preparation choices (e.g., digestion protocol) constitute a major potential bias in machine-learning workflows for archaeological materials.[C6]  
- Material culture practices (e.g., mixing clays) can violate assumptions of homogeneity within clusters, complicating both unsupervised grouping and any downstream supervised modeling based on those groups.[C6]

---

### Worked Workflow: Cluster Analysis of Pottery Compositions

This section reconstructs a typical computational workflow using the Parowan pottery study as a guide.[C1][C5][C6][C10]

#### Step 1: Data Collection and Preprocessing

- Collect geochemical measurements for pottery sherds and related samples (e.g., clays) from multiple sites and types.[C10]  
- Exclude certain components such as bulk rock from the PCA, as explicitly done in the principal component plots (bulk rock omitted).[C10]  

#### Step 2: Exploratory Multivariate Analysis

- Perform PCA and plot samples on principal components (e.g., PC1 vs. PC2, PC1 vs. PC3) by site and type, allowing visual assessment of clustering or overlap among Parowan Valley ceramics and other groups.[C10]  

  These plots help to:

  - Detect broad compositional trends or separations.[C10]  
  - Identify outliers before formal clustering.[C10]

#### Step 3: Unsupervised Grouping (Cluster Analysis)

- Apply **Ward’s algorithm** to the pottery dataset, generating a dendrogram with cases (sherds) and distances along the horizontal axis.[C1][C5]  
- Apply **average-link clustering** as an alternative method, also visualized by a dendrogram.[C6][C10]  

Comparing these algorithms allows assessment of how robust the clustering is to linkage criteria.[C1][C2][C3][C5][C6][C10]

#### Step 4: Group Evaluation with Mahalanobis Distance

- Use the initial Ward’s clusters as provisional compositional groups.[C1][C5]  
- Calculate Mahalanobis distances and probabilities of group membership for each sample.[C1][C5]  
- Remove samples with extremely low group-membership probabilities (P < 0.1) as potential outliers and recompute distances and probabilities for the reduced dataset.[C5]  

- Interpret the unexpected result: probabilities of group membership fail to increase, and some previously well-fitting samples now have very low probabilities.[C5][C6]  

This reveals that even after outlier removal, the group structure may not be statistically coherent under the assumed multivariate model.[C5][C6]

#### Step 5: Diagnose Data and Model Issues

- Consider that digestion might not have been sufficiently complete, leaving compositional signals blurred.[C6]  
- Consider that sherds may incorporate multiple sources of clay or temper, creating inherently mixed compositions.[C6]  

The workflow thus loops back to laboratory preparation, sampling strategy, and archaeological expectations, rather than treating the clustering output as final.[C5][C6]

---

### Case Study: Turquoise and Olivella Ornaments (PIXE Database)

The Fremont ornament study provides a focused example of feature engineering and unsupervised learning on PIXE data.[C2][C3]

#### Data and Features

- The dataset consists of a PIXE database measured as oxides for turquoise and Olivella ornaments from the Parowan Valley and beyond.[C2]  
- Oxides are used as quantitative features that describe the chemical composition of each ornament.[C2][C3]  

#### Feature Engineering

Two main preprocessing strategies are explicitly documented:

1. **Normalized oxides**  
   - Cluster analysis with Ward’s algorithm on the PIXE database as normalized oxides produces a dendrogram (Figure 11) with cases 1–38 and distances.[C2]  
   - Average-link cluster analysis on the same normalized oxides produces a second dendrogram (Figure 12), enabling comparison of linkage methods.[C2][C3]  

2. **Log-transformed normalized oxides**  
   - Ward’s cluster analysis on the PIXE database as log-transformed normalized oxides produces another dendrogram (Figure 13).[C3]  
   - Average-link clustering on these log-transformed normalized oxides generates yet another dendrogram (Figure 14) with distances up to about 0.7.[C3]  

Thus, the same physical artifacts (ornaments) are analyzed in multiple feature spaces: raw normalized oxides and log-transformed normalized oxides.[C2][C3]

#### Interpretation and Archaeological Use

By comparing:

- Ward vs. average-link results on normalized oxides, and  
- Ward vs. average-link results on log-transformed normalized oxides,[C2][C3]  

the researcher can assess:

- How sensitive inferred compositional groups (and thus potential exchange or distribution patterns) are to choices in feature transformation and clustering algorithm.[C2][C3]  

The case study demonstrates that:

- Feature engineering (normalization, log transformation) and clustering choices meaningfully shape the groupings of ornaments, which in turn inform hypotheses about exchange and distribution networks.[C2][C3]

---

### Common Mistakes

1. **Treating Clusters as Ground Truth**

   In both pottery and ornament studies, clusters from Ward’s or average-link analyses are provisional and must be evaluated with additional metrics like Mahalanobis distance.[C1][C2][C3][C5][C6][C10]  
   - The pottery case shows that initially plausible groups can fail under probabilistic evaluation, indicating that naïve acceptance of cluster structure would be misleading.[C5][C6]

2. **Ignoring Data Preparation Artifacts**

   The pottery analysis explicitly identifies inadequate “near-total” digestion as a possible reason for obscure compositional groups.[C6]  
   - Failing to consider laboratory preparation can lead to misinterpreting noisy or blended features as archaeologically meaningful structure.[C6]

3. **Assuming Homogeneous Provenance**

   Mixed construction of sherds from multiple clay sources is identified as a plausible explanation for unstable grouping.[C6]  
   - Assuming single-source homogeneity when materials are actually composite can distort both clustering and any subsequent supervised learning built on those groups.[C6]

4. **Overlooking the Impact of Transformations**

   The ornament study’s use of normalized vs. log-transformed normalized oxides demonstrates that different feature transformations lead to different cluster structures.[C2][C3]  
   - Ignoring how normalization and log transformation affect distances can lead to uncritical acceptance of whichever dendrogram happens to be inspected first.[C2][C3]

---

### Exercises

1. **PCA Interpretation (Conceptual)**  
   Based on the description of PC1 vs. PC2 and PC1 vs. PC3 plots for Parowan Valley and other ceramic types (bulk rock omitted), explain how you would use such plots to:  
   - Identify potential compositional groups, and  
   - Select candidate outliers for further scrutiny.[C10]

2. **Cluster-Algorithm Comparison**  
   Using the descriptions of Ward’s and average-link cluster analyses on normalized oxides in the PIXE database, discuss how you would decide whether the two methods support the same group structure or suggest alternative interpretations of ornament exchange.[C2][C3]

3. **Feature-Transformation Thought Experiment**  
   Compare the potential effects of clustering on normalized oxides vs. log-transformed normalized oxides for the same PIXE dataset. Under what conditions might log transformation be preferable for archaeological interpretation?[C2][C3]

4. **Diagnosing Group Instability**  
   In the pottery study, removal of low-probability samples (P < 0.1) does not improve, and sometimes worsens, group membership probabilities under Mahalanobis distance.[C5][C6]  
   - Propose a sequence of next steps (methodological or laboratory) that you would take in response to this outcome.[C5][C6]

5. **Bias and Material Practice**  
   Given the possibility that sherds are made from multiple clays, describe how this practice could affect both PCA and cluster analysis results, and how you would account for it in designing a machine-learning study.[C6]

---

### Key Takeaways

- Archaeological machine learning often centers on multivariate analysis of geochemical and compositional data, using PCA and cluster analysis as core tools.[C1][C2][C3][C5][C6][C10]  
- Feature engineering—especially normalization and log transformation of oxide data—substantially influences cluster structure and must be documented and justified.[C2][C3]  
- Group evaluation metrics like Mahalanobis distance can reveal weaknesses in apparently strong clusters and should be used to assess the statistical coherence of compositional groups.[C1][C5][C6]  
- Data-preparation issues (e.g., incomplete digestion) and material practices (e.g., mixing clays) introduce bias and complexity that limit simplistic clustering-based provenance assignments.[C5][C6]  
- Archaeological interpretations of exchange, distribution, and production must remain sensitive to the methodological choices in machine-learning workflows and the underlying assumptions they encode.[C2][C3][C5][C6][C10]

## Citation Map

- C1: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C2: citekey=Jardine2007-br; title=Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond; year=2007; doi=None
- C3: citekey=Jardine2007-br; title=Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond; year=2007; doi=None
- C5: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C6: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None
- C10: citekey=Watkins2006-lm; title=Parowan Pottery and Fermont Complexity: Late Formative Ceramic; year=2006; doi=None