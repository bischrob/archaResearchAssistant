from pathlib import Path
p = Path('/mnt/c/Users/rjbischo/Zotero/storage/S3P5M3I3/Bubeck_2023_Sparks_of_AGI.references.txt')
lines = p.read_text(encoding='utf-8').splitlines()
print('count', len(lines))
print('tail1', lines[-3])
print('tail2', lines[-2])
print('tail3', lines[-1])
