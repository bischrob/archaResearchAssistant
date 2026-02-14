import torch
from sentence_transformers import SentenceTransformer
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# === Config ===
query = "obsidian projectile point"
use_fp16 = True  # set to False if you run into problems
threshold = 0.4  # Only return results with similarity > this

# === Load model
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if use_fp16 and torch.cuda.is_available() else torch.float32

print(f"🚀 Loading BGE-M3 model on {device} ({dtype})...")
model = SentenceTransformer("BAAI/bge-m3", device=device)
if dtype == torch.float16:
    model = model.half()

# === Embed query
print(f"🧠 Encoding query: '{query}'")
query_embedding = model.encode(
    query,
    batch_size=1,
    convert_to_numpy=True,
    normalize_embeddings=True,
    device=device
)

# === Load all embeddings from embeddings.pkl
print("📂 Loading embeddings...")
df = pd.read_pickle("embeddings/embeddings.pkl")
print(f"✅ Loaded {len(df)} records.")

df = df[['basenames','embedding']].copy()

# === Convert embedding column to NumPy matrix
embedding_matrix = np.array(df["embedding"].tolist())

# === Compute cosine similarity
similarities = cosine_similarity([query_embedding], embedding_matrix)[0]
df["similarity"] = similarities

# === Filter by threshold and sort
df_results = df[df["similarity"] >= threshold].sort_values(by="similarity", ascending=False)

# === Output
print(f"🔍 Found {len(df_results)} matches above threshold {threshold}")
print(df_results[["index", "file_id", "similarity"]].head(10))  # show top 10 results

# Optionally save
# df_results.to_csv("search_results.csv", index=False)

