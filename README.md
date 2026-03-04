# An Empirical Study of Privacy Policy Display Compliance in Health Connect Apps

Health Connect (HC) is Google’s new Android platform layer that lets mobile‑health (mHealth) apps exchange sensitive health data while giving users fine‑grained control. To make that sharing transparent, every HC‑integrating app must provide a dedicated *privacy‑rationale* Activity explaining why permissions are needed and how data will be handled.

This repository contains the artifacts, code, and datasets for the **first large‑scale compliance audit** of those requirements. We analysed **673 real‑world mHealth APKs** using a pipeline that blends automated UI exploration, static code analysis, and privacy policy disclosure investigation. Our study shows that **54.8 % of apps either omit or incorrectly implement the mandated dialog**, **code-level detection framework can achieve up to 0.879 accuracy**, and that **76.3 % of privacy‑policy texts fail to justify the requested permissions**.

## Table of Contents

* [How to Use](#how-to-use)

  * [Setup](#setup)
  * [Usage](#usage)
  

## How to Use

### Setup

Install the required libraries:

```bash
pip install -r requirements.txt
```

### Usage

#### RQ1 UI Compliance Testing

*RQ1* contains PowerShell scripts to automate UI testing of APKs and capture screenshots of the **Health Connect permission rationale dialog** and an input example. The scripts are intended to be run inside the Android Studio terminal (or any shell where `adb` is available in the PATH).

| sub‑folder        | contents                                                                                      |
| ----------------- | --------------------------------------------------------------------------------------------- |
| `RQ1/UI_test_script` | PowerShell scripts to automate UI testing to capture screenshots. It installs each APK, exercises the UI, and captures screenshots of the Health Connect permission rationale dialog.     |
| `RQ1/input_sample`   | an input json file example for running the scripts.                    |

Running the script

  ```bash
  cd RQ1/UI_test_scrip

  ./UI_testing_fully_automatic.ps1
         
  ./UI_testing_semi_automatic.ps1
  ```

#### 2. RQ2 ML/LLM-based Code-level Accessibility Detection

*RQ2* contains two approaches for identifying whether an app correctly implements the required *privacy-rationale* Activity at the code level.

| Sub-folder  | Purpose |
|-------------|---------|
| **`RQ2/ml`**  | Traditional machine-learning classifiers (`lr.py`, `rf.py`, `svm.py`) trained on static code embeddings. The embeddings are pre-computed and provided in `HC_apps_embeddings_GT.json`. The file `encode.py` shows the encoding method. |
| **`RQ2/llm`** | Scripts that query large-language models to reason over raw Java source code implementing rationale activities. Includes `openAI_api_query.py`, `claude_api_call.py`, `deepseekR1_api_call.py`, and `codellama_local.py`. |

Input examples are provided in both folders:  
- **ML**: `RQ2/ml/HC_apps_embeddings_GT.json`  
- **LLM**: `RQ2/llm/input_sample/`  

* ML‑based detection
  
Running an experiment

  ```bash
  cd RQ2/ml/model_train

  # Run one of the classifiers:

  python lr.py   # Logistic Regression

  python rf.py   # Random Forest

  python svm.py  # Support Vector Machine
  ```
  
  Each script automatically loads the pre‑computed embeddings, fits the model, prints accuracy / F1 / AUC to stdout, and writes predictions to `pred_<model>.csv`.

* LLM‑based detection

`RQ2/LLM_based_detection/llm.py` reads **rationale Java source files**. These input archives are hosted on our [project website](https://sites.google.com/view/privacyinmhealth/datasets) — download them and point the script to the extracted folders:

Running an experiment
```bash
cd RQ2/llm/llm_query

# Run one of the query scripts:

python claude_api_call.py

python openAI_api_query.py

python deepseekR1_api_call.py

python codellama_local.py
```

The script streams model thoughts to the console and saves a JSON containing per‑app verdicts. Feel free to tweak the prompt or use a different API endpoint.


#### 3. RQ3 Permission-Clarity & Privacy-Policy Disclosure Analysis

*RQ3* provides scripts and examples for analyzing **permission clarity** and **privacy-policy disclosure** using large language models (LLMs). Specifcially, the Gemma-3 pipeline demonstrates how to process **both text and image inputs** for policy analysis.

| Sub-folder        | Contents                                                                 |
|-------------------|---------------------------------------------------------------------------|
| `RQ3/Gemma-3`     | Examples and scripts demonstrating analysis on both text and image input |
| `RQ3/gpt-4o-mini` | Processed examples and scripts for running lightweight GPT-4o-mini        |



Running the sample analysis

```bash
cd RQ3

python RQ3/Gemma-3/llm_analysis.py            # try gemma-3

pythoy RQ3/gpt-4o-mini/llm_analysis.py        # try gpt-4o-mini
```


Grab the complete HC‑compatible dataset from our [project website](https://sites.google.com/view/privacyinmhealth/datasets) and run the experiment to produce the JSON replicates the disclosure‑analysis numbers reported in Section 4 of the paper.


### Contributing

If you’d like to contribute, please open an issue or pull request.

### License

This project is licensed under the Apache 2.0 License – see the `LICENSE` file for details.
