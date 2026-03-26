import sys
from pathlib import Path
sys.path.insert(0, '.')

from src.rag.config import Settings
from src.rag.openclaw_structured_refs import (
    _extract_lines_with_page,
    detect_section_plan_details,
    _reference_block_text,
    split_reference_strings_for_anystyle,
)

pdf = Path('/mnt/storage/main/home_server/researchAssistant/ingest_inputs/zotero/storage/EVQUW6ZD/allison2008-AbajoRed-on-orangeEarlyPuebloICulturalDiversityInNorthernSanJuanRegion.pdf')
settings = Settings()
lines_with_page = _extract_lines_with_page(pdf, settings=settings, strip_page_noise=True)
lines = [line for _, line in lines_with_page]
headings, sections, _ = detect_section_plan_details(lines, settings=settings)
print('HEADINGS', headings)
print('SECTIONS')
for s in sections:
    print({'kind': s.kind, 'start_line': s.start_line, 'end_line': s.end_line})

for s in sections:
    if s.kind != 'references':
        continue
    print('=== REFERENCE SECTION ===')
    print({'start_line': s.start_line, 'end_line': s.end_line})
    block = _reference_block_text(lines, s, settings=settings)
    print('=== BLOCK ===')
    print(block)
    refs = split_reference_strings_for_anystyle(block, settings=settings)
    print('=== SPLIT REFS ===')
    print('count', len(refs))
    for i, ref in enumerate(refs, start=1):
        print(f'REF {i}: {ref}')
