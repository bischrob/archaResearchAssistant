import pickle
import os
import glob
import pandas as pd
from tqdm import tqdm

# === Config ===
input_dir = "embeddings"
output_file = "embeddings/embeddings.pkl"
output_format = "pkl"

# === Find all per-GPU pickle files ===
files = sorted(glob.glob(os.path.join(input_dir, "embeddings_cuda*.pkl")))

print(f"📂 Found {len(files)} embedding files:")
for f in files:
    print(f"  - {f}")

# === Load all batches into one flat list ===
all_records = []

for fpath in files:
    with open(fpath, "rb") as f:
        try:
            while True:
                batch = pickle.load(f)
                if isinstance(batch, tuple):
                    _, records = batch
                else:
                    records = batch
                all_records.extend(records)
        except EOFError:
            pass
        except Exception as e:
            print(f"❌ Failed to read {fpath}: {e}")

print(f"✅ Loaded {len(all_records)} total embedding rows.")

# === Convert to DataFrame and sort by index (optional) ===
df = pd.DataFrame(all_records)
df.sort_values("index", inplace=True)
pdfs = pd.read_pickle("pdfs.pkl")
pdfs = pdfs[["file_id","basename"]].copy()
df = df.merge(pdfs, on="file_id", how="left")

# === Save to output ===
if output_format == "parquet":
    df.to_parquet(output_file, index=False)
elif output_format == "pkl":
    df.to_pickle(output_file)
else:
    raise ValueError("Unsupported output format")

print(f"✅ Merged embeddings saved to: {output_file}")

