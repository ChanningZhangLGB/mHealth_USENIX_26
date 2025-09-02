import os
import re
import time
import json
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

# ─── CONFIG ────────────────────────────────────────────────────────────────
API_KEY     = "api_key"
MODEL       = "claude-sonnet-4-20250514"
INPUT_DIR   = r"./dataset/java_txt"      # folder containing your .txt files
OUTPUT_FILE = r"./artifacts/llm_results.json"
MAX_TOKENS  = 1024
POLL_DELAY  = 5  # seconds between status checks
# ─────────────────────────────────────────────────────────────────────────────

client = anthropic.Anthropic(api_key=API_KEY)

# 1) Prompt template goes entirely in the user message
PROMPT_TEMPLATE = """
You are given the contents of a Java source file below.

------------ start of code ------------
{code}
------------ end of code ------------

Please analyze and answer these two questions:
1. Does this code implement an activity that displays app's privacy policy when the user clicks on the privacy policy link in the Health Connect permissions screen? Answer1:[Yes/No]
2. If yes, explain the code that implements the activity. Answer2:[Explanation] 

and respond *only* with a JSON object with keys:
  - "Answer1": "Yes" or "No"
  - "Answer2": a brief explanation (or empty string if Answer1 is "No")

Example of the ONLY acceptable response format:

{{
  "Answer1": "Yes",
  "Answer2": "This activity registers a click listener on the privacy-policy link..."
}}
"""

def sanitize_id(fname: str) -> str:
    # strip extension, replace invalid chars, truncate
    base = os.path.splitext(fname)[0]
    clean = re.sub(r'[^A-Za-z0-9_-]', '_', base)
    return clean[:64] or "_"

# 2) Prepare batch requests
batch_requests = []
for fname in sorted(os.listdir(INPUT_DIR)):
    if not fname.lower().endswith(".txt"):
        continue
    code = open(os.path.join(INPUT_DIR, fname), encoding="utf-8").read()
    user_prompt = PROMPT_TEMPLATE.format(code=code)
    batch_requests.append(
        Request(
            custom_id=sanitize_id(fname),
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": user_prompt}],
            )
        )
    )

# 3) Submit batch
batch = client.messages.batches.create(requests=batch_requests)
batch_id = batch.id
print(f"Batch submitted: {batch_id}")
print(f"Initial request counts: {batch.request_counts}")

# 4) Poll until complete
while True:
    status = client.messages.batches.retrieve(batch_id)
    counts = status.request_counts
    print(f"processing={counts.processing}, succeeded={counts.succeeded}, errored={counts.errored}")
    if status.processing_status == "ended":
        break
    time.sleep(POLL_DELAY)

# 5) Collect and parse results
entries = list(client.messages.batches.results(batch_id))
# Convert each Pydantic model to a dict
output = [entry.model_dump() for entry in entries]

# 6) Write out the JSON array
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print(f"Completed: saved {len(output)} batch results to {OUTPUT_FILE}")