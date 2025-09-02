import os
import json
import time
import requests
import re

# -------- Prompt ----------
prompt_template = '''
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
'''

system_message = (
    "You are an expert in analyzing Java code for Android applications. "
    "Carefully inspect the provided Java source and answer concisely in JSON."
)

API_URL = "https://api.aimlapi.com/v1/chat/completions"
API_KEY = "api_key"

def classify_text(code: str) -> dict:
    """Send code to the model and return a dict with Answer1/Answer2."""
    formatted_prompt = prompt_template.format(code=code)

    payload = {
        "model": "deepseek/deepseek-r1",
        "temperature": 0,
        "top_p": 1,
        "n": 1,
        "max_tokens": 2048,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": formatted_prompt}
        ],
        "stream": False,
        # If supported by your endpoint, uncomment for stricter JSON:
        # "response_format": {"type": "json_object"}
    }

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload
    )
    resp.raise_for_status()
    data = resp.json()

    content = ""
    if data.get("choices"):
        content = data["choices"][0]["message"].get("content", "")

    # Try strict JSON parse; if that fails, extract the first {...} block.
    try:
        return json.loads(content)
    except Exception:
        match = re.search(r'\{.*\}', content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        # Fallback empty structure to keep pipeline running
        return {"Answer1": "No", "Answer2": ""}

def process_txt_folder(input_folder: str, output_json_path: str):
    """Read every .txt file, classify, and write a single JSON array."""
    results = []
    files = sorted([f for f in os.listdir(input_folder) if f.lower().endswith(".txt")])

    for fname in files:
        fpath = os.path.join(input_folder, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()

            res = classify_text(code)
            # Ensure keys exist
            ans1 = res.get("Answer1", "No")
            ans2 = res.get("Answer2", "") if isinstance(res.get("Answer2", ""), str) else ""
            results.append({"Answer1": ans1, "Answer2": ans2, "fileName": fname})

            print(f"Processed {fname}")
        except Exception as e:
            print(f"Error processing {fname}: {e}")
        time.sleep(1)  # gentle pacing

    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as out:
        json.dump(results, out, ensure_ascii=False, indent=2)
    print(f"Wrote {len(results)} items to {output_json_path}")

def main():
    # Set these to your folders:
    input_folder = r"./dataset/java_txt"   
    output_json  = r"./artifacts/llm_results.json"    
    process_txt_folder(input_folder, output_json)

if __name__ == "__main__":
    main()
