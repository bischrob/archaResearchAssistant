# Research for 10. Ethics, Data Governance, and Community Collaboration

- Date: 2026-02-14
- Question: Write a concise but substantive college-level textbook chapter in markdown for '10. Ethics, Data Governance, and Community Collaboration'. Audience: undergraduate computer science students learning computational archaeology. Include sections: Learning Objectives, Core Ideas, Worked Workflow, Case Study, Common Mistakes, Exercises, Key Takeaways. Focus: Discuss reproducibility ethics, FAIR+CARE, Indigenous data sovereignty, consent, and responsible publication practices. Use only grounded RAG evidence and cite claims with [C#].
- Search query used: ethics data governance community collaboration computational archaeology reproducibility ethics FAIR CARE Indigenous data sovereignty consent responsible publication practices undergraduate computer science textbook chapter
- Model: gpt-5.1
- RAG results: 10

## Synthesized Draft

# 10. Ethics, Data Governance, and Community Collaboration

## Learning Objectives

By the end of this chapter, you should be able to:

- Explain how FAIR and CARE principles jointly shape ethical archaeological data practice (“FAIR+CARE”). [C1][C5][C8][C10]
- Describe Indigenous data sovereignty and why it matters for computational archaeology. [C1][C4][C5]
- Identify responsibilities around consent, control, and benefit-sharing when working with Indigenous data. [C1][C2][C3][C5]
- Outline a reproducible, ethically grounded workflow for managing archaeological data. [C8][C9][C10]
- Recognize common ethical pitfalls in digital and computational heritage work, including 3D and XR technologies. [C7][C8][C10]

---

## Core Ideas

### 1. Reproducibility as an Ethical Obligation

Infrastructure that supports reuse of scholarly data is urgently needed, because current digital ecosystems prevent the community from extracting maximum benefit from research investments. [C9] Good data management is not an end in itself but a conduit to knowledge discovery, innovation, and data reuse by the broader community. [C9] In computational archaeology, this means that making your workflows and datasets reusable is part of your ethical responsibility to both science and affected communities. [C8][C10]

The FAIR Guiding Principles—Findable, Accessible, Interoperable, Reusable—were designed to improve infrastructure for data reuse and transform scholarly data sharing. [C9][C8] FAIR emphasizes that machines as well as humans should be able to automatically find and use data. [C9] In archaeology, FAIR is being promoted through data life‑cycle frameworks that address creation, curation, and dissemination. [C8][C10]

### 2. FAIR + CARE: Technical and Social Dimensions

FAIR alone focuses on characteristics of data (findability, accessibility, interoperability, reusability) to facilitate sharing across entities. [C5][C8] However, open data and open science movements based only on FAIR do not fully engage with Indigenous Peoples’ rights and interests, and they tend to ignore power differentials and historical contexts. [C5] As a result, efforts to increase openness can be in tension with Indigenous demands for greater control over the use of Indigenous data and knowledge for collective benefit. [C5]

The CARE Principles—Collective Benefit, Authority to Control, Responsibility, and Ethics—are people‑ and purpose‑oriented and were developed to reflect the role of data in advancing Indigenous innovation and self‑determination. [C5] They complement FAIR by encouraging open data movements to consider both people and purpose in their advocacy and practices. [C5] Archaeological data have complex technical, professional, social, economic, cultural, legal, and policy entanglements, so FAIR and CARE must be implemented together as “FAIR+CARE” to guide intentional data creation, curation, and dissemination. [C8][C10]

When FAIR is implemented with CARE, it can connect the reuse of information about past populations to issues of trust, transparency, ethical practice, and “better science.” [C8] This combined framework is promoted explicitly in archaeology as a way to manage data ethically and responsibly. [C8][C10]

### 3. Indigenous Data Sovereignty and Governance

The UN Declaration on the Rights of Indigenous Peoples (UNDRIP) reaffirms Indigenous rights to self‑governance and authority over their cultural heritage—languages, knowledge, practices, technologies, natural resources, territories—which together can be understood as “Indigenous data.” [C4] Indigenous data include data collected by governments and institutions about Indigenous Peoples and their territories. [C4] Indigenous data are intrinsic to Indigenous Peoples’ capacity to realize their human rights and responsibilities. [C4] Indigenous data sovereignty reinforces the right to engage in decision‑making in accordance with Indigenous values and collective interests. [C4][C5]

The CARE framework articulates specific governance rights. Indigenous Peoples have rights and interests in both Indigenous Knowledge and Indigenous data, including collective and individual rights to free, prior, and informed consent in data collection and use, as well as in the development of data policies and protocols. [C1] Indigenous data governance supports Indigenous nations and governing bodies in determining how Indigenous Peoples, lands, territories, resources, knowledges, and geographical indicators are represented and identified within data. [C1]

Indigenous Peoples also have the right to data that are relevant to their worldviews and that empower self‑determination and effective self‑governance, and these data must be accessible to Indigenous nations and communities to support Indigenous governance. [C1][C2] They further have the right to develop cultural governance protocols for Indigenous data and to be active leaders in stewardship and access, especially for Indigenous Knowledge. [C2]

### 4. Collective Benefit and Equitable Value

CARE’s “Collective Benefit” principle emphasizes that governments and institutions must actively support Indigenous nations and communities in using and reusing data to establish foundations for Indigenous innovation, value generation, and self‑determined development. [C6] Data can enrich planning, implementation, and evaluation processes for Indigenous service and policy needs, and can improve governance and citizen engagement. [C6]

Ethical use of open data can improve transparency and decision‑making by providing Indigenous nations and communities with better understanding of their peoples, territories, and resources, and with insight into third‑party policies and programs affecting them. [C6] Any value created from Indigenous data should benefit Indigenous communities equitably and contribute to Indigenous aspirations for wellbeing. [C1][C6]

### 5. Responsibility, Capacity, and Ethics Across the Data Life Cycle

The CARE “Responsibility” principle requires that those working with Indigenous data share how data are used to support self‑determination and collective benefit, with accountability demonstrated through meaningful and openly available evidence of these efforts and the benefits accruing to Indigenous Peoples. [C2] Indigenous data use is considered unviable unless embedded in relationships based on respect, reciprocity, trust, and mutual understanding, as defined by the Indigenous Peoples concerned. [C2]

Responsibility also includes ensuring that data creation, interpretation, and use uphold or respect the dignity of Indigenous nations and communities. [C2][C3] Use of Indigenous data invokes a reciprocal responsibility to enhance data literacy within Indigenous communities and to support development of an Indigenous data workforce and digital infrastructure for data creation, management, security, governance, and application. [C3] Resources must be provided to generate data grounded in Indigenous languages, worldviews, lived experiences, values, and principles. [C3]

Under the “Ethics” principle, Indigenous rights and wellbeing should be the primary concern at all stages of the data life cycle and across the data ecosystem. [C3] Ethical data should not stigmatize or portray Indigenous Peoples, cultures, or knowledges in deficit terms, and must align with Indigenous ethical frameworks and rights affirmed in UNDRIP. [C3] Assessment of benefits and harms should be made from the perspective of the Indigenous Peoples to whom the data relate. [C3]

---

## Worked Workflow: An Ethical, Reproducible Data Life Cycle

This workflow shows how FAIR+CARE can structure a computational archaeology project involving Indigenous data.

### Step 1: Project Scoping and Governance

- Begin by recognizing Indigenous Peoples’ rights and interests in both Indigenous Knowledge and data, including their authority to control such data. [C1][C4]
- Engage Indigenous governing bodies early to co‑develop data policies and protocols, respecting their free, prior, and informed consent in collection and use. [C1][C2]
- Identify community priorities for how data can support self‑determination, governance, and wellbeing. [C1][C2][C6]

### Step 2: Ethical Study Design and Consent

- Design the project so that any value created from Indigenous data will benefit Indigenous communities in an equitable manner and contribute to their aspirations for wellbeing. [C1][C6]
- Ensure planned data are relevant to Indigenous worldviews and governance needs, and that resulting datasets will be made available and accessible to the communities for their own governance and decision‑making. [C1][C2][C6]
- Agree on consent procedures that include input into collection methods, future uses, and publication and sharing conditions. [C1][C2][C3]

### Step 3: Data Collection and Documentation

- Collect data in ways that uphold the dignity of Indigenous nations and communities and avoid stigmatizing or deficit‑based representations. [C2][C3]
- Document how data relate to Indigenous lands, territories, resources, and knowledges so that Indigenous Peoples can later determine appropriate representation and identification within data systems. [C1][C2]
- Plan metadata and formats to support FAIR (machine‑actionable, interoperable, reusable) while embedding CARE‑aligned governance and restrictions where required. [C8][C9][C10]

### Step 4: Curation, Security, and Access

- Implement the FAIR principles to make data findable, accessible, interoperable, and reusable in appropriate repositories or platforms. [C8][C9][C10]
- At the same time, implement CARE by:
  - Applying Indigenous cultural governance protocols for access and stewardship. [C2]
  - Documenting Indigenous authority to control specific data and specifying conditions of reuse. [C1][C2]
  - Ensuring that open access is not granted where it would conflict with Indigenous rights, wellbeing, or ethical frameworks. [C2][C3][C5]

- Facilitate Indigenous access to the data to support their governance and decision‑making. [C1][C2][C6]

### Step 5: Analysis, Reproducibility, and Community Review

- Structure computational workflows and code so that they contribute to knowledge integration and reuse under FAIR principles. [C8][C9]
- Share analytic methods and results with Indigenous partners, explaining how analyses support self‑determination and collective benefit. [C2][C3][C6][C8]
- Invite community feedback on interpretations to avoid deficit framings and misrepresentation. [C2][C3]

### Step 6: Publication, Sharing, and Long‑Term Stewardship

- When publishing, describe how FAIR and CARE have guided data management and how benefits to Indigenous communities have been pursued. [C5][C8][C10]
- Use dissemination channels that also support Indigenous innovation and local self‑determined development processes. [C6]
- Make evidence of responsibilities and benefits openly available where appropriate, strengthening accountability. [C2]
- Support the development of Indigenous data literacy, workforce, and digital infrastructure as part of long‑term collaboration. [C3][C6]

---

## Case Study: FAIR+CARE in Archaeological Data Platforms

Archaeological data management platforms such as Open Context and tDAR have been used to preserve and improve access to archaeological data. [C10] Drawing on two decades of work with these systems, researchers have introduced a data life‑cycle framework grounded in the FAIR Guiding Principles to improve archaeology’s capacity to manage data ethically and responsibly. [C8][C10]

These efforts emphasize that:

- FAIR is necessary to improve data findability, accessibility, interoperability, and reusability and to transform the landscape of scholarly data sharing. [C8][C9]
- Implementation of FAIR in archaeology must consider the CARE Principles for Indigenous Data Governance, because archaeological data are entangled with social, cultural, legal, economic, and policy issues. [C8][C10]
- Presenting FAIR and CARE in tandem (“FAIR+CARE”) is essential to address elevated perceptions of risk around data sharing and open science and to promote trust, transparency, and better science. [C8][C10]

In practice, this has meant building systems and workflows that:

- Incorporate metadata and access controls reflecting Indigenous authority to control data and cultural protocols for stewardship. [C1][C2][C10]
- Make datasets technically reusable while respecting community‑defined conditions, including limits on openness. [C2][C3][C5][C8][C10]
- Frame data reuse in ways that can support Indigenous governance, planning, and evaluation, rather than solely external research agendas. [C1][C2][C6][C8][C10]

This case illustrates how computational infrastructures can be designed to align technical reproducibility with Indigenous data sovereignty and ethical obligations.

---

## Common Mistakes

1. **Treating FAIR as value‑neutral and sufficient.**  
   Applying FAIR only as a technical checklist, without considering power differentials, historical contexts, and Indigenous rights and interests, ignores documented limitations of open data movements. [C5][C8][C10]

2. **Equating “open” with “ethical.”**  
   Assuming that more openness is always better can create tension with Indigenous Peoples’ assertions of control over Indigenous data and knowledge for collective benefit. [C5] CARE explicitly indicates that some data must be governed, not simply opened. [C1][C2][C3][C5]

3. **Ignoring Indigenous authority to control data.**  
   Failing to recognize Indigenous Peoples’ rights and interests in Indigenous data and knowledge, and their collective and individual rights to free, prior, and informed consent, violates CARE principles and Indigenous data sovereignty. [C1][C4][C5]

4. **Instrumentalizing community “benefit.”**  
   Designing projects that primarily benefit external researchers or institutions, while only nominally addressing Indigenous wellbeing or innovation, contradicts CARE’s requirement that value created from Indigenous data equitably benefit Indigenous communities and support their aspirations. [C1][C6]

5. **Weak accountability and opaque reuse.**  
   Not providing meaningful, openly available evidence of how data use supports Indigenous self‑determination and collective benefit undermines the Responsibility principle and erodes trust. [C2]

6. **Deficit‑based or stigmatizing representations.**  
   Producing or sharing data and interpretations that stigmatize Indigenous Peoples or present cultures and knowledge in terms of deficit conflicts with CARE’s Ethics principle. [C3]

7. **Unstructured use of emerging digital tools.**  
   In heritage contexts, technologies such as XR (VR/AR/MR), 3D scanning, generative AI, and unauthorized “guerilla scanning” introduce new risks around unauthorized capture, monetization, and circulation of cultural objects and knowledge. [C7] Without Indigenous governance and CARE‑aligned protocols, these uses can conflict with Indigenous Data Governance, defined as the right and authority of Indigenous Peoples and Tribal Nations to govern data originating from their knowledges. [C7]

---

## Exercises

1. **Short Essay (Conceptual).**  
   Explain how the FAIR and CARE principles complement each other in archaeological data management. Use examples to show why FAIR alone is insufficient for ethical practice involving Indigenous data. Support your arguments with citations to the definitions and critiques of FAIR and CARE. [C5][C8][C9][C10]

2. **Workflow Critique (Applied).**  
   Draft a simple data life‑cycle for a computational archaeology project using remote sensing data from Indigenous territories. Identify at least three points where Indigenous Authority to Control and free, prior, and informed consent must shape decisions. Discuss how you would document responsibility and collective benefit. [C1][C2][C3][C4][C5][C6]

3. **Case Analysis (Ethics and Technology).**  
   Using the glossary definitions of XR, guerilla scanning, and Indigenous Data Governance, analyze potential ethical issues that arise when archaeologists or other actors create and share 3D scans of cultural objects online without community involvement. Propose governance measures aligned with CARE to address these issues. [C1][C2][C3][C4][C5][C7]

4. **Policy Design (Governance).**  
   Draft a one‑page outline of a data sharing policy for an archaeological repository that wants to adopt FAIR+CARE. Specify how the repository will handle:
   - Requests for open access to datasets involving Indigenous data.
   - Documentation of community consent and governance protocols.
   - Evidence of benefits to Indigenous communities and accountability mechanisms. [C1][C2][C3][C5][C6][C8][C10]

---

## Key Takeaways

- Good data management is a conduit to knowledge discovery and reuse; FAIR principles were developed to improve infrastructure for data reuse and transform scholarly data sharing, including in archaeology. [C8][C9][C10]
- The movement toward open data and open science, grounded in FAIR alone, does not fully engage with Indigenous Peoples’ rights and interests and often ignores power differentials and historical contexts. [C5]
- Indigenous data sovereignty affirms Indigenous rights to self‑governance and authority over Indigenous data and cultural heritage, reinforcing decision‑making in accordance with Indigenous values and collective interests. [C4][C5]
- CARE—Collective Benefit, Authority to Control, Responsibility, Ethics—complements FAIR by centering people and purpose, emphasizing equitable benefit, consent, Indigenous governance, accountability, and non‑stigmatizing data practices. [C1][C2][C3][C5][C6]
- Archaeological data are deeply entangled with social, cultural, legal, and political issues; implementing FAIR+CARE together is therefore crucial to build trust, transparency, ethical practice, and better science. [C8][C10]
- Ethical computational archaeology requires workflows that recognize Indigenous authority, ensure free, prior, and informed consent, support Indigenous governance and wellbeing, and provide clear evidence of responsibility and benefit throughout the data life cycle. [C1][C2][C3][C4][C5][C6][C8][C10]
- Emerging digital tools, including XR and 3D technologies, must be governed under Indigenous Data Governance and CARE principles to avoid unauthorized capture, misuse, or commodification of Indigenous heritage. [C3][C4][C5][C7]

## Citation Map

- C1: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C2: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C3: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C4: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C5: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C6: citekey=Carroll2020-fy; title=The {CARE} {Principles} for {Indigenous} {Data} {Governance}; year=2020; doi=10.5334/dsj-2020-043
- C7: citekey=Csoba-DeHass2025-wt; title=Ethical Considerations in the use of 3D technologies to preserve and perpetuate Indigenous Heritage; year=2025; doi=10.1017/aaq.2024.82
- C8: citekey=Nicholson2023-oq; title=Will it ever be FAIR?: Making archaeological data findable, accessible, interoperable, and reusable; year=2023; doi=10.1017/aap.2022.40
- C9: citekey=Wilkinson2016-vv; title=The {FAIR} {Guiding} {Principles} for scientific data management and stewardship; year=2016; doi=10.1038/sdata.2016.18
- C10: citekey=Nicholson2023-oq; title=Will it ever be FAIR?: Making archaeological data findable, accessible, interoperable, and reusable; year=2023; doi=10.1017/aap.2022.40