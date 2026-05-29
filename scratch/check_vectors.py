import pickle
import os

meta_path = "/Users/igorvasin/freelance-2026/ai-eggs/data/vector_index/metadata.pkl"

if os.path.exists(meta_path):
    with open(meta_path, "rb") as f:
        metadata = pickle.load(f)
        print(f"Total entries: {len(metadata)}")
        for i, entry in enumerate(metadata):
            text = entry.get("text", "")
            if "16 апреля" in text or "2026-04-16" in text:
                print(f"[{i}] {text[:100]}...")
else:
    print("Metadata file not found.")
