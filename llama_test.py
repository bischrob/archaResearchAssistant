import transformers
import torch
import fitz 
from pathlib import Path

model_id = "meta-llama/Meta-Llama-3.1-8B-Instruct"

pipeline = transformers.pipeline(
    "text-generation",
    model=model_id,
    model_kwargs={"torch_dtype": torch.bfloat16},
    device_map="auto",
)

print(pipeline.model.device)


messages = [
    {"role": "system", "content": "You are a helpful assistant capable of assisting with my research projects"},
    {"role": "user", "content": "Can you help parse text into separate paragraph chunks?"},
]

outputs = pipeline(
    messages,
    max_new_tokens=256,
)
print(outputs[0]["generated_text"][-1].get("content"))


def extract_text(pdf_path):
        """Extracts text from a PDF file."""
        doc = fitz.open(pdf_path)
        return "\n".join(page.get_text() for page in doc)

pdf_path  = '/mnt/e/Paperpile/allPapers/riris2024-FrequentDisturbancesEnhancedResilienceOfPastHumanPopulations.pdf'

text = extract_text(pdf_path)

