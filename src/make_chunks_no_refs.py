import os
import re
import json
import spacy
import fitz
from multiprocessing import Pool, cpu_count
from functools import partial

# === Load NLP model ===
nlp = spacy.load("en_core_web_sm")
nlp.max_length = 10_000_000

# === Utility Functions ===
def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def split_into_semantic_chunks(text, max_tokens=5000):
    doc = nlp(text)
    chunks = []
    current_chunk = ""
    current_tokens = 0

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue
        sent_tokens = len(sent_text.split())
        if current_tokens + sent_tokens > max_tokens:
            chunks.append(current_chunk.strip())
            current_chunk = sent_text
            current_tokens = sent_tokens
        else:
            current_chunk += " " + sent_text
            current_tokens += sent_tokens

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def run_parallel(pdf_paths, skip_if_exists, num_workers=None):
    if num_workers is None:
        num_workers = 1
    process_with_flag = partial(process, skip_if_exists=skip_if_exists)
    with Pool(num_workers) as pool:
        pool.map(process_with_flag, pdf_paths)

def process(pdf_path, skip_if_exists=True):
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    json_path = os.path.join("jsons", f"{base_name}.json")
    if skip_if_exists and os.path.exists(json_path):
        print(f"⏭️ Skipping {pdf_path} — JSON already exists.")
        return

    try:
        text = extract_text(pdf_path)
        chunks = split_into_semantic_chunks(text, max_tokens=5000)

        result = {"chunks": chunks}

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ Saved parsed output to {json_path}")
    except Exception as e:
        print(f"❌ Error processing {pdf_path}: {e}")


def create_chunks(pdf_paths, skip_if_exists=True, parallel = False, num_workers = 4):
    os.makedirs("jsons", exist_ok=True)

    if isinstance(pdf_paths,str):
        pdf_paths = [pdf_paths]

    if parallel:
        run_parallel(pdf_paths, skip_if_exists=skip_if_exists, num_workers = num_workers)
    else:
        for pdf_path in pdf_paths:
            process(pdf_path, skip_if_exists=skip_if_exists)
    print("Process completed for " + str(len(pdf_paths)) + "pdfs")

def find_all_pdfs(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                yield os.path.join(dirpath, filename)

def find_all_jsons(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".json"):
                yield os.path.join(dirpath, filename)




