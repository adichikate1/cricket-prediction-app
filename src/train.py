"""
train.py
--------
Simplified, training-only pipeline: fits the final model on ALL 137 rows,
no train/val/test split, no CV comparison, no hyperparameter tuning, no
accuracy printed.

This means there is NO honest out-of-sample number produced by this script
anymore - you're trading that away on purpose for a model trained on every
available row. If you want to know how good the model actually is before
trusting its predictions, that needs a separate evaluation run (e.g. the
previous version of this script, which did a stratified split + CV + a
held-out test set - ask if you want that restored as a standalone
evaluate-only script instead of being mixed into training).

Model used: ExtraTreesClassifier with the regularized settings found to
generalize best in the earlier CV comparison (max_depth=5,
min_samples_leaf=4) - picked from that comparison, not re-derived here,
since there's no evaluation step in this script to pick a champion with.
Probabilities are calibrated via 5-fold Platt scaling so predict_match()
still returns meaningful probabilities, not just a raw label.
"""
import json
from pathlib import Path

import joblib
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

from data_preprocessing import load_raw, clean
from feature_engineering import add_engineered_features, get_feature_columns

RANDOM_STATE = 42
MODE = "after_toss"


def build_preprocessor(numeric_cols, categorical_cols):
    return ColumnTransformer([
        ("num", StandardScaler(), numeric_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
    ])


def main():
    Path("models").mkdir(exist_ok=True)

    df = clean(load_raw())
    df = add_engineered_features(df)
    cols = get_feature_columns(MODE)
    numeric_cols, categorical_cols = cols["numeric"], cols["categorical"]
    feature_cols = numeric_cols + categorical_cols

    X = df[feature_cols]
    y = df["win"]

    model = ExtraTreesClassifier(
        n_estimators=300, max_depth=5, min_samples_leaf=4, random_state=RANDOM_STATE
    )
    pipe = Pipeline([("pre", build_preprocessor(numeric_cols, categorical_cols)), ("clf", model)])

    # CalibratedClassifierCV internally does 5-fold fitting to calibrate
    # probabilities - this is part of fitting the model, not an evaluation
    # step, and nothing about it is printed or reported.
    calibrated = CalibratedClassifierCV(pipe, method="sigmoid", cv=5)
    calibrated.fit(X, y)

    joblib.dump(calibrated, "models/best_model.pkl")
    joblib.dump({"numeric_cols": numeric_cols, "categorical_cols": categorical_cols}, "models/feature_pipeline.pkl")
    with open("models/feature_columns.json", "w") as f:
        json.dump({"numeric": numeric_cols, "categorical": categorical_cols, "mode": MODE}, f, indent=2)

    print(f"Trained on all {len(df)} rows. Saved models/best_model.pkl, "
          f"feature_pipeline.pkl, feature_columns.json.")


if __name__ == "__main__":
    main()
