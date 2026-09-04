"""
predict.py
----------
Loads the saved model artifacts and exposes predict_match(), which the
Streamlit app (app.py) and any other caller can use without retraining.
"""
import json
import joblib
import numpy as np
import pandas as pd

from data_preprocessing import load_raw, clean
from feature_engineering import add_engineered_features, DIFF_SPECS

MODEL_PATH = "models/best_model.pkl"
FEATURE_COLUMNS_PATH = "models/feature_columns.json"

_model = None
_feature_cols = None
_league_df = None  # cleaned+engineered historical data, used for fallback stats


def _load():
    global _model, _feature_cols, _league_df
    if _model is None:
        _model = joblib.load(MODEL_PATH)
        with open(FEATURE_COLUMNS_PATH) as f:
            _feature_cols = json.load(f)
        _league_df = add_engineered_features(clean(load_raw()))
    return _model, _feature_cols, _league_df


def confidence_label(probability: float) -> str:
    """probability = probability of the PREDICTED side (i.e. max(p, 1-p))."""
    margin = max(probability, 1 - probability)
    if margin < 0.55:
        return "VERY LOW"
    if margin < 0.60:
        return "LOW"
    if margin < 0.70:
        return "MEDIUM"
    if margin < 0.80:
        return "HIGH"
    return "VERY HIGH"


def _team_fallback_stats(league_df: pd.DataFrame, team: str) -> dict:
    """
    League-average-with-shrinkage fallback for a team with little/no history.
    Uses a simple Bayesian-style shrinkage toward the league mean so a team
    with only 1-2 matches doesn't produce an unrealistic 0%/100% win rate.
    """
    league_mean_wr = pd.concat([
        league_df["team1_win_rate"], league_df["team2_win_rate"]
    ]).mean()

    as_team1 = league_df[league_df["team1"] == team]
    as_team2 = league_df[league_df["team2"] == team]
    n_obs = len(as_team1) + len(as_team2)

    if n_obs == 0:
        # completely unknown team -> pure league average, flagged
        return {
            "win_rate": league_mean_wr,
            "recent_form": pd.concat([league_df["team1_recent_form"], league_df["team2_recent_form"]]).mean(),
            "venue_win_rate": league_mean_wr,
            "avg_runs_last_5": pd.concat([league_df["team1_avg_runs_last_5"], league_df["team2_avg_runs_last_5"]]).mean(),
            "avg_wicket_last_5": pd.concat([league_df["team1_avg_wicket_last_5"], league_df["team2_avg_wicket_last_5"]]).mean(),
            "known": False,
        }

    # shrinkage: weight observed rate by n_obs against a prior of 10 "phantom" league-average matches
    K = 10
    raw_wr = pd.concat([as_team1["team1_win_rate"], as_team2["team2_win_rate"]]).mean()
    shrunk_wr = (raw_wr * n_obs + league_mean_wr * K) / (n_obs + K)

    return {
        "win_rate": shrunk_wr,
        "recent_form": pd.concat([as_team1["team1_recent_form"], as_team2["team2_recent_form"]]).mean(),
        "venue_win_rate": pd.concat([as_team1["team1_venue_win_rate"], as_team2["team2_venue_win_rate"]]).mean(),
        "avg_runs_last_5": pd.concat([as_team1["team1_avg_runs_last_5"], as_team2["team2_avg_runs_last_5"]]).mean(),
        "avg_wicket_last_5": pd.concat([as_team1["team1_avg_wicket_last_5"], as_team2["team2_avg_wicket_last_5"]]).mean(),
        "known": True,
    }


