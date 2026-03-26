import time
from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.retrieval import contextual_retrieve

q='Hohokam projectile points'
start=time.time(); print('settings...')
settings=Settings(); print('settings', time.time()-start)
start=time.time(); print('graphstore...')
store=GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
print('graphstore', time.time()-start)
start=time.time(); print('retrieve...')
rows=contextual_retrieve(store,q,3,limit_scope='papers',chunks_per_paper=1)
print('retrieve', time.time()-start, 'rows', len(rows))
store.close()
for r in rows[:3]:
    print(r.get('article_title'), r.get('paper_score'))
