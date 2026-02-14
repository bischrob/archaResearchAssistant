# 05 Curriculum Bridge

- Date: 2026-02-14
- Question: Draft notes that connect introductory computer science topics (algorithms, data structures, complexity, visualization) to archaeological case studies and student projects.
- Search query used: computer science archaeology education student projects algorithms data structures complexity visualization archaeological case studies introductory CS teaching
- Model: gpt-5.1
- RAG results count: 12

## Synthesized Notes

- Algorithms  
  - Both Watkins and Jardine use **Ward’s algorithm** and the **Average Link algorithm** for cluster analysis to group archaeological samples based on chemical composition. These are explicit examples of algorithmic procedures producing structured groupings from raw data. [C1][C2][C3][C5][C6][C10][C11]  
  - Jardine also uses **k-means cluster analysis** to identify 2, 3, and 5 cluster solutions in turquoise compositional data, again highlighting an algorithm that iteratively assigns cases to clusters. [C11]  
  - Notes for students: introductory CS discussions of “what is an algorithm” can be tied directly to how Ward’s, Average Link, and k-means procedures are defined, applied to data, and compared in these studies. [C2][C3][C5][C6][C10][C11]  

- Data structures and data modeling  
  - The turquoise and pottery studies work with **databases of cases** (e.g., 38 cases for the PIXE database after removing outliers) and multiple measured variables, essentially structured tables of observations and attributes. [C2][C3][C6][C10][C11]  
  - Kansa et al. emphasize that **data modeling and organization** strongly affect later reuse; they note that poor data modeling (for example, forcing complex phenomena into simple flat tables) can impede reuse and increase downstream effort. [C9]  
  - They call for better **data validation and decoding** and for improved **data modeling** practices at the time of data creation, underscoring the importance of how information is structured. [C9]  
  - Lodwick similarly frames archaeology as “built on the production and analysis of quantitative data,” with archaeobotany depending on time‑intensive, structured records of plant remains, which later must be shared, cited, and reused. [C12]  
  - Notes for students: introductory CS views of arrays/tables and schemas can be connected to how archaeological case tables (cases × variables) are designed and cleaned for cluster analysis and long‑term reuse. [C2][C3][C6][C9][C10][C11][C12]  

- Complexity and quantitative reasoning  
  - Watkins evaluates the “strength of the groups” suggested by the cluster algorithms using the **Mahalanobis Distance metric**, calculating probabilities of group membership and iteratively removing samples with very low membership probabilities (P < 0.1) before recalculating the distances. [C1][C5]  
  - Jardine also attempts to measure the strength of clusters with Mahalanobis Distance but notes that the calculation requires at least two more samples than measured variables, constraining what cluster solutions can be evaluated. [C10]  
  - Watkins reports that, after pruning low‑probability samples and recalculating Mahalanobis distances, the probabilities of group membership for the remaining samples sometimes dropped sharply, leading to multiple possible explanations about data quality and group structure. [C4][C5]  
  - Jardine describes **outliers** (two cases omitted from analysis; separate geological, archaeological, and project samples that behave differently across analyses) and notes that the archaeological sample appears as an outlier in one clustering visualization, even when it joins larger clusters in others. [C10][C11]  
  - Kansa et al. and Lodwick both connect quantitative complexity to **reproducibility and reuse**: they stress that better data management, modeling, and sharing practices are needed so complex datasets can be reanalyzed and combined, rather than remaining one‑off, opaque results. [C9][C12]  
  - Notes for students: CS notions of “complexity” in data and models (not just runtime) can be illustrated by these difficulties in measuring group membership, handling outliers, and meeting statistical preconditions for distance metrics in real archaeological datasets. [C4][C5][C9][C10][C11][C12]  

- Visualization and exploratory data analysis  
  - Watkins uses **principal component plots** to visualize ceramic compositional variation: figures plotting principal component 1 (PC1) against PC2 and PC3, labeled by site and ceramic type (e.g., Parowan Valley, Baker, Mukwitch, Sevier Classic, South Temple, clay samples), serve as visual summaries of multivariate relationships. [C6]  
  - Both Watkins and Jardine present **dendrogram‑like cluster analysis graphics**, where “Distances” on one axis and “Case” identifiers on the other show how individual samples merge into clusters under Ward’s and Average Link algorithms, for different data transformations (normalized oxides, log‑transformed normalized oxides). [C1][C2][C3][C4][C5][C6][C10][C11]  
  - Jardine notes that log transformations give more “weight” to trace elements in the clustering, and Figures 13 and 14 are used to interpret how this transformation changes visible cluster structure and outlier status. [C11]  
  - Watkins’ and Jardine’s figures are concrete examples of visualization as a core step in data analysis: patterns, clusters, and anomalies are first recognized visually and then interpreted substantively. [C1][C2][C3][C4][C5][C6][C10][C11]  
  - Notes for students: CS topics on plotting, dimensionality reduction, and visual encodings can be tied to these principal‑component scatterplots and cluster diagrams used to reason about pottery and turquoise provenance. [C6][C10][C11]  

