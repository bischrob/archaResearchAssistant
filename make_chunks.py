import os
import re
import json
import spacy
import fitz
import torch
import transformers
from math import ceil
from sentence_transformers import SentenceTransformer, util
from transformers import AutoTokenizer

# === Load NLP + Models ===
nlp = spacy.load("en_core_web_sm")

model_id = "meta-llama/Meta-Llama-3.1-8B-Instruct"
model_name = "BAAI/BGE-M3"

model = SentenceTransformer(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_id)

pipeline = transformers.pipeline(
    "text-generation",
    model=model_id,
    tokenizer=tokenizer,
    model_kwargs={"torch_dtype": torch.bfloat16},
    device_map="auto",
)
print("🧠 LLaMA device:", pipeline.model.device)


# === Utility Functions ===
def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def split_into_semantic_chunks(text, max_tokens=2000):
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


def chunk_text_by_tokens(text, tokenizer, max_tokens=7000):
    words = text.split()
    chunks = []
    current_chunk = []

    for word in words:
        current_chunk.append(word)
        encoded = tokenizer(" ".join(current_chunk), return_tensors="pt", truncation=False, add_special_tokens=False)
        if encoded.input_ids.shape[1] > max_tokens:
            current_chunk.pop()
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def parse_references_with_llama_chunks_batched(
    references_text,
    pipeline,
    tokenizer,
    max_tokens=1000,
    chunk_token_limit=7000,
    batch_size=4
):
    chunks = chunk_text_by_tokens(references_text, tokenizer, max_tokens=chunk_token_limit)
    all_references = []
    reference_like_text = []

    message_batches = []
    chunk_lookup = []  # Keep track of which original chunk goes with which message

    for chunk in chunks:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that parses references from academic text. "
                    "If the input text *is* a list of references, split each citation onto a new line. "
                    "Merge all parts of the citation (author, title, year, etc.) into one line per reference. "
                    "⚠️ If the input is NOT a list of references (just regular text), respond with:\n"
                    "**NOT_REFERENCES: <reason or original text>**"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Split the following text into citations if it's a reference section. "
                    "If it's not a reference section, return NOT_REFERENCES:\n\n"
                    f"{chunk}"
                ),
            },
        ]
        message_batches.append(messages)
        chunk_lookup.append(chunk)

    for i in range(0, len(message_batches), batch_size):
        batch = message_batches[i:i + batch_size]
        chunk_batch = chunk_lookup[i:i + batch_size]
        print(f"🚀 Processing reference batch {i//batch_size + 1}/{ceil(len(message_batches)/batch_size)}")

        results = pipeline(batch, max_new_tokens=max_tokens)

        for result, original_chunk in zip(results, chunk_batch):
            assistant_response = ""

            # Case 1: result is a dict with 'generated_text' (standard HuggingFace pipeline output)
            if isinstance(result, dict):
                output = result.get("generated_text", "")

            # Case 2: result is a list (unexpected, but possible in some models)
            elif isinstance(result, list):
                output = result  # treat as is

            # Case 3: anything else
            else:
                output = result

            # Now process the output
            if isinstance(output, list):
                # Chat format — look for assistant message
                for msg in output:
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        assistant_response = msg.get("content", "").strip()
                        break
            elif isinstance(output, dict):
                # Possibly already a single assistant message
                assistant_response = output.get("content", "").strip()
            elif isinstance(output, str):
                # Plain string output
                assistant_response = output.strip()
            else:
                print("⚠️ Unexpected LLaMA output format:")
                print(type(output), "\n", str(output))
                assistant_response = ""


            if assistant_response.lower().startswith("not_references"):
                print("⚠️ Chunk marked as NOT_REFERENCES — adding to reference_like_text")
                reference_like_text.append(original_chunk.strip())
                continue

            # Otherwise treat as reference lines
            references = [
                line.strip("0123456789.- ").strip()
                for line in assistant_response.splitlines()
                if line.strip() and not line.lower().startswith("not_references")
            ]
            all_references.extend(references)

    return all_references, reference_like_text


def find_references_section(text, model, similarity_threshold=0.5, max_tokens=6000):
    regex = re.compile(r"\b(references|bibliography|literature cited|works cited)\b", re.IGNORECASE)
    match = regex.search(text)
    if match:
        split_index = match.start()
        main_text = text[:split_index].strip()
        references_text = text[split_index:].strip()
        return main_text, references_text

    query = "This section lists all the references or works cited at the end of an academic article."
    chunks = split_into_semantic_chunks(text, max_tokens=max_tokens)
    chunk_embeddings = model.encode(chunks, convert_to_tensor=True)
    query_embedding = model.encode(query, convert_to_tensor=True)

    scores = util.cos_sim(query_embedding, chunk_embeddings)[0]
    best_score = float(scores.max())
    best_idx = int(scores.argmax())

    if best_score >= similarity_threshold:
        references_text = chunks[best_idx]
        main_text = text.replace(references_text, "").strip()
        return main_text, references_text

    return text, None


def process(pdf_path, skip_if_exists=True):
    os.makedirs("jsons", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    json_path = os.path.join("jsons", f"{base_name}.json")

    if skip_if_exists and os.path.exists(json_path):
        print(f"⏭️ Skipping {pdf_path} — JSON already exists.")
        return

    text = extract_text(pdf_path)
    main_text, references_text = find_references_section(text, model)
    main_chunks = split_into_semantic_chunks(main_text)

    if references_text:
        parsed_references, reference_like_text = parse_references_with_llama_chunks_batched(
            references_text, pipeline, tokenizer
        )
    else:
        parsed_references = []
        reference_like_text = []

    result = {
        "main_chunks": main_chunks,
        "references": parsed_references,
        "reference_like_text": reference_like_text
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved parsed output to {json_path}")



def find_all_pdfs(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                yield os.path.join(dirpath, filename)


# === Run on All PDFs ===
pdf_root = "pdfs"
for pdf_file in find_all_pdfs(pdf_root):
    print(f"📄 Processing: {pdf_file}")
    try:
        process(pdf_file)
    except Exception as e:
        print(f"❌ Error processing {pdf_file}: {e}")
