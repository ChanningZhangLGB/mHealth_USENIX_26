import os
import re
import json
import time
import tempfile
from typing import Dict, Any, List, Tuple, Union
from openai import OpenAI

# ─── Configuration ─────────────────────────────────────────────────────────────
API_KEY      = "api_key"
INPUT_JSON   = r"/manual_20_neg_300.json"   # your JSON input file
OUTPUT_FILE  = r"/manual_20_neg_300_res.json"
MODEL        = "gpt-4o-mini-2024-07-18"
BATCH_ENDPOINT = "/v1/chat/completions"
POLL_INTERVAL_SECS = 10
# ───────────────────────────────────────────────────────────────────────────────

client = OpenAI(api_key=API_KEY)

PROMPT_TEMPLATE = """
Read the following privacy policy text from the privacy policy.

---------------- start of privacy policy ----------------
{pp_text}
---------------- end of privacy policy ----------------

The requested permission list is: {requested_permission}

Analyze and answer the following two questions for EACH requested permission:
1) Does the privacy policy text explicitly contain rationales specific for each requested permission — i.e., clear explanations of why the app requests each permission and how that permission will be used or handled?
2) If yes, provide the specific sentence(s) from the policy that support your answer.

You MUST respond as a pure JSON ARRAY (no code fences, no extra text). The array should contain one object per permission with keys:
  - "permission": string (one of the requested permissions)
  - "Answer1": "Yes" or "No"
  - "Answer2": string (supporting sentence(s) or "")

Your output MUST:
- begin with '[' and end with ']'
- contain ONLY JSON
- not include trailing commas
"""

# ----------------------------- Utilities --------------------------------------

def load_input_data() -> List[Dict[str, Any]]:
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def make_jsonl_lines(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lines = []
    for rec in records:
        prompt = PROMPT_TEMPLATE.format(
            pp_text="\n".join(rec.get("pp_text", [])),
            requested_permission=rec.get("requested_permission", [])
        )
        line = {
            "custom_id": rec.get("apkname", "unknown_apk"),
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": {
                "model": MODEL,
                "temperature": 0.2,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        }
        lines.append(line)
    return lines

def write_temp_jsonl(lines: List[Dict[str, Any]]) -> str:
    fd, path = tempfile.mkstemp(prefix="openai-batch-", suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as w:
        for obj in lines:
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path

def create_batch(input_file_id: str) -> str:
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint=BATCH_ENDPOINT,
        completion_window="24h"
    )
    return batch.id

def poll_batch(batch_id: str) -> Dict[str, Any]:
    TERMINAL = {"completed", "failed", "expired", "cancelled"}
    while True:
        b = client.batches.retrieve(batch_id)
        status = b.status
        print(f"[BATCH] {batch_id} status = {status}")
        if status in TERMINAL:
            return b.to_dict()
        time.sleep(POLL_INTERVAL_SECS)

def download_file(file_id: str) -> List[str]:
    content = client.files.content(file_id)
    data = getattr(content, "text", None)
    if data is None:
        data = content.read().decode("utf-8")
    return data.splitlines()

# ---- JSON repair helpers ------------------------------------------------------

CODE_FENCE_RE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL | re.IGNORECASE)

def strip_code_fences(text: str) -> str:
    # If fenced, prefer the first fenced block; else return original.
    m = CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()

def extract_json_array(text: str) -> str:
    """
    Try to extract a JSON array substring. We look for the FIRST '['
    and the LAST ']' and return that slice if it parses or looks plausible.
    """
    s = text
    start = s.find('[')
    end = s.rfind(']')
    if start != -1 and end != -1 and end > start:
        return s[start:end+1].strip()
    return s

def normalize_quotes_commas(text: str) -> str:
    # replace smart quotes
    s = (text
         .replace("“", '"').replace("”", '"')
         .replace("’", "'"))
    # remove trailing commas before ] or }
    s = re.sub(r",(\s*[\]\}])", r"\1", s)
    return s