- Data management, sharing, and computational practice  
  - Kansa et al. argue that **improving data creation practices**, including validation, decoding, and modeling, reduces downstream costs for “data editors” and later data consumers; they emphasize that many researchers lack formal training in data management even though adequate modeling is crucial. [C9]  
  - Lodwick reviews **data sharing, citation, and reuse** in archaeobotany and frames these as central to the reproducibility and rigour of archaeological research, especially for data‑rich sub‑disciplines. [C12]  
  - Kintigh et al. discuss national and international **digital archaeological data services** (such as tDAR, ADS, and DANS), created in part to meet legal and regulatory requirements to curate digital archaeological data from federal activities, which underlines the infrastructural dimension of computational work in archaeology. [C7]  
  - Notes for students: introductory coverage of databases, data pipelines, and basic information systems can be connected to these efforts to curate, validate, and publish archaeological datasets for long‑term reuse and regulatory compliance. [C7][C9][C12]  

- Potential student project directions (grounded in these cases)  
  - Implement and compare **Ward’s, Average Link, and k‑means** clustering on a small, tabular mock dataset modeled after the “cases × variables” structure described for ceramics or turquoise, then visualize results as distance‑based dendrograms and scatterplots, mirroring the figures in Watkins and Jardine. [C2][C3][C5][C6][C10][C11]  
  - Experiment with **data transformations** (e.g., a simple analog to normalized vs. log‑transformed normalized oxides) to see how cluster membership and outlier behavior change, as Jardine reports for turquoise sources and trace elements. [C10][C11]  
  - Design a **data model** and validation rules for an archaeobotanical or artifact‑composition dataset, drawing on Kansa et al.’s discussion of validation, decoding, and modeling problems and Lodwick’s emphasis on reusable quantitative data. [C9][C12]  
  - Prototype a minimal **data‑sharing workflow** (e.g., from raw coded table to cleaned, documented dataset ready for reuse), explicitly addressing the problems and goals highlighted by Kansa et al. and Lodwick (documentation of codes, structure, and intended reuse). [C9][C12]

## Used Citations

- C1: Parowan Pottery and Fermont Complexity: Late Formative Ceramic (2006); Authors: Watkins CN, Janetski JC; Citekey: Watkins2006-lm; DOI: ; Source: pdfs/watkins2006-ParowanPotteryFermontComplexity-LateFormativeCeramic.pdf
- C2: Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond (2007); Authors: Jardine; Citekey: Jardine2007-br; DOI: ; Source: pdfs/jardine2007-FremontFinery_ExchangeDistributionOfTurquoiseOlivellaOrnamentsInParowanValleyBeyond.pdf
- C3: Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond (2007); Authors: Jardine; Citekey: Jardine2007-br; DOI: ; Source: pdfs/jardine2007-FremontFinery_ExchangeDistributionOfTurquoiseOlivellaOrnamentsInParowanValleyBeyond.pdf
- C4: Parowan Pottery and Fermont Complexity: Late Formative Ceramic (2006); Authors: Watkins CN, Janetski JC; Citekey: Watkins2006-lm; DOI: ; Source: pdfs/watkins2006-ParowanPotteryFermontComplexity-LateFormativeCeramic.pdf
- C5: Parowan Pottery and Fermont Complexity: Late Formative Ceramic (2006); Authors: Watkins CN, Janetski JC; Citekey: Watkins2006-lm; DOI: ; Source: pdfs/watkins2006-ParowanPotteryFermontComplexity-LateFormativeCeramic.pdf
- C6: Parowan Pottery and Fermont Complexity: Late Formative Ceramic (2006); Authors: Watkins CN, Janetski JC; Citekey: Watkins2006-lm; DOI: ; Source: pdfs/watkins2006-ParowanPotteryFermontComplexity-LateFormativeCeramic.pdf
- C7: Cultural Dynamics, Deep Time, and Data (2015); Authors: Kintigh KW, Altschul JH, Kinzig AP, Limp WF, Michener WK, Sabloff JA, Hackett EJ, Kohler TA; Citekey: Kintigh2015-rs; DOI: 10.7183/2326-3768.3.1.1; Source: pdfs/kintigh2015-CulturalDynamics,DeepTime,Data.pdf
- C9: Publishing and Pushing: Mixing Models for Communicating Research Data in Archaeology (2014); Authors: Kansa EC, Kansa SW, Arbuckle B; Citekey: Kansa2014-pj; DOI: 10.2218/ijdc.v9i1.301; Source: pdfs/kansa2014-PublishingPushing-MixingModelsCommunicatingResearchDataInArchaeology.pdf
- C10: Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond (2007); Authors: Jardine; Citekey: Jardine2007-br; DOI: ; Source: pdfs/jardine2007-FremontFinery_ExchangeDistributionOfTurquoiseOlivellaOrnamentsInParowanValleyBeyond.pdf
- C11: Fremont Finery_ Exchange and Distribution of Turquoise and Olivella Ornaments in the {Parowan }Valley and Beyond (2007); Authors: Jardine; Citekey: Jardine2007-br; DOI: ; Source: pdfs/jardine2007-FremontFinery_ExchangeDistributionOfTurquoiseOlivellaOrnamentsInParowanValleyBeyond.pdf
- C12: Sowing the Seeds of Future Research: Data Sharing, Citation and Reuse in Archaeobotany (2019); Authors: Lodwick L; Citekey: Lodwick2019-pr; DOI: 10.5334/oq.62; Source: pdfs/lodwick2019-SowingSeedsOfFutureResearch-DataSharing,CitationReuseInArchaeobotany.pdf