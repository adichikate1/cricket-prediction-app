"""
data_preprocessing.py
----------------------
Loads the raw Caribbean Premier League CSV and performs basic cleaning.

IMPORTANT DATA-QUALITY NOTE (read this before trusting any downstream number):
The source CSV has NO date/timestamp/match-id column. Every numeric feature
(team1_win_rate, team1_recent_form, team1_venue_win_rate, avg_runs_last_5,
etc.) already arrives as a PRE-COMPUTED AGGREGATE - there is no raw,
row-per-ball or row-per-innings log to rebuild rolling windows from, and no
way to sort rows chronologically. That means genuine time-based validation
(oldest -> train, newest -> test) is NOT POSSIBLE on this file. This module
does NOT attempt to fake one. See README.md for how validation is instead
done (stratified K-fold + grouped-by-matchup K-fold) and why.
"""
import pandas as pd
import numpy as np
import json

RAW_PATH = "data/Caribbean Premier League.csv"

NUMERIC_COLS = [
    "team1_win_rate", "team2_win_rate", "head_to_head_win_rate",
    "team1_recent_form", "team2_recent_form",
    "team1_venue_win_rate", "team2_venue_win_rate",
    "team1_avg_runs_last_5", "team2_avg_runs_last_5",
    "team1_avg_wicket_last_5", "team2_avg_wicket_last_5",
    "avg_first_innings_score", "chasing_success_rate",
    "temperature", "humidity", "rain_probability",
]
CATEGORICAL_COLS = ["team1", "team2", "toss_winner", "toss_decision", "venue", "pitch_type"]
TARGET_COL = "win"  # 1 = team2 wins, 0 = team1 wins (verified against team win-rate means)


def load_raw(path: str = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    # normalize whitespace in team / venue names (source has some double-spaces,
    # e.g. "St Kitts  Nevis Patriots")
    for col in ["team1", "team2", "toss_winner", "venue", "pitch_type"]:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df


def inspect(df: pd.DataFrame) -> dict:
    """Returns a small report used by train.py / README generation."""
    report = {
        "n_rows": len(df),
        "n_cols": df.shape[1],
        "missing": df.isnull().sum().to_dict(),
        "duplicates": int(df.duplicated().sum()),
        "target_balance": df[TARGET_COL].value_counts().to_dict(),
        "n_unique_team1": df["team1"].nunique(),
        "n_unique_team2": df["team2"].nunique(),
        "n_unique_venues": df["venue"].nunique(),
        "n_unique_matchups": df[["team1", "team2"]].drop_duplicates().shape[0],
        "has_date_column": False,
    }
    return report


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # toss_decision has a few missing values -> mark explicitly rather than
    # silently imputing a bat/bowl guess (that would inject information we
    # don't have)
    df["toss_decision"] = df["toss_decision"].fillna("Unknown")

    # drop exact duplicate rows if any (there are none currently, but keep
    # this defensive in case new data is appended later)
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"[data_preprocessing] dropped {dropped} duplicate rows")

    return df


LEAKAGE_COLUMNS_REMOVED = []  # nothing in this file is post-match (see README "Leakage audit")


CSV_COLUMNS = [
    "team1", "team2", "venue", "pitch_type",
    "team1_win_rate", "team2_win_rate", "head_to_head_win_rate",
    "team1_recent_form", "team2_recent_form",
    "team1_venue_win_rate", "team2_venue_win_rate",
    "team1_avg_runs_last_5", "team2_avg_runs_last_5",
    "team1_avg_wicket_last_5", "team2_avg_wicket_last_5",
    "avg_first_innings_score", "chasing_success_rate",
    "toss_winner", "toss_decision",
    "temperature", "humidity", "rain_probability", "win",
]


def append_row(row: dict, path: str = RAW_PATH) -> pd.DataFrame:
    """Appends one completed-match row to the CSV and returns the updated
    dataframe. `row` must include a non-null 'win' (0 or 1) - this is meant
    for finished matches being added to the training set, not pre-match
    predictions. Missing CSV_COLUMNS keys in `row` are left blank."""
    if row.get("win") is None:
        raise ValueError("append_row requires a known match result ('win' = 0 or 1) - "
                          "use predict_match() for pre-match predictions instead.")

    existing = pd.read_csv(path)
    new_row = {col: row.get(col) for col in CSV_COLUMNS}
    updated = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
    updated.to_csv(path, index=False)
    return updated


ADDED_URLS_PATH = "data/added_match_urls.json"


def load_added_urls(path: str = ADDED_URLS_PATH) -> set:
    """Set of CREX match URLs already appended to the training CSV, so the
    same match can't be added twice (e.g. clicking the button twice, or
    pasting the same URL again by mistake)."""
    try:
        with open(path) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def mark_url_added(url: str, path: str = ADDED_URLS_PATH) -> None:
    urls = load_added_urls(path)
    urls.add(url)
    with open(path, "w") as f:
        json.dump(sorted(urls), f, indent=2)


if __name__ == "__main__":
    df = load_raw()
    rep = inspect(df)
    for k, v in rep.items():
        print(f"{k}: {v}")
    df = clean(df)
    print("\nCleaned shape:", df.shape)