def try_parse_json_array(text: str) -> Union[List[Any], None]:
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
    except json.JSONDecodeError:
        return None
    return None

def coerce_to_json_array(raw: str) -> Tuple[Union[List[Any], None], str]:
    """
    Try multiple strategies to coerce model output into a JSON array.
    Returns (parsed_json_or_none, cleaned_text_used).
    """
    candidates = []

    # 1) As-is
    candidates.append(raw.strip())

    # 2) Strip code fences
    stripped = strip_code_fences(raw)
    candidates.append(stripped)

    # 3) Extract array slice and try
    array_slice = extract_json_array(stripped)
    candidates.append(array_slice)

    # 4) Normalize quotes and commas on slice
    normalized = normalize_quotes_commas(array_slice)
    candidates.append(normalized)

    # Try them in order
    for c in candidates:
        parsed = try_parse_json_array(c)
        if parsed is not None:
            return parsed, c

    return None, normalized

def validate_items(items: List[Any]) -> List[Dict[str, Any]]:
    """Keep only well-formed objects; coerce Answer2 to string."""
    clean = []
    for it in items:
        if not isinstance(it, dict):
            continue
        perm = it.get("permission")
        a1 = it.get("Answer1")
        a2 = it.get("Answer2", "")
        if isinstance(perm, str) and a1 in {"Yes", "No"}:
            clean.append({
                "permission": perm,
                "Answer1": a1,
                "Answer2": "" if a2 is None else str(a2)
            })
    return clean

# -----------------------------------------------------------------------------

def parse_batch_output(output_lines: List[str]) -> List[Dict[str, Any]]:
    results = []
    for raw in output_lines:
        obj = json.loads(raw)
        custom_id = obj.get("custom_id")
        error = obj.get("error")
        if error:
            results.append({"apkname": custom_id, "error": error})
            continue

        body = (((obj.get("response") or {}).get("body")) or {})
        choices = body.get("choices") or []
        if not choices:
            results.append({"apkname": custom_id, "error": "no choices"})
            continue

        content = (choices[0].get("message") or {}).get("content") or ""

        # Try to coerce to a JSON array
        parsed, cleaned = coerce_to_json_array(content)
        if parsed is None:
            results.append({
                "apkname": custom_id,
                "error": "invalid JSON",
                "raw": content[:1000]  # keep more raw for debugging
            })
            continue

        # Validate/clean individual items
        cleaned_items = validate_items(parsed)
        if not cleaned_items:
            results.append({
                "apkname": custom_id,
                "error": "parsed but no valid items",
                "raw": cleaned[:1000]
            })
        else:
            results.append({
                "apkname": custom_id,
                "analysis": cleaned_items
            })
    return results

# ----------------------------- Main -------------------------------------------

def main():
    records = load_input_data()
    lines = make_jsonl_lines(records)
    jsonl_path = write_temp_jsonl(lines)
    print(f"[INPUT] JSONL ready: {jsonl_path}")

    with open(jsonl_path, "rb") as f:
        up = client.files.create(file=f, purpose="batch")
    input_file_id = up.id
    print(f"[UPLOAD] input_file_id = {input_file_id}")

    batch_id = create_batch(input_file_id)
    print(f"[CREATE] batch_id = {batch_id}")

    final = poll_batch(batch_id)
    status = final.get("status")
    print(f"[DONE] Batch {batch_id} → {status}")

    output_file_id = final.get("output_file_id")
    if not output_file_id:
        outputs = final.get("output_files") or []
        if outputs:
            output_file_id = outputs[0].get("id")
    if not output_file_id:
        raise RuntimeError("No output file id found on batch object.")

    out_lines = download_file(output_file_id)
    parsed_results = parse_batch_output(out_lines)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(parsed_results, out, indent=2, ensure_ascii=False)

    print(f"\nAll done! Wrote {len(parsed_results)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
