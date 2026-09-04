"""
evaluate.py
-----------
Loads the saved champion model + metrics and produces:
  - a printed model-comparison table
  - a feature-importance chart (permutation importance, model-agnostic since
    the champion may be an ensemble/calibrated wrapper)
  - a SHAP summary for the underlying tree model where available
"""
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.inspection import permutation_importance

from data_preprocessing import load_raw, clean
from feature_engineering import add_engineered_features, get_feature_columns

MODE = "after_toss"


def print_comparison_table(metrics_path="models/model_metrics.json"):
    try:
        with open(metrics_path) as f:
            m = json.load(f)
    except FileNotFoundError:
        print(f"\nNo {metrics_path} found - the current train.py trains on all "
              f"data with no evaluation step, so there's no comparison table "
              f"or accuracy to show. This is expected if you've run the "
              f"training-only version of train.py.")
        return None
    print("\n=== Model comparison (cross-validated) ===")
    print(f"{'Model':22s} {'CV Acc':>10s} {'CV AUC':>10s} {'GroupKFold Acc':>16s}")
    for name, r in m["cv_comparison"].items():
        print(f"{name:22s} {r['cv_accuracy_mean']:.3f}+/-{r['cv_accuracy_std']:.2f} "
              f"{r['cv_auc_mean']:>9.3f} {r['groupkfold_accuracy_mean']:>10.3f}+/-{r['groupkfold_accuracy_std']:.2f}")
    print(f"\nChampion: {m['champion']}")
    print(f"Train accuracy: {m['train_metrics']['accuracy']:.3f}")
    print(f"TEST accuracy (unseen, touched once): {m['test_metrics']['accuracy']:.3f}")
    print(f"TEST ROC-AUC: {m['test_metrics']['roc_auc']:.3f}")
    print(f"Overfit gap (train-test): {m['overfit_gap_train_minus_test']:.3f}")
    print(f"\nValidation note: {m['note']}")
    return m


def feature_importance_chart(top_n=20, out_path="models/feature_importance.png"):
    model = joblib.load("models/best_model.pkl")
    df = clean(load_raw())
    df = add_engineered_features(df)
    cols = get_feature_columns(MODE)
    feature_cols = cols["numeric"] + cols["categorical"]
    X = df[feature_cols]
    y = df["win"]

    print("\nComputing permutation importance on full dataset (n=137, so treat as directional, not precise)...")
    result = permutation_importance(model, X, y, n_repeats=20, random_state=42, scoring="roc_auc")
    importances = pd.Series(result.importances_mean, index=feature_cols).sort_values(ascending=False)
    top = importances.head(top_n)

    plt.figure(figsize=(8, 6))
    top.iloc[::-1].plot(kind="barh")
    plt.title(f"Top {min(top_n, len(top))} Feature Importances (permutation, ROC-AUC drop)")
    plt.xlabel("Mean AUC decrease when shuffled")
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    print(f"Saved chart to {out_path}")
    print("\nTop features:\n", top.to_string())
    return top


if __name__ == "__main__":
    print_comparison_table()
    feature_importance_chart()
