from pathlib import Path
from src.rag.config import Settings
from src.rag.openclaw_structured_refs import extract_structured_chunks_and_citations

settings = Settings(citation_parser='openclaw_refsplit_anystyle')
paths = [
    Path('/mnt/c/Users/rjbischo/Zotero/storage/S3P5M3I3/Bubeck_2023_Sparks_of_AGI.pdf'),
    Path('/mnt/c/Users/rjbischo/Zotero/storage/D6GP963Q/3411764.3445618.pdf'),
    Path('/mnt/c/Users/rjbischo/Zotero/storage/X4HP8U4T/3397481.3450649.pdf'),
]
for p in paths:
    print(f'=== {p}')
    result = extract_structured_chunks_and_citations(
        pdf_path=p,
        article_id=p.stem,
        settings=settings,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
        strip_page_noise=settings.chunk_strip_page_noise,
    )
    print('reference_count', len(result.reference_strings))
    if result.reference_strings:
        print('first1', result.reference_strings[0])
        if len(result.reference_strings) > 1:
            print('first2', result.reference_strings[1])
        print('last', result.reference_strings[-1])
    else:
        print('first1', None)
        print('first2', None)
        print('last', None)
    sidecar = p.with_suffix('.references.txt')
    print('sidecar_exists', sidecar.exists())
    if sidecar.exists():
        lines = sidecar.read_text(encoding='utf-8').splitlines()
        print('sidecar_lines', len(lines))
    print()
