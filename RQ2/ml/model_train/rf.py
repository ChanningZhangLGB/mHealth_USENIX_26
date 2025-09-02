# pip install scikit-learn pandas joblib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, GridSearchCV, cross_val_predict
from sklearn.metrics import classification_report, accuracy_score, f1_score, confusion_matrix
import joblib

# ========= CONFIG =========
JSON_FILE  = Path(r"/HC_apps_embeddings_GT.json")
OUT_DIR    = Path(r"/model_saved/rf")
MODEL_OUT  = OUT_DIR / "rf_hc_apps_grid.joblib"
CV_CSV_OUT = OUT_DIR / "rf_cv_results.csv"
REPORT_OUT = OUT_DIR / "rf_cv_report.txt"
PRED_CSV   = OUT_DIR / "rf_cv_predictions.csv"
CM_CSV     = OUT_DIR / "rf_cv_confusion_matrix.csv"
META_OUT   = OUT_DIR / "rf_training_meta.json"
N_SPLITS   = 5
RSEED      = 42
# =========================

def load_xy(p: Path):
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    X, y, names = [], [], []
    for o in data:
        if o.get("embedding") is None or o.get("manual_label") is None:
            continue
        lab = str(o["manual_label"]).strip().upper()
        if lab not in {"P","N"}: 
            continue
        X.append(o["embedding"])
        y.append(1 if lab=="P" else 0)
        names.append(o.get("pkg_name",""))
    return np.asarray(X, np.float32), np.asarray(y, np.int64), names

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    X, y, names = load_xy(JSON_FILE)
    print(f"Loaded {len(X)} samples | P={int(y.sum())} N={int((y==0).sum())} | dim={X.shape[1]}")

    base = RandomForestClassifier(
        n_estimators=400,                 # fixed for fairness / speed
        class_weight="balanced_subsample",# fixed to handle imbalance
        random_state=RSEED,
        n_jobs=-1
    )

    # 16 candidates → ~80 fits with 5-fold CV (similar to SVM's 85 fits)
    param_grid = {
        "max_depth": [None, 20],           # 2
        "min_samples_split": [2, 4],       # 2
        "min_samples_leaf": [1, 2],        # 2
        "max_features": ["sqrt", 0.5],     # 2  (0.5 = 50% of features)
    }

    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RSEED)
    grid = GridSearchCV(
        estimator=base,
        param_grid=param_grid,
        scoring={
            "accuracy": "accuracy",
            "f1_macro": "f1_macro",
            "precision_macro": "precision_macro",
            "recall_macro": "recall_macro",
        },
        refit="f1_macro",
        cv=cv,
        n_jobs=-1,
        verbose=1,
        return_train_score=False,
    )

    grid.fit(X, y)
    best_idx = grid.best_index_
    best_cv_acc = grid.cv_results_["mean_test_accuracy"][best_idx]
    print("\n=== Grid Search Results (RF, compact) ===")
    print(f"Best mean CV accuracy: {best_cv_acc:.4f}")
    print("Best params:", grid.best_params_)
    pd.DataFrame(grid.cv_results_).to_csv(CV_CSV_OUT, index=False)

    # Cross‑validated metrics using best params
    y_pred = cross_val_predict(grid.best_estimator_, X, y, cv=cv, n_jobs=-1)
    acc = accuracy_score(y, y_pred)
    f1m = f1_score(y, y_pred, average="macro")
    report = classification_report(y, y_pred, target_names=["N","P"], digits=4)
    cm = confusion_matrix(y, y_pred, labels=[0,1])

    print("\n=== Cross-validated report ===")
    print(f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}\n{report}\n{cm}")

    # Save artifacts
    Path(REPORT_OUT).write_text(
        f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}\n\n{report}", encoding="utf-8"
    )
    pd.DataFrame(cm, index=["N_true","P_true"], columns=["N_pred","P_pred"]).to_csv(CM_CSV, index=True)
    pd.DataFrame({"pkg_name": names,
                  "true_label": np.where(y==1,"P","N"),
                  "pred_label": np.where(y_pred==1,"P","N")}).to_csv(PRED_CSV, index=False)

    joblib.dump(grid.best_estimator_, MODEL_OUT)
    print(f"\nSaved best RF model to: {MODEL_OUT}")

    meta = {
        "model_type": "RandomForestClassifier",
        "embedding_dim": int(X.shape[1]),
        "label_mapping": {"N":0,"P":1},
        "n_samples": int(len(X)),
        "cv_splits": int(N_SPLITS),
        "grid_candidates": 16,
        "cv_best_accuracy": float(best_cv_acc),
        "best_params": grid.best_params_,
    }
    Path(META_OUT).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("Metadata:", meta)

if __name__ == "__main__":
    main()
