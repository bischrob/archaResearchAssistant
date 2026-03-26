from src.rag.openclaw_structured_refs import detect_section_plan, detect_section_plan_details
from src.rag.config import Settings

lines = [
    "Introduction",
    "Body paragraph.",
    "References",
    "[1] Alpha. 2020. First reference.",
    "[2] Beta. 2021. Second reference.",
    "APPENDIX",
    "Figure 1: Supplemental figure.",
]

print(detect_section_plan(lines, settings=Settings()))
print(detect_section_plan_details(lines, settings=Settings()))