def _build_feature_row(team1, team2, venue, toss_winner, toss_decision,
                        temperature, humidity, rain_probability, league_df,
                        overrides=None):
    """Builds a single-row feature dataframe, falling back to league/shrunk
    averages for anything not directly observed (unseen team/venue/matchup).

    overrides: optional dict that can manually set any of the auto-computed
    stat columns (team1_win_rate, team2_win_rate, head_to_head_win_rate,
    team1_recent_form, team2_recent_form, team1_venue_win_rate,
    team2_venue_win_rate, team1_avg_runs_last_5, team2_avg_runs_last_5,
    team1_avg_wicket_last_5, team2_avg_wicket_last_5, avg_first_innings_score,
    chasing_success_rate). Any key not present/None is auto-computed as before.
    """
    overrides = overrides or {}

    exact = league_df[(league_df["team1"] == team1) & (league_df["team2"] == team2)]

    t1_stats = _team_fallback_stats(league_df, team1)
    t2_stats = _team_fallback_stats(league_df, team2)

    # head-to-head
    h2h_rows = league_df[
        ((league_df["team1"] == team1) & (league_df["team2"] == team2)) |
        ((league_df["team1"] == team2) & (league_df["team2"] == team1))
    ]
    if len(h2h_rows) > 0:
        # win column: 1 = team2(of that row) wins. Normalize to "team1(requested) win rate"
        wins_for_team1 = 0
        for _, r in h2h_rows.iterrows():
            if r["team1"] == team1:
                wins_for_team1 += (1 - r["win"])
            else:
                wins_for_team1 += r["win"]
        h2h_win_rate = 100.0 * wins_for_team1 / len(h2h_rows)
    else:
        h2h_win_rate = 50.0  # no history -> neutral prior

    # venue stats
    venue_rows_t1 = league_df[(league_df["venue"] == venue) &
                               ((league_df["team1"] == team1) | (league_df["team2"] == team1))]
    venue_rows_t2 = league_df[(league_df["venue"] == venue) &
                               ((league_df["team1"] == team2) | (league_df["team2"] == team2))]
    league_venue_wr = pd.concat([league_df["team1_venue_win_rate"], league_df["team2_venue_win_rate"]]).mean()
    t1_venue_wr = t1_stats["venue_win_rate"] if len(venue_rows_t1) == 0 else t1_stats["venue_win_rate"]
    t2_venue_wr = t2_stats["venue_win_rate"] if len(venue_rows_t2) == 0 else t2_stats["venue_win_rate"]

    venue_rows_all = league_df[league_df["venue"] == venue]
    pitch_type = venue_rows_all["pitch_type"].mode().iloc[0] if len(venue_rows_all) else league_df["pitch_type"].mode().iloc[0]
    avg_first_innings = venue_rows_all["avg_first_innings_score"].mean() if len(venue_rows_all) else league_df["avg_first_innings_score"].mean()
    chasing_success = venue_rows_all["chasing_success_rate"].mean() if len(venue_rows_all) else league_df["chasing_success_rate"].mean()

    row = {
        "team1": team1, "team2": team2, "venue": venue, "pitch_type": pitch_type,
        "team1_win_rate": t1_stats["win_rate"], "team2_win_rate": t2_stats["win_rate"],
        "head_to_head_win_rate": h2h_win_rate,
        "team1_recent_form": t1_stats["recent_form"], "team2_recent_form": t2_stats["recent_form"],
        "team1_venue_win_rate": t1_venue_wr, "team2_venue_win_rate": t2_venue_wr,
        "team1_avg_runs_last_5": t1_stats["avg_runs_last_5"], "team2_avg_runs_last_5": t2_stats["avg_runs_last_5"],
        "team1_avg_wicket_last_5": t1_stats["avg_wicket_last_5"], "team2_avg_wicket_last_5": t2_stats["avg_wicket_last_5"],
        "avg_first_innings_score": avg_first_innings,
        "chasing_success_rate": chasing_success,
        "temperature": temperature, "humidity": humidity, "rain_probability": rain_probability,
        "toss_winner": toss_winner if toss_winner else team1,  # placeholder for before-toss mode
        "toss_decision": toss_decision if toss_decision else "Unknown",
    }

    # apply manual overrides (only for keys the caller actually set)
    overridden_keys = []
    for key, val in overrides.items():
        if val is not None and key in row:
            row[key] = val
            overridden_keys.append(key)

    row_df = pd.DataFrame([row])
    row_df = add_engineered_features(row_df)
    if not toss_winner:
        # before-toss mode: neutral (no info) rather than defaulting to team1
        row_df["toss_winner_is_team1"] = 0
        row_df["toss_decision_bat"] = 0

    warnings = []
    if not t1_stats["known"]:
        warnings.append(f"'{team1}' has no history in the dataset - using league-average fallback.")
    if not t2_stats["known"]:
        warnings.append(f"'{team2}' has no history in the dataset - using league-average fallback.")
    if len(venue_rows_all) == 0:
        warnings.append(f"Venue '{venue}' has no history in the dataset - using league-average venue stats.")
    if len(h2h_rows) == 0:
        warnings.append(f"No head-to-head history between {team1} and {team2} - using a neutral 50% prior.")
    if overridden_keys:
        warnings.append("Manually overridden stats: " + ", ".join(overridden_keys))

    return row_df, warnings


