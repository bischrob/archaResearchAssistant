# Research for 9. Uncertainty, Validation, and Sensitivity Analysis

- Date: 2026-02-14
- Question: Write a concise but substantive college-level textbook chapter in markdown for '9. Uncertainty, Validation, and Sensitivity Analysis'. Audience: undergraduate computer science students learning computational archaeology. Include sections: Learning Objectives, Core Ideas, Worked Workflow, Case Study, Common Mistakes, Exercises, Key Takeaways. Focus: Present uncertainty quantification, Monte Carlo thinking, robustness checks, error propagation, and reporting standards. Use only grounded RAG evidence and cite claims with [C#].
- Search query used: uncertainty quantification monte carlo robustness checks error propagation reporting standards computational archaeology uncertainty quantification monte carlo simulation robustness checks sensitivity analysis error propagation validation reporting standards archaeological modeling undergraduate textbook
- Model: gpt-5.1
- RAG results: 10

## Synthesized Draft

## 9. Uncertainty, Validation, and Sensitivity Analysis

### Learning Objectives

After this chapter you should be able to:

- Explain why uncertainty and error are fundamental issues in archaeological computational modeling, not just technical details. [C7]  
- Describe what sensitivity analysis is and how it relates to uncertainty analysis, calibration, and solution‐space exploration. [C3][C5]  
- Recognize that assumptions about past behavior and data are uncertain in both computational and “traditional” archaeological reasoning. [C7]  
- Outline a basic workflow that incorporates uncertainty assessment and sensitivity analysis into simulation or other computational models. [C3][C5][C7]  
- Identify common mistakes in using quantitative and modeling tools drawn from other disciplines. [C5][C8][C9][C10]  
- Formulate transparent reporting practices that make uncertainty and robustness checks explicit. [C5][C7]

---

### Core Ideas

#### 9.1 Uncertainty is Everywhere

With the expansion of formal computational models in archaeology since the late 1960s, such as simulations and predictive modeling, model use has increased but is still less common than it could be. [C4] At the same time, there is no discipline‑wide protocol for identifying and isolating sources of error or uncertainty in these models. [C5]

Uncertainty arises at multiple levels:

- **Data and proxies:** Archaeological network analysis, for example, often cannot observe social links directly; instead it infers ties from proxies such as shared artifact types, styles, or raw material sources. [C10] These proxies introduce uncertainty about what the inferred relationships actually represent. [C10]
- **Conceptual assumptions:** Underlying ideas about past human behavior are often built on ambiguous archaeological data and anthropological analogy, so uncertainty is not limited to computational methods but also affects “traditional” models. [C7]
- **Computational implementation:** Different combinations of software, coding languages, input parameters, landscape reconstructions, and behavioral processes produce models with complex and sometimes opaque uncertainty structures. [C5]

Because of this, the editors of a major volume on archaeological computational modeling explicitly argue that uncertainty assessment should be applied not only to formal models but also to implicit assumptions about the past. [C7]

#### 9.2 Monte Carlo Thinking and Solution‑Space Exploration

In simulation work, sensitivity analysis is framed as part of a broader “solution space exploration” that also includes optimization, calibration, and uncertainty analysis, all aimed at understanding a model’s results, their robustness, and their implications. [C3]

Monte Carlo–style thinking—systematically exploring many possible combinations of parameters or inputs—is conceptually aligned with this solution‑space exploration:

- You treat parameters and inputs as variable rather than fixed.
- You run many model realizations with varied inputs.
- You examine how outcomes change across these realizations to understand robustness and uncertainty. [C3]

Although the term “Monte Carlo” is not used explicitly in the cited texts, the practice of varying inputs systematically to explore outcome behavior is the same conceptual foundation as Monte Carlo approaches. [C3]

#### 9.3 Sensitivity Analysis: What It Is and Why It Matters

Sensitivity analysis is defined as a phase in simulation development, often regarded as part of analyzing results. [C3] It “consists of varying the input of a simulation, either parameter values or input data, and recording the changes” in outcomes. [C3]

It is intimately tied to:

- **Robustness:** By checking how much outcomes change when inputs are perturbed, you evaluate the robustness of substantive conclusions. [C3]
- **Uncertainty analysis and calibration:** Sensitivity analysis is considered alongside uncertainty analysis and calibration as complementary ways of understanding models. [C3]
- **Discipline practice:** A case study on the MERCURY model in Roman economic integration explicitly uses sensitivity analysis, and its authors argue that sensitivity analyses should become much more common in archaeology, providing open scripts to help others implement them. [C3]

Given the lack of discipline‑based protocols for testing models, a forum at the Society for American Archaeology was convened specifically on “Error, Sensitivity Analysis, and Uncertainty in Archaeological Computational Modeling,” leading to a collected volume meant to foreground these practices across archaeology. [C5][C7]

#### 9.4 Error Propagation in Archaeological Models

Because models combine multiple uncertain components—software, code, input parameters, reconstructed landscapes, and behavioral rules—errors can propagate in complex ways. [C5]

Key implications:

- Small uncertainties in inputs (e.g., environmental reconstructions, artifact classifications) can have disproportionate effects on outputs once processed through a model’s internal logic. [C5][C7]
- Since modelers often rely on ambiguous data and analogy, error propagation is not only numerical but conceptual: uncertain assumptions flow through to uncertain interpretations of past behavior. [C7]
- Formal modeling is valuable precisely because it allows such uncertainty to be investigated explicitly, rather than remaining implicit. [C7]

#### 9.5 Critical Use of Imported Methods

Several authors warn that quantitative and modeling tools taken from other disciplines must be used critically:

- In network analysis, methods and interpretative assumptions from sociology are often imported, despite archaeological data being fundamentally different from sociological data. [C8][C9]
- Archaeological networks are often built from assemblage data rather than direct observation of relationships, meaning that some measures, theories, and techniques are applicable only if “appropriately utilized.” [C10]
- Consequently, archaeological network analysis should be rooted in relational thinking and archaeological reasoning, not just borrowed tools. [C8][C9][C10]

This is directly relevant to uncertainty and validation: an uncritical adoption of external tools can hide mismatches between method assumptions and archaeological data, creating unrecognized sources of error. [C8][C9][C10]

---

### Worked Workflow: Building Uncertainty and Sensitivity into a Model

This section sketches a generic workflow for an archaeological computational model that explicitly incorporates uncertainty, robustness checks, and sensitivity analysis. It synthesizes themes from work on archaeological simulations, uncertainty, and network analysis. [C3][C5][C7][C8][C9][C10]

#### Step 1: Problem Definition and Assumption Audit

- Define the archaeological question (e.g., dynamics of Roman economic integration or prehistoric economies). [C3][C4][C10]
- List all major theoretical assumptions about behavior, environment, and material culture.
- Explicitly note where assumptions rest on ambiguous data or analogy, recognizing that these are themselves uncertain. [C7]

#### Step 2: Data and Proxy Assessment

- Identify what you can observe directly versus what must be inferred from proxies (e.g., social links from shared artifact types or raw material sources; networks from assemblage distributions). [C8][C9][C10]
- Document the uncertainties involved in each proxy: what alternative interpretations could the same pattern support? [C10]

#### Step 3: Model Design with Uncertainty in Mind

- Design the computational model (simulation, GIS‑based model, or network‑based model) as one component in a broader research design, rather than as an infallible oracle. [C2][C7][C8]
- Explicitly mark uncertain parameters (e.g., rates, thresholds, decision rules) for later sensitivity analysis. [C3][C5][C7]
- Recognize that choices of software, code architecture, and landscape reconstruction all introduce potential errors. [C5]

#### Step 4: Implementation and Verification

- Implement the model using explicit, reproducible code and, where possible, prepare scripts that others can reuse or adapt for their own sensitivity analyses, as done in the MERCURY model study. [C3]
- Verify that the implementation matches the intended design (i.e., check for coding errors or unintended behavior), acknowledging that this is distinct from validating the model against data. [C5][C7]

#### Step 5: Uncertainty Exploration and Monte Carlo‑Style Runs

- Treat uncertain parameters and inputs as ranges rather than fixed values.
- Run many model realizations across these ranges, akin to solution‑space exploration, to see what set of outcomes the model can produce. [C3]
- Record distributions of key outputs instead of relying on a single “best run,” reflecting the emphasis on exploring solution spaces rather than point predictions. [C3][C7]

#### Step 6: Sensitivity Analysis

- Systematically vary one or more parameters or input datasets and record how the outputs change, following the definition of sensitivity analysis as varying inputs and tracking resulting changes. [C3]
- Use this to:
  - Identify which inputs most strongly affect outcomes (high sensitivity).
  - Detect parameters that do not materially change results (low sensitivity), which may indicate redundancy or over‑parameterization.
- Interpret these patterns in light of archaeological questions (e.g., which aspects of behavior or environment are truly crucial to a hypothesized process). [C3]

#### Step 7: Calibration and Comparative Evaluation

- Consider sensitivity analysis alongside calibration and uncertainty analysis within a coherent solution‑space exploration framework. [C3]
- Where appropriate (e.g., for network or economic models), compare model outputs to empirical archaeological patterns such as observed distributions of table wares or obsidian. [C3][C8][C10]
- Use discrepancies not simply to reject models but to refine assumptions and highlight where uncertainty or missing processes might lie. [C5][C7][C8]

#### Step 8: Interpretation and Error Propagation Reflection

- Trace how uncertainties in proxies, assumptions, and parameters propagate through the model to affect conclusions about past behavior. [C5][C7][C10]
- Distinguish between robust findings (stable across a wide range of plausible inputs) and fragile ones (dependent on narrow parameter choices). [C3][C7]

#### Step 9: Transparent Reporting

- Report how and where uncertainty enters the model, both theoretically and methodologically. [C5][C7]
- Describe how many runs were executed, what ranges were explored, and how sensitivity analysis was performed (e.g., which parameters varied, what metrics recorded). [C3][C5]
- Clarify how modeling tools from other disciplines (e.g., network metrics from sociology) were adapted or critiqued in light of archaeological data properties. [C8][C9][C10]

---

### Case Study (Conceptual): Sensitivity Analysis and Economic / Network Models

Several concrete strands in the literature illustrate how uncertainty, sensitivity, and robustness play out in computational archaeology. This section conceptually synthesizes them without reconstructing full technical details.

#### MERCURY Model and Roman Economic Integration

A sensitivity analysis of the MERCURY simulation model, applied to debates on Roman economic integration, offers a practical example. [C3]

Key points:

- The authors replicated and modified an existing model specifically to enable sensitivity analysis, showing that models not originally built for this purpose may need re‑engineering to support systematic input variation. [C3]
- By varying parameter values and input data, and recording changes in key outcomes, they evaluated how robust the model’s implications for Roman economic integration were to plausible uncertainties. [C3]
- Based on this experience, they argued that sensitivity analysis should become routine in archaeological simulation and provided an open analysis script to support adoption. [C3]

This case directly demonstrates that serious archaeological inferences (here about large‑scale economic integration) depend on understanding how sensitive model conclusions are to uncertainties in assumptions and data. [C3]

#### Archaeological Network Analysis and Data Uncertainty

Work on archaeological network analysis, such as studies of Roman table ware distributions and Mesoamerican economies, emphasizes different but related uncertainty issues. [C8][C9][C10]

- Archaeological network analysis often derives networks from assemblage data rather than direct social observations, for example using shared artifact types or raw material sources to infer ties between archaeological sites. [C10]
- Because these are indirect measures, there is inherent uncertainty in what sort of relationships they encode; this affects any subsequent quantitative analysis, such as computing network centrality or other metrics borrowed from sociology. [C8][C9][C10]
- Authors therefore stress that not all measures and techniques from social network analysis can be applied uncritically; only those appropriately matched to archaeological data and reasoning should be used. [C8][C9][C10]

Inside a full modeling workflow, these insights inform:

- How to construct network‑based models or compare simulated networks to empirical ones.
- How to interpret sensitivity of network metrics to definitions of ties or to different artifact proxies (e.g., different ceramic types or materials). [C8][C9][C10]

Together, the MERCURY study and archaeological network work underscore that uncertainty and sensitivity analysis are as much about the nature of archaeological evidence and proxies as about numerical techniques. [C3][C8][C9][C10]

---

### Common Mistakes

The literature identifies recurring pitfalls in archaeological computational modeling and quantitative analysis.

1. **Treating Models or Tools as Infallible**

   - A forum and subsequent volume explicitly question the “infallibility” of tools like GIS and highlight the lack of discipline‑wide protocols for error and uncertainty assessment. [C2][C5]
   - Over‑trust in software outputs without explicit uncertainty analysis leads to misleading confidence in results. [C2][C5][C7]

2. **Ignoring Theoretical and Data Uncertainty**

   - Focusing only on numerical error while ignoring that underlying ideas about past behavior are built on ambiguous data and analogy. [C7]
   - Failing to acknowledge that uncertainty extends beyond computational aspects into “traditional” archaeological reasoning. [C7]

3. **Uncritical Adoption of External Methods**

   - Importing network measures and interpretative assumptions from sociology without considering that archaeological networks are built on different types of evidence. [C8][C9][C10]
   - Applying all techniques of social network analysis to archaeological data, instead of carefully selecting those that are appropriate to proxy‑derived networks. [C8][C9][C10]

4. **Lack of Sensitivity Analysis**

   - Running a model once (or only a few times) and treating outcomes as definitive without systematic exploration of parameter and input uncertainty. [C3][C5]
   - Omitting sensitivity analysis entirely, despite its role in assessing robustness and understanding how inputs shape outputs. [C3][C5]

5. **Opaque Reporting**

   - Not documenting where uncertainty enters (in data, parameters, reconstructions, code) or how it was handled. [C5][C7]
   - Providing results without open scripts or sufficient detail to allow replication or independent sensitivity analysis. [C3][C5]

Avoiding these mistakes requires both methodological rigor and a reflective stance about the nature of archaeological evidence and inference. [C5][C7][C8][C9][C10]

---

### Exercises

1. **Assumption Audit Exercise**

   - Take a simple computational model you have encountered (or design a sketch of one, e.g., a site location predictive model).
   - List:
     - Data inputs and their sources.
     - Theoretical assumptions about behavior or environment.
     - Any proxies used to represent unobserved processes (e.g., artifact types as proxies for interaction).
   - For each, describe briefly what makes it uncertain (e.g., ambiguity in data, reliance on analogy). [C7][C10]

2. **Conceptual Sensitivity Analysis Design**

   - Suppose you are modeling an economic network in a Roman or Mesoamerican context.
   - Identify three parameters or inputs that you would systematically vary (e.g., link thresholds, cost assumptions, or artifact‑based tie definitions).
   - For each, describe what outputs or metrics you would monitor to assess sensitivity (e.g., changes in overall connectivity, centrality of specific sites).
   - Explain how differences in the archaeological proxies (like different artifact types) could alter inferred networks. [C3][C8][C9][C10]

3. **Critical Method Adoption**

   - Choose a quantitative method from another discipline (e.g., a network centrality measure from sociology).
   - Write a short critique of how applying it to archaeological assemblage‑based networks might introduce error or misinterpretation, and what adaptations or cautions are needed. [C8][C9][C10]

4. **Reporting Plan**

   - Draft a one‑page outline of how you would report uncertainty and sensitivity analysis in a hypothetical modeling study:
     - What uncertainties would you highlight?
     - How would you summarize sensitivity results?
     - What scripts or data would you share to facilitate replication? [C3][C5][C7]

---

### Key Takeaways

- Computational models in archaeology have grown with increasing computer power, but the discipline lacks clear protocols for identifying and managing uncertainty and error. [C4][C5]
- Uncertainty arises from ambiguous data, proxy‑based inference, analogical reasoning, and implementation choices, affecting both computational and “traditional” models of the past. [C5][C7][C10]
- Sensitivity analysis, defined as varying simulation inputs and recording outcome changes, is central to evaluating robustness and belongs alongside optimization, calibration, and uncertainty analysis in exploring a model’s solution space. [C3]
- Case work such as the MERCURY model study demonstrates that meaningful archaeological interpretations, like those concerning Roman economic integration, depend on explicit sensitivity analysis; such work also shows the value of open scripts for community adoption. [C3]
- Archaeological network analysis highlights that data are often indirect proxies for relationships, so methods and interpretations from sociology and other fields must be adapted carefully, grounded in archaeological reasoning and relational thinking. [C8][C9][C10]
- Uncertainty assessment should be applied not only to computational details but also to implicit ideas and assumptions about the past, and it must be transparently reported to make archaeological modeling credible and cumulative. [C5][C7]

## Citation Map

- C2: citekey=Brouwer-Burg2016-na; title=Introduction to Uncertainty and Sensitivity Analysis in Archaeological Computational Modeling; year=2016; doi=10.1007/978-3-319-27833-9_1
- C3: citekey=Kanters2021-wq; title=Sensitivity analysis in archaeological simulation: An application to the MERCURY model; year=2021; doi=10.1016/j.jasrep.2021.102974
- C4: citekey=Brouwer-Burg2016-na; title=Introduction to Uncertainty and Sensitivity Analysis in Archaeological Computational Modeling; year=2016; doi=10.1007/978-3-319-27833-9_1
- C5: citekey=Brouwer-Burg2016-na; title=Introduction to Uncertainty and Sensitivity Analysis in Archaeological Computational Modeling; year=2016; doi=10.1007/978-3-319-27833-9_1
- C7: citekey=Brouwer-Burg2016-na; title=Introduction to Uncertainty and Sensitivity Analysis in Archaeological Computational Modeling; year=2016; doi=10.1007/978-3-319-27833-9_1
- C8: citekey=Brughmans2010-mg; title=Connecting the dots: Towards archaeological network analysis: Connecting the dots; year=2010; doi=10.1111/j.1468-0092.2010.00349.x
- C9: citekey=Brughmans2010-mg; title=Connecting the dots: Towards archaeological network analysis: Connecting the dots; year=2010; doi=10.1111/j.1468-0092.2010.00349.x
- C10: citekey=Kerig2019-pf; title=Social Network Analysis in Economic Archaeology - Perspectives from the New World; year=2019; doi=None