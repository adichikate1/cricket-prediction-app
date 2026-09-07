"""
feature_engineering.py
-----------------------
Builds model-ready features from the cleaned CPL dataframe.

Because the source file only gives us pre-aggregated per-team stats (see
data_preprocessing.py docstring), feature engineering here is limited to:
  1. team1-vs-team2 DIFFERENCE features (these carry most of the signal)
  2. a toss-relative feature (did team1 win the toss?)
  3. two feature MODES:
       MODE_A_BEFORE_TOSS -> no toss information at all
       MODE_B_AFTER_TOSS  -> adds toss_winner / toss_decision info
  4. categorical encoding for team1, team2, venue, pitch_type (+ toss cols in mode B)

No rolling-window recomputation is attempted, because we do not have a raw
per-match log to roll up from -- only the single pre-aggregated form/venue/
win-rate columns already present in the CSV.
"""
import pandas as pd
import numpy as np

DIFF_SPECS = [
    ("team1_win_rate", "team2_win_rate", "diff_win_rate"),
    ("team1_recent_form", "team2_recent_form", "diff_recent_form"),
    ("team1_venue_win_rate", "team2_venue_win_rate", "diff_venue_win_rate"),
    ("team1_avg_runs_last_5", "team2_avg_runs_last_5", "diff_avg_runs_last_5"),
    ("team1_avg_wicket_last_5", "team2_avg_wicket_last_5", "diff_avg_wicket_last_5"),
]

BASE_NUMERIC = [
    "team1_win_rate", "team2_win_rate", "head_to_head_win_rate",
    "team1_recent_form", "team2_recent_form",
    "team1_venue_win_rate", "team2_venue_win_rate",
    "team1_avg_runs_last_5", "team2_avg_runs_last_5",
    "team1_avg_wicket_last_5", "team2_avg_wicket_last_5",
    "avg_first_innings_score", "chasing_success_rate",
    "temperature", "humidity", "rain_probability",
]
DIFF_NUMERIC = [d[2] for d in DIFF_SPECS]
CATEGORICAL_BASE = ["team1", "team2", "venue", "pitch_type"]
CATEGORICAL_TOSS = ["toss_winner", "toss_decision"]


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c1, c2, name in DIFF_SPECS:
        df[name] = df[c1] - df[c2]

    # toss-relative feature: was team1 the toss winner?
    df["toss_winner_is_team1"] = (df["toss_winner"] == df["team1"]).astype(int)
    df["toss_decision_bat"] = (df["toss_decision"] == "Bat").astype(int)

    # simple weather composite (dry/hot vs humid/rainy) - directional guess,
    # left as a raw-ish feature rather than something claiming special meaning
    df["weather_rain_x_humidity"] = df["rain_probability"] * df["humidity"] / 100.0
    return df


def get_feature_columns(mode: str = "after_toss") -> dict:
    """
    mode: 'before_toss' (Mode A) or 'after_toss' (Mode B)
    Returns dict with 'numeric' and 'categorical' column lists.
    """
    numeric = BASE_NUMERIC + DIFF_NUMERIC + ["weather_rain_x_humidity"]
    categorical = list(CATEGORICAL_BASE)

    if mode == "after_toss":
        numeric = numeric + ["toss_winner_is_team1", "toss_decision_bat"]
        categorical = categorical + CATEGORICAL_TOSS
    elif mode == "before_toss":
        pass
    else:
        raise ValueError("mode must be 'before_toss' or 'after_toss'")

    return {"numeric": numeric, "categorical": categorical}


if __name__ == "__main__":
    from data_preprocessing import load_raw, clean

    df = clean(load_raw())
    df = add_engineered_features(df)
    cols_b = get_feature_columns("before_toss")
    cols_a = get_feature_columns("after_toss")
    print("Before-toss feature count:", len(cols_b["numeric"]) + len(cols_b["categorical"]))
    print("After-toss feature count:", len(cols_a["numeric"]) + len(cols_a["categorical"]))
    print(df[DIFF_NUMERIC].describe())
