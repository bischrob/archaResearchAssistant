from pathlib import Path
from src.rag.config import Settings
from src.rag.openclaw_structured_refs import _extract_lines_with_page
p = Path('/mnt/c/Users/rjbischo/Zotero/storage/S3P5M3I3/Bubeck_2023_Sparks_of_AGI.pdf')
lines = [line for _, line in _extract_lines_with_page(p, settings=Settings(), strip_page_noise=True)]
for i in range(7690, 7745):
    print(i, lines[i])
