# encoder_utils.py

import os
import torch
from sentence_transformers import SentenceTransformer
import gc


def encode_batch(batch_idx, batch_df, device="cuda:0", encode_batch_size=16):
    """
    Encode a batch of text chunks from a pandas DataFrame using SentenceTransformer.
    
    Args:
        batch_idx (int): Index of the batch.
        batch_df (pandas.DataFrame): DataFrame containing 'chunks' and 'file_id' columns.
        device (str): CUDA device string (e.g., "cuda:0").
    
    Returns:
        tuple: (batch_idx, list of dicts with 'index', 'file_id', 'embedding')
    """
    # Limit visibility to the assigned GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = device.split(":")[-1]

    print(f"🧠 Batch {batch_idx}: Loading model on {device}...")

    # Load model on the assigned device
    model = SentenceTransformer("BAAI/bge-m3")
    model.to(torch.device("cuda"))

    print(f"✅ Batch {batch_idx}: Model loaded, encoding {len(batch_df)} texts.")

    # Extract texts
    texts = batch_df["chunks"].tolist()

    # Generate embeddings
    embeddings = model.encode(
        texts,
        batch_size=encode_batch_size,  # not hardcoded anymore!
        convert_to_numpy=True,
        normalize_embeddings=True,
        device="cuda"
    )

    # Combine embeddings with metadata
    results = [
        {
            "index": int(row.Index),         # row.Index comes from itertuples()
            "file_id": row.file_id,
            "embedding": embedding
        }
        for row, embedding in zip(batch_df.itertuples(), embeddings)
    ]

    print(f"📦 Batch {batch_idx}: Done encoding.")

    # Clear variables explicitly
    del model, embeddings, texts, batch_df

    # Clear unused memory from Python and PyTorch
    gc.collect()
    torch.cuda.empty_cache()

    return batch_idx, results
