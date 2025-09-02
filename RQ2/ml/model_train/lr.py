# pip install scikit-learn pandas joblib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, GridSearchCV, cross_val_predict
from sklearn.metrics import classification_report, accuracy_score, f1_score, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
import joblib

# ========= CONFIG =========
JSON_FILE  = Path("/HC_apps_embeddings_GT.json")  
OUT_DIR    = Path("/model_saved/logreg")
MODEL_OUT  = OUT_DIR / "logreg_hc_apps_grid.joblib"
CV_CSV_OUT = OUT_DIR / "logreg_cv_results.csv"
REPORT_OUT = OUT_DIR / "logreg_cv_report.txt"
PRED_CSV   = OUT_DIR / "logreg_cv_predictions.csv"
CM_CSV     = OUT_DIR / "logreg_cv_confusion_matrix.csv"
META_OUT   = OUT_DIR / "logreg_training_meta.json"
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
    return np.asarray(X, np.float32), np.asarray(y, np.int64), names

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    X, y, names = load_xy(JSON_FILE)
    if len(X) == 0:
        raise RuntimeError("No valid samples with both embedding and manual_label found.")
    print(f"Loaded {len(X)} samples | P={int(y.sum())} N={int((y==0).sum())} | dim={X.shape[1]}")

    # Class weights (helps if P/N slightly imbalanced)
    classes = np.array([0, 1])
    weights = compute_class_weight("balanced", classes=classes, y=y)
    class_weight_map = {int(c): float(w) for c, w in zip(classes, weights)}
    print("Class weights:", class_weight_map)

    base = LogisticRegression(
        class_weight="balanced",   # try balanced by default; grid will override if needed
        max_iter=5000,
        random_state=RANDOM_SEED,
        n_jobs=None,               # liblinear/saga ignore n_jobs for binary
        solver="liblinear"         # default; grid will also try saga
    )

    # ~17 total candidates to match SVM compute
    param_grid = [
        # liblinear supports L1 and L2
        {"solver": ["liblinear"], "penalty": ["l2"], "C": [0.1, 0.5, 1, 3, 10]},
        {"solver": ["liblinear"], "penalty": ["l1"], "C": [0.1, 0.5, 1, 3, 10]},
        # saga supports l1, l2, and elasticnet; test a smaller set
        {"solver": ["saga"], "penalty": ["l2"], "C": [0.5, 1, 3]},
        {"solver": ["saga"], "penalty": ["l1"], "C": [0.5, 1, 3]},
        {"solver": ["saga"], "penalty": ["elasticnet"], "C": [1], "l1_ratio": [0.5]},
    ]
    # count: 5 + 5 + 3 + 3 + 1 = **17** candidates

    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)
    grid = GridSearchCV(
        estimator=base,
        param_grid=param_grid,
        scoring={
            "accuracy": "accuracy",
            "f1_macro": "f1_macro",
            "precision_macro": "precision_macro",
            "recall_macro": "recall_macro",
        },
        refit="f1_macro",     # choose best by F1-macro
        cv=cv,
        n_jobs=-1,
        verbose=1,
        return_train_score=False,
    )

    grid.fit(X, y)

    # Summarize & persist grid results
    results_df = pd.DataFrame(grid.cv_results_)
    results_df.to_csv(CV_CSV_OUT, index=False)
    best_idx = grid.best_index_
    best_mean_cv_acc = results_df.loc[best_idx, "mean_test_accuracy"]

    print("\n=== Grid Search Results (Logistic Regression) ===")
    print(f"Best mean CV accuracy: {best_mean_cv_acc:.4f}")
    print("Best params:", grid.best_params_)
    print(f"Saved full CV results to: {CV_CSV_OUT}")

    # Cross-validated predictions with best params (unbiased metrics)
    best_est = grid.best_estimator_
    y_pred = cross_val_predict(best_est, X, y, cv=cv, n_jobs=-1)

    acc = accuracy_score(y, y_pred)
    f1m = f1_score(y, y_pred, average="macro")
    report = classification_report(y, y_pred, target_names=["N", "P"], digits=4)
    cm = confusion_matrix(y, y_pred, labels=[0, 1])

    print("\n=== Cross-validated report (held-out folds) ===")
    print(f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}")
    print(report)
    print(cm)

    # Save artifacts
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("Cross-validated performance (best LogReg via GridSearchCV)\n")
        f.write(f"Accuracy: {acc:.4f} | F1-macro: {f1m:.4f}\n\n")
        f.write(report)
    pd.DataFrame(cm, index=["N_true","P_true"], columns=["N_pred","P_pred"]).to_csv(CM_CSV, index=True)

    pd.DataFrame({
        "pkg_name": names,
        "true_label": np.where(y == 1, "P", "N"),
        "pred_label": np.where(y_pred == 1, "P", "N"),
    }).to_csv(PRED_CSV, index=False)

    # Save best model (already refit on all data due to refit="f1_macro")
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_est, MODEL_OUT)
    print(f"\nSaved best LogReg model to: {MODEL_OUT}")

    # Metadata
    meta = {
        "model_type": "LogisticRegression",
        "best_params": grid.best_params_,
        "embedding_dim": int(X.shape[1]),
        "label_mapping": {"N": 0, "P": 1},
        "n_samples": int(len(X)),
        "cv_splits": int(N_SPLITS),
        "cv_best_accuracy": float(best_mean_cv_acc),
        "cv_report": {"accuracy": float(acc), "f1_macro": float(f1m)},
        "artifacts": {
            "cv_results_csv": str(CV_CSV_OUT),
            "cv_report_txt": str(REPORT_OUT),
            "cv_confusion_matrix_csv": str(CM_CSV),
            "cv_predictions_csv": str(PRED_CSV),
            "model_path": str(MODEL_OUT),
        },
    }
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("Metadata:", meta)

if __name__ == "__main__":
    main()

