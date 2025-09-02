import os
import requests
from pymongo import MongoClient
import pandas as pd
import logging
from sklearn.metrics import accuracy_score, recall_score, precision_score, f1_score
from tqdm import tqdm
import ast

# === Parameters ===
root_folder = "rationale_java"
ollama_url = "http://localhost:11434/api/generate"
model = "codellama:34b"

neg_code = """    @Override // androidx.fragment.app.j, androidx.activity.h, androidx.core.app.f, android.app.Activity
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(f.f13399a);
        View findViewById = findViewById(e.f13398a);
        AbstractC1819s.h(findViewById, "findViewById(...)");
        WebView webView = (WebView) findViewById;
        webView.setWebViewClient(new WebViewClient());
        webView.getSettings().setJavaScriptEnabled(true);
        webView.loadUrl("https://trainwell.net/privacy-policy");
        webView.setWebViewClient(new a());
    }"""
pos_code = """
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = new WebView(this);
        webView.setWebViewClient(new a());
        webView.loadUrl("https://developer.android.com/health-and-fitness/guides/health-connect/develop/get-started");
        setContentView(webView);
    }
"""
def build_fewshot_prompt(pos_code, neg_code, code):
    return (
        "Analyze the following Java code examples and answer these questions:"
        "Example 1 (Positive Case):"
        f"{neg_code}"
        "1. Does this code implement an activity that displays the app's privacy policy when the user clicks on the privacy policy link in the Health Connect permissions screen?"  
        "Answer: Yes"  
        "2. If yes, explain the code that implements the activity."  
        "Answer: This code implement the activity that includes a WebView that loads the privacy policy URL."
        "Example 2 (Negative Case):"
        f"{pos_code}"
        "1. Does this code implement an activity that displays the app's privacy policy when the user clicks on the privacy policy link in the Health Connect permissions screen?" 
        "Answer: No"  
        "2. If yes, explain the code that implements the activity."  
        "Answer: N/A"
        "Now, analyze the following Java code:"
        f"{code}"
        "1. Does this code implement an activity that displays the app's privacy policy when the user clicks on the privacy policy link in the Health Connect permissions screen?"  
        "Answer: [Yes/No]"  
        "2. If yes, explain the code that implements the activity. " 
        "Answer: [Explanation]"
        )

def build_prompt(code, xml):
    return (
        "Analyze the following decleared activity and the java code and answer these questions:" 
        "1. Does this code implement an activity that displays app's privacy policy when the user clicks on the privacy policy link in the Health Connect permissions screen? Answer:[Yes/No]"
        "2. If yes, explain the code that implements the activity. Answer:[Explanation] \n\n" 
        f"Declared activity in manifest: {xml}\n Java code:```\n{code}\n```"
    )

# === Recursively find Java files ===
def find_java_files(base_dir):
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".java"):
                yield os.path.join(root, f)

# === Query Code LLaMA via Ollama HTTP API ===
def query_ollama(model, prompt):
    response = requests.post(ollama_url, json={
        "model": model,
        "prompt": prompt,
        "stream": False
    })
    if response.ok:
        return response.json()["response"]
    else:
        return f"[ERROR] {response.status_code}: {response.text}"

