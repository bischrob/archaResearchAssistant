import torch
import pandas as pd
import numpy as np
import umap
import joblib
import pickle
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# === Config ===
embedding_file = "embeddings/embeddings.pkl"
umap_model_file = "embeddings/umap_model_128d.pkl"
reduced_output_file = "embeddings/embeddings_reduced.parquet"
query = "obsidian projectile point"
embedding_dim = 128
similarity_top_n = 10

# === Load model
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Loading embedding model on {device}...")
model = SentenceTransformer("BAAI/bge-m3", device=device)

# === Load full embedding DataFrame
print(f"📂 Loading: {embedding_file}")
df = pd.read_pickle(embedding_file)
df = df.head(1000)
embedding_matrix = np.array(df["embedding"].tolist())
print(f"✅ Loaded {len(df)} embeddings")

# === Train UMAP
print(f"🔧 Training UMAP to reduce to {embedding_dim} dimensions...")
umap_model = umap.UMAP(
    n_neighbors=15,
    n_components=embedding_dim,
    metric="cosine",
    transform_seed=42
).fit(embedding_matrix)

# === Save UMAP model
joblib.dump(umap_model, umap_model_file)
print(f"💾 Saved UMAP model to {umap_model_file}")

# === Save reduced embeddings
reduced = umap_model.embedding_
df_reduced = df.copy()
df_reduced["embedding_umap"] = reduced.tolist()
df_reduced.drop(columns=["embedding"], inplace=True)
df_reduced.to_parquet(reduced_output_file, index=False)
print(f"💾 Saved reduced embeddings to {reduced_output_file}")

# === Embed and reduce the query
print(f"🧠 Encoding and transforming query: '{query}'")
query_embedding = model.encode(
    query,
    batch_size=1,
    convert_to_numpy=True,
    normalize_embeddings=True,
    device=device
)
query_reduced = umap_model.transform([query_embedding])

# === Similarity search in reduced space
print("🔎 Searching...")
reduced_embeddings = np.array(df_reduced["embedding_umap"].tolist())
similarities = cosine_similarity(query_reduced, reduced_embeddings)[0]
df_reduced["similarity"] = similarities

# === Top N results
results = df_reduced.sort_values("similarity", ascending=False).head(similarity_top_n)
print(f"\n🔝 Top {similarity_top_n} Matches:")
print(results[["basenames", "similarity"]].drop_duplicates(subset=["basenames"]))
