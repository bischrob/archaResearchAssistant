import os
import sys
import pickle
import multiprocessing
from multiprocessing import Process, set_start_method
import pandas as pd
from tqdm import tqdm
from src.encoder_utils import encode_batch  # no changes needed there

def gpu_worker(device, batches, output_file, completed):
    print(f"[{device}] 🏁 Started worker with {len(batches)} batches assigned")
    output_file = f"embeddings/embeddings_{device.replace(':', '')}.pkl"

    # Count total rows this GPU is responsible for (excluding completed batches)
    remaining_batches = [b for b in batches if b[0] not in completed]
    total_rows = sum(len(batch_df) for _, batch_df in remaining_batches)

    with open(output_file, "ab") as f, tqdm(total=total_rows, desc=f"[{device}]", position=int(device[-1])) as pbar:
        for idx, batch_df in batches:
            if idx in completed:
                continue

            try:
                batch_idx, result = encode_batch(idx, batch_df, device)
                pickle.dump((batch_idx, result), f)
                pbar.update(len(batch_df))  # ✅ Update by number of rows encoded
                pbar.set_postfix(batch=batch_idx)
            except Exception as e:
                print(f"[{device}] ❌ Error in batch {idx}: {e}")



if __name__ == "__main__":
    set_start_method("spawn", force=True)

    # === Config ===
    input_file = "upload.pkl"
    output_file = "embeddings/embeddings.pkl"
    batch_size = 512
    devices = ["cuda:0", "cuda:1", "cuda:2", "cuda:3"]

    # === Load input ===
    with open(input_file, "rb") as f:
        df = pickle.load(f)

    # Ensure 'chunks' is non-empty
    df = df[df["chunks"].str.strip().astype(bool)]

    # Create batches of (batch_idx, batch_df)
    batches = [
        (i, df.iloc[i:i + batch_size])
        for i in range(0, len(df), batch_size)
    ]

    # === Resume support: collect completed batch indices ===
    completed = set()
    if os.path.exists(output_file):
        with open(output_file, "rb") as f:
            try:
                while True:
                    batch_result = pickle.load(f)
                    if isinstance(batch_result, tuple):
                        batch_idx, _ = batch_result
                        completed.add(batch_idx)
                    else:
                        completed.add(len(completed))
            except EOFError:
                pass

    print(f"🚀 Starting embedding with one worker per GPU")
    print(f"🧱 Total batches: {len(batches)} | Already completed: {len(completed)}")
    print(f"🧮 Remaining batches: {len(batches) - len(completed)}")

    # Distribute batches evenly to devices
    from itertools import cycle

    batches_per_gpu = [[] for _ in devices]
    gpu_cycle = cycle(range(len(devices)))  # rotate 0, 1, 2, 3...

    for batch_idx, batch_df in batches:
        if batch_idx not in completed:
            gpu_index = next(gpu_cycle)
            batches_per_gpu[gpu_index].append((batch_idx, batch_df))

    # Spawn one process per GPU
    processes = []
    for i, device in enumerate(devices):
        p = Process(
            target=gpu_worker,
            args=(device, batches_per_gpu[i], output_file, completed)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    print("✅ All batches processed.")
