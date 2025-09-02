import os
import json
import time
from openai import OpenAI

# ─── Configuration ─────────────────────────────────────────────────────────────
API_KEY      = "api_key"
INPUT_FOLDER = r"./dataset/java_txt"      # folder containing your .txt files
OUTPUT_FILE  = r"./artifacts/llm_results.json"
MODEL        = "openAI_model"
# Candidate models:
# o4-mini    
# gpt-5-mini  
# gpt-5-nano  
# ────────────────────────────────────────────────────────────────────────────────

client = OpenAI(api_key=API_KEY)

# We ask GPT to return *only* a JSON object with the two fields we need.
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

def classify_text(code: str) -> dict:
    """Send the code to GPT and parse the JSON response."""
    prompt = PROMPT_TEMPLATE.format(code=code)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    ).to_dict()

    # Extract the assistant’s content
    content = resp["choices"][0]["message"]["content"].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from model response:\n{content}") from e

def main():
    results = []

    for fn in sorted(os.listdir(INPUT_FOLDER)):
        if not fn.lower().endswith(".txt"):
            continue

        path = os.path.join(INPUT_FOLDER, fn)
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()

        try:
            answer = classify_text(code)
            # attach the filename so we know which is which
            answer["fileName"] = fn
            results.append(answer)
            print(f"[OK]  {fn} → {answer['Answer1']}")
        except Exception as err:
            print(f"[ERR] {fn}: {err}")

        # avoid hammering the API
        time.sleep(1)

    # Write all results to one JSON array
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)

    print(f"\nAll done!  Wrote {len(results)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