def predict_match(team1, team2, venue, toss_winner=None, toss_decision=None,
                   temperature=None, humidity=None, rain_probability=None,
                   team1_win_rate=None, team2_win_rate=None, head_to_head_win_rate=None,
                   team1_recent_form=None, team2_recent_form=None,
                   team1_venue_win_rate=None, team2_venue_win_rate=None,
                   team1_avg_runs_last_5=None, team2_avg_runs_last_5=None,
                   team1_avg_wicket_last_5=None, team2_avg_wicket_last_5=None,
                   avg_first_innings_score=None, chasing_success_rate=None):
    """
    Mode A (before toss): leave toss_winner / toss_decision as None.
    Mode B (after toss): pass toss_winner and toss_decision.

    All the team1_win_rate / team1_recent_form / ... / chasing_success_rate
    arguments are OPTIONAL manual overrides. If left as None (the default),
    each one is auto-computed from historical data (with league-average /
    shrinkage fallback for unseen teams or venues), same as before. Pass a
    number to force that stat instead - useful for what-if scenarios or when
    you have more current stats than what's in the training CSV.

    Returns a dict:
        {
            "team1": ..., "team2": ...,
            "team1_probability": float, "team2_probability": float,
            "predicted_winner": str, "confidence": str,
            "mode": "before_toss" | "after_toss",
            "warnings": [str, ...]
        }
    """
    model, feature_cols, league_df = _load()

    # sensible league-average defaults for missing weather inputs
    if temperature is None:
        temperature = league_df["temperature"].mean()
    if humidity is None:
        humidity = league_df["humidity"].mean()
    if rain_probability is None:
        rain_probability = league_df["rain_probability"].mean()

    mode = "after_toss" if (toss_winner and toss_decision) else "before_toss"

    overrides = {
        "team1_win_rate": team1_win_rate, "team2_win_rate": team2_win_rate,
        "head_to_head_win_rate": head_to_head_win_rate,
        "team1_recent_form": team1_recent_form, "team2_recent_form": team2_recent_form,
        "team1_venue_win_rate": team1_venue_win_rate, "team2_venue_win_rate": team2_venue_win_rate,
        "team1_avg_runs_last_5": team1_avg_runs_last_5, "team2_avg_runs_last_5": team2_avg_runs_last_5,
        "team1_avg_wicket_last_5": team1_avg_wicket_last_5, "team2_avg_wicket_last_5": team2_avg_wicket_last_5,
        "avg_first_innings_score": avg_first_innings_score, "chasing_success_rate": chasing_success_rate,
    }

    row_df, warnings = _build_feature_row(
        team1, team2, venue, toss_winner, toss_decision,
        temperature, humidity, rain_probability, league_df, overrides=overrides
    )

    all_cols = feature_cols["numeric"] + feature_cols["categorical"]
    X = row_df[all_cols]

    proba_team2 = model.predict_proba(X)[0, 1]  # win=1 means team2 wins
    proba_team1 = 1 - proba_team2

    predicted_winner = team1 if proba_team1 >= proba_team2 else team2
    conf = confidence_label(max(proba_team1, proba_team2))

    return {
        "team1": team1,
        "team2": team2,
        "team1_probability": round(float(proba_team1), 4),
        "team2_probability": round(float(proba_team2), 4),
        "predicted_winner": predicted_winner,
        "confidence": conf,
        "mode": mode,
        "warnings": warnings,
    }


def compute_defaults(team1, team2, venue):
    """Returns the auto-computed stat values for team1/team2/venue, so a UI
    can pre-fill editable fields with them (instead of showing blank boxes)."""
    _, _, league_df = _load()
    row_df, _ = _build_feature_row(
        team1, team2, venue, None, None,
        league_df["temperature"].mean(), league_df["humidity"].mean(),
        league_df["rain_probability"].mean(), league_df
    )
    keys = ["team1_win_rate", "team2_win_rate", "head_to_head_win_rate",
            "team1_recent_form", "team2_recent_form",
            "team1_venue_win_rate", "team2_venue_win_rate",
            "team1_avg_runs_last_5", "team2_avg_runs_last_5",
            "team1_avg_wicket_last_5", "team2_avg_wicket_last_5",
            "avg_first_innings_score", "chasing_success_rate"]
    return {k: round(float(row_df.iloc[0][k]), 2) for k in keys}


if __name__ == "__main__":
    r1 = predict_match("Trinbago Knight Riders", "Guyana Amazon Warriors", "Queens Park Oval")
    print("Before toss:", r1)
    r2 = predict_match("Trinbago Knight Riders", "Guyana Amazon Warriors", "Queens Park Oval",
                        toss_winner="Trinbago Knight Riders", toss_decision="Bat")
    print("After toss: ", r2)
    r3 = predict_match("Brand New XI", "Guyana Amazon Warriors", "A New Ground")
    print("Unknown team/venue:", r3)