def main():
    logging.basicConfig(
        filename="logs/codellama_java.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    # === Main logic ===
    client = MongoClient("mongodb://localhost:27017/")
    db = client["hc_pp"]
    collection = db["codellama_java_fewshot"]

    df = pd.read_csv('package_process_labeled_N_PP_show.csv')
    neg_list = df["PackageName"].dropna().tolist()

    df = pd.read_csv('package_process_labeled_P.csv')
    pos_list = df["PackageName"].dropna().tolist()

    df = pd.read_csv('no_interact_packages_116.csv')
    block_list = df["PackageName"].dropna().tolist()
    assert(len(block_list) == 116)

    gt, predict = [], []
    app_idx = 0
    for java_path in find_java_files(root_folder):
        relative_path = os.path.relpath(java_path, root_folder)
        packagename = relative_path.split(os.sep)[0]  # first-level subfolder
        app_idx += 1

        if packagename in block_list:
            logging.info(f"[{app_idx}] Skip non-interaction app: {packagename}")
            continue
        exists = collection.count_documents({"packagename": packagename}) > 0
        if exists:
            logging.info(f"[{app_idx}] ✅ Found document for: {packagename}")
            continue
        
        # print(f"\n🔍 Analyzing: {java_path}")
        logging.info(f"[{app_idx}] Analyzing {java_path}")

        with open(java_path, "r", encoding="utf-8") as f:
            java_code = f.read()
        with open(f"app_candidates_manifests_RA/{packagename}.txt", "r", encoding="utf-8") as f:
            xml_code = f.read().replace("\n\n", "\n")

        prompt = build_fewshot_prompt(pos_code, neg_code, java_code)
        llm_response = query_ollama(model, prompt)

        llm_label = -1
        if "Yes" in llm_response:
            llm_label = 0
        elif "No" in llm_response:
            llm_label = 1
        else:
            # struggling to answer the first question
            llm_label = -1

        predict.append(llm_label)
        if packagename in neg_list:
            gt.append(0)
        elif packagename in pos_list:
            gt.append(1)
        else:
            gt.append(-1)
            logging.info(f"❌ Not found {packagename} in csv file")

        doc = {
            "packagename": packagename,
            "codellama_response": llm_response,
            "codellama_binary_label": llm_label,
            "binary_gt": gt[-1]
        }


        collection.insert_one(doc)
    
    client.close()
    accuracy = accuracy_score(gt, predict)
    logging.info(f"Total {len(gt)} apps, with {accuracy*100}% accuracy")


def measure_accuracy():
    # Connect to MongoDB
    client = MongoClient("mongodb://localhost:27017/")
    db = client["hc_pp"]
    collection = db["codellama_java_xml"]
    check_collection = db["codellama_java_xml"]
    cursor = check_collection.find({ "codellama_binary_label": { "$ne": None }, "binary_gt": { "$ne": None } })
    valid_pkg = [doc["packagename"] for doc in cursor]
    print(f"Total {len(valid_pkg)} apps")

    # Initialize counters
    total = 0
    correct = 0
    predict_list, gt_list = [], []
    # Iterate through all documents
    for doc in collection.find({ "codellama_binary_label": { "$ne": None }, "binary_gt": { "$ne": None } }):
        if doc['packagename'] not in valid_pkg:
            continue
        label = doc.get("codellama_binary_label")
        gt = doc.get("binary_gt")
        # print(f"label = {label}, gt = {gt}")
        if label in [-1, 0, 1] and gt in [-1, 0, 1]:
            total += 1
            gt_list.append(gt)
            if label == -1:
                if gt == 1:
                    predict_list.append(0)
                else:
                    predict_list.append(1)
            else:
                predict_list.append(label)
       
            
    # Calculate and print accuracy
    if total > 0:
        accuracy = correct / total
        print(f"Accuracy: {accuracy:.4f} ({correct}/{total} correct)")
    else:
        print("No valid records found.")
    
    client.close()
    acc = accuracy_score(predict_list, gt_list)
    rec = recall_score(predict_list, gt_list)
    pre = precision_score(predict_list, gt_list)
    f1 = f1_score(predict_list, gt_list)
    print(f"Accuracy: {acc}   Recall: {rec}   Precision: {pre}   F1: {f1}")


import csv 

def db2csv():
    client = MongoClient("mongodb://localhost:27017/")  # Update with your MongoDB URI
    db = client["hc_pp"]
    collection = db["codellama_java"]
    total_docs = collection.count_documents({})

    with open("output/codallama_java_v1.csv", "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["packagename", "groundtruth", "prediction", "reasoning"])

        for doc in tqdm(collection.find(), total=total_docs, desc="Processing records"):
            gt = doc.get("binary_gt", "")
            label = doc.get("codellama_binary_label", "")
            reasoning = doc.get("codellama_response", "")
            writer.writerow([doc['packagename'], gt, label, reasoning])


    client.close()

if __name__ == "__main__":
    main()
    measure_accuracy()
    db2csv()
