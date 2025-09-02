# pip install -U sentence-transformers torch  # (torch will be pulled in automatically on most setups)
from pathlib import Path
import json
import sys

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    sys.exit("Please install: pip install -U sentence-transformers torch")

# ========= CONFIG =========
INPUT_DIR   = Path(r"./java_raw_sample/java_txt")   # folder containing *.txt (one per package)
OUTPUT_JSON = Path(r"./dataset/java_embeddings.json")
RECURSIVE   = False   # set True to include subfolders
BATCH_SIZE  = 16
NORMALIZE   = True    # cosine-friendly unit vectors
# =========================

def load_texts(txt_paths):
    texts, names, used_paths = [], [], []
    for p in txt_paths:
        try:
            s = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[skip] {p.name}: {e}")
            continue
        if not s.strip():
            print(f"[skip-empty] {p.name}")
            continue
        texts.append(s)
        names.append(p.stem)   # pkg name = file name without .txt
        used_paths.append(p)
    return texts, names, used_paths

def main():
    # Collect files
    pattern = "**/*.txt" if RECURSIVE else "*.txt"
    files = sorted(INPUT_DIR.glob(pattern))
    if not files:
        sys.exit(f"No .txt files found under: {INPUT_DIR}")

    # Load model (auto CPU/GPU)
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    records = []
    total = len(files)
    processed = 0

    # Batch over files
    for i in range(0, total, BATCH_SIZE):
        batch_paths = files[i:i+BATCH_SIZE]
        texts, names, used_paths = load_texts(batch_paths)
        if not texts:
            continue

        # Compute embeddings
        embs = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            convert_to_numpy=True,
            normalize_embeddings=NORMALIZE,
            show_progress_bar=False
        )

        for pkg, emb in zip(names, embs):
            records.append({
                "pkg_name": pkg,
                "embedding": emb.tolist()
            })
        processed += len(names)

    # Save JSON array
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)

    print(f"Processed {processed} of {total} files.")
    print(f"Wrote embeddings to: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()

