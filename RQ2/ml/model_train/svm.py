# pip install scikit-learn joblib pandas
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.model_selection import StratifiedKFold, GridSearchCV, cross_val_predict
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)
from sklearn.utils.class_weight import compute_class_weight
import joblib

# ========= CONFIG =========
JSON_FILE  = Path(r"/HC_apps_embeddings_GT.json")
OUT_DIR    = Path(r"/model_saved/svm")
MODEL_OUT  = OUT_DIR / "svm_hc_apps_grid.joblib"
CV_CSV_OUT = OUT_DIR / "svm_cv_results.csv"
REPORT_OUT = OUT_DIR / "svm_cv_report.txt"
META_OUT   = OUT_DIR / "svm_training_meta.json"
N_SPLITS   = 5
RANDOM_SEED = 42
# =========================

def load_xy(json_path: Path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    X, y, names = [], [], []
    for obj in data:
        emb = obj.get("embedding")
        lab = obj.get("manual_label")
        if emb is None or lab is None:
            continue
        lab = str(lab).strip().upper()
        if lab not in {"P", "N"}:
            continue
        X.append(emb)
        y.append(1 if lab == "P" else 0)  # P=1, N=0
        names.append(obj.get("pkg_name", ""))

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.int64)
    return X, y, names

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    X, y, names = load_xy(JSON_FILE)
    if len(X) == 0:
        raise RuntimeError("No valid samples with both embedding and manual_label found.")
    print(f"Loaded {len(X)} samples | P={int(y.sum())} N={int((y==0).sum())} | dim={X.shape[1]}")

    # Class weights in case of imbalance
    classes = np.array([0, 1])
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=y)
    class_weight = {int(c): float(w) for c, w in zip(classes, weights)}
    print("Class weights:", class_weight)

    # Pipeline so params use "svc__" prefix (matches your earlier output)
    pipe = Pipeline([
        ("svc", SVC(class_weight=class_weight))
    ])

    # Grid over linear & RBF
    param_grid = [
        {"svc__kernel": ["linear"], "svc__C": [0.1, 0.5, 1, 3, 10]},
        {"svc__kernel": ["rbf"],    "svc__C": [0.5, 1, 3, 10], "svc__gamma": ["scale", 0.01, 0.001]},
    ]


    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)

    grid = GridSearchCV(
        estimator=pipe,
        param_grid=param_grid,
        scoring={"accuracy": "accuracy", "f1_macro": "f1_macro"},
        refit="f1_macro",   # pick model with best F1-macro
        cv=cv,
        n_jobs=-1,
        verbose=1,
        return_train_score=False,
    )

    # === Grid Search ===
    grid.fit(X, y)
    best_params = grid.best_params_
    best_cv_acc = grid.cv_results_["mean_test_accuracy"][grid.best_index_]
    print("\n=== Grid Search Results ===")
    print(f"Best mean CV accuracy: {best_cv_acc:.4f}")
    print("Best params:", best_params)

    # Save full CV results
    pd.DataFrame(grid.cv_results_).to_csv(CV_CSV_OUT, index=False)
    print(f"Saved full CV results to: {CV_CSV_OUT}")

    # === Cross-validated FULL metrics with best params ===
    # Use the best estimator for CV predictions (each sample predicted only in its held-out fold)
    best_estimator = grid.best_estimator_
    y_pred = cross_val_predict(best_estimator, X, y, cv=cv, n_jobs=-1)

    acc = accuracy_score(y, y_pred)
    f1m = f1_score(y, y_pred, average="macro")
    report = classification_report(y, y_pred, target_names=["N", "P"], digits=4)
    cm = confusion_matrix(y, y_pred, labels=[0, 1])

    print("\n=== Cross-validated report (held-out folds) ===")
    print(f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}")
    print(report)
    print("Confusion matrix (rows=true N,P; cols=pred N,P):")
    print(cm)

    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("Cross-validated performance with best params (held-out folds)\n")
        f.write(f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}\n\n")
        f.write(report)
        f.write("\nConfusion matrix (rows=true N,P; cols=pred N,P):\n")
        f.write(np.array2string(cm))
    print(f"Saved CV report to: {REPORT_OUT}")

    # === Fit best model on ALL data and save ===
    best_estimator.fit(X, y)
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_estimator, MODEL_OUT)
    print(f"Saved best model to: {MODEL_OUT}")

    # === Metadata ===
    meta = {
        "model_type": type(best_estimator.named_steps["svc"]).__name__,
        "best_params": best_params,
        "embedding_dim": int(X.shape[1]),
        "label_mapping": {"N": 0, "P": 1},
        "n_samples": int(len(X)),
        "cv_splits": int(N_SPLITS),
        "cv_best_accuracy": float(best_cv_acc),
        "cv_report_accuracy": float(acc),
        "cv_report_f1_macro": float(f1m),
        "class_weight": class_weight,
    }
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("Metadata:", meta)

if __name__ == "__main__":
    main()
