# CPL Match Predictor

A pre-match win-probability model for Caribbean Premier League matchups, built
on `data/Caribbean Premier League.csv`.

**Read this whole README before trusting the numbers below.** The dataset has
real structural limits that change what "leakage-free" and "unseen future
match" can honestly mean here — they're explained below rather than papered
over.

---

## 0. Deploying with live data collection (CREX scrape + retrain)

The app has a "🔴 Fetch live stats from CREX" panel that can (a) pre-fill a
prediction with live pre-match stats, and (b) for a *finished* match, scrape
the result and append it to the training CSV, then retrain on the updated
data. That second part **will not survive a reboot on Streamlit Community
Cloud (or most hosts) unless you set up GitHub auto-sync** - the container's
local disk is wiped on every restart/redeploy, but your GitHub repo isn't.

One-time setup:
1. Create a GitHub Personal Access Token (fine-grained), scoped to only this
   repo, with **Contents: Read and write** permission:
   https://github.com/settings/personal-access-tokens/new
2. In your Streamlit Community Cloud app → **Settings → Secrets**, add:
   ```
   GITHUB_TOKEN = "ghp_..."
   GITHUB_REPO = "your-username/your-repo-name"
   GITHUB_BRANCH = "main"
   ```
   Add `GITHUB_PATH_PREFIX = "cricket_prediction/"` too if your repo nests
   this project inside a subfolder rather than at the repo root.
3. That's it — after that, "Add this match to training data & retrain"
   commits the updated CSV + model files straight back to your repo, so the
   growth persists across reboots. Without these secrets set, the button
   still works for the current session, but a clear warning tells you the
   change will be lost on the next restart.

See `src/github_sync.py` for exactly what gets committed and how.

## 1. Dataset audit (what's actually in the file)

- **137 rows, 23 columns.** No `date`, no match ID, no ball-by-ball or
  innings-level log.
- Every feature arrives as a **pre-computed aggregate**: `team1_win_rate`,
  `team1_recent_form`, `team1_venue_win_rate`, `team1_avg_runs_last_5`,
  `team1_avg_wicket_last_5`, `avg_first_innings_score`, `chasing_success_rate`,
  plus `toss_winner`, `toss_decision`, `temperature`, `humidity`,
  `rain_probability`, `venue`, `pitch_type`, and the target `win`.
- **0 duplicate rows.** Only `toss_decision` has missing values (3 rows) —
  filled with an explicit `"Unknown"` category rather than guessed.
- **Target balance:** 69 rows `win=1`, 68 rows `win=0` — well balanced.
- **8 unique teams, 8 venues, only 39 unique team1/team2 pairings** across 137
  rows — a small, repeated-matchup dataset.
- **Target semantics verified, not assumed:** rows with `win=0` have a higher
  mean `team1_win_rate`/`team1_venue_win_rate`; rows with `win=1` have a higher
  mean for team2's equivalents. So `win=1` = Team 2 wins, `win=0` = Team 1
  wins, exactly matching the requested target convention.

## 2. Leakage audit

Checked every column against "would this be known before the match starts?":

| Column | Verdict |
|---|---|
| `team1_win_rate`, `team2_win_rate`, `head_to_head_win_rate`, `*_recent_form`, `*_venue_win_rate`, `*_avg_runs_last_5`, `*_avg_wicket_last_5`, `avg_first_innings_score`, `chasing_success_rate` | Pre-match historical aggregates — kept |
| `toss_winner`, `toss_decision` | Known only once the toss happens — kept, but gated behind **Mode B (after toss)**; excluded entirely from **Mode A (before toss)** |
| `temperature`, `humidity`, `rain_probability`, `venue`, `pitch_type` | Known pre-match (forecast/venue) — kept |
| `win` | Target — excluded from features |

**No columns were removed for leakage** — none of the given columns describe
the outcome of *this* match (no final score, no post-match stats for the row
itself). The one caveat: because these aggregates arrive pre-computed, we
cannot independently verify whether each team's `win_rate`/`recent_form` for a
given row was computed strictly from matches *before* that row — there's no
row order to check it against. This is disclosed, not hidden.

## 3. Why there's no chronological (time-series) validation

The brief asked for oldest→train, newest→test, plus `TimeSeriesSplit`. **This
is not possible on this file** — there is no date column, so rows cannot be
sorted chronologically, and doing so with an invented order would produce a
validation number that *looks* leakage-free but is actually meaningless
(possibly worse than useless, since it would hide the real evaluation problem
behind a fake methodology).

Instead, `train.py` uses:

1. **A single stratified 60/20/20 train/val/test split** — the test set is
   touched exactly once, at the end.
2. **RepeatedStratifiedKFold (5 folds × 5 repeats)** on train+val for model
   comparison, reporting mean ± std so the small-sample variance is visible.
3. **GroupKFold grouped by (team1, team2) matchup** as a secondary,
   generalization-to-unseen-matchup check — the closest honest proxy to
   "future/unseen" available without dates.

## 4. Feature engineering

- Difference features: `diff_win_rate`, `diff_recent_form`,
  `diff_venue_win_rate`, `diff_avg_runs_last_5`, `diff_avg_wicket_last_5`
  (team1 − team2), which carry most of the model's signal.
- `toss_winner_is_team1`, `toss_decision_bat` (Mode B only).
- `weather_rain_x_humidity` composite.
- Categorical encoding via one-hot (`team1`, `team2`, `venue`, `pitch_type`,
  + toss columns in Mode B).
- **What wasn't attempted:** rebuilding 3/5/10-match rolling windows from
  scratch. The source data doesn't include a raw per-match log to roll up —
  only the single pre-aggregated form/venue/win-rate columns already in the
  CSV, which are used as given.

## 5. Models compared (RepeatedStratifiedKFold, train+val only)

| Model | CV Accuracy | CV AUC | GroupKFold Accuracy (by matchup) |
|---|---|---|---|
| Logistic Regression | 0.593 ± 0.113 | 0.653 | 0.532 ± 0.049 |
| Random Forest | 0.602 ± 0.068 | 0.675 | 0.560 ± 0.041 |
| **Extra Trees** | **0.653 ± 0.061** | **0.716** | 0.577 ± 0.107 |
| Gradient Boosting | 0.569 ± 0.093 | 0.635 | 0.551 ± 0.065 |
| HistGradientBoosting | 0.543 ± 0.089 | 0.581 | 0.523 ± 0.073 |
| XGBoost | 0.604 ± 0.088 | 0.649 | 0.541 ± 0.084 |
| LightGBM | 0.552 ± 0.087 | 0.588 | 0.532 ± 0.064 |
| CatBoost | 0.583 ± 0.083 | 0.654 | 0.578 ± 0.018 |

Top 3 by CV accuracy (Extra Trees, XGBoost, Random Forest) were tuned with
**Optuna** (25 trials each, small search spaces — the dataset is too small
for aggressive tuning) and re-compared on the untouched validation split. A
soft-voting ensemble of the tuned top 3 was also tried but **did not beat the
single best model on validation AUC** (ensemble val AUC 0.577 vs. Extra
Trees' 0.597), so it was not selected.

**Why Extra Trees won:** highest CV accuracy and AUC among all 8 candidates,
held up on the secondary matchup-generalization check, and — after applying
depth/leaf regularization (`max_depth≤6`, `min_samples_leaf≥3`) — showed only
an 11.6-point train/test accuracy gap, i.e. it wasn't just memorizing the 81
training rows. (Note: before regularizing the tree-based candidates, several
of them hit 100% training accuracy on this dataset almost immediately — a
red flag disclosed here rather than quietly fixed and forgotten.)

## 6. Final, unseen-test results (touched once)

**Update: `train.py` was later changed to a training-only script (see the
note at the top of `src/train.py`).** It no longer does a split, CV
comparison, tuning, or evaluation - it just fits ExtraTrees (the config
below) on all 137 rows and saves it, at the person's explicit request, to
maximize training data for the deployed model. The numbers below are from
the earlier, evaluation-based version of the script and describe how that
same model config performs when properly held out - **they are not
re-measured against the current all-data model**, since nothing in the
current pipeline touches a held-out set anymore. If you want a fresh honest
accuracy number for the current model, that needs a separate
evaluation-only run (ask if you'd like that restored as a standalone
script that doesn't affect what gets deployed).

- **Train accuracy:** 90.1%
- **Test accuracy (28 held-out rows, never used for model/hyperparameter
  selection):** **78.6%**
- **Test ROC-AUC:** 0.750
- **Test Log Loss:** 0.612
- **Test Brier Score:** 0.210
- **Confusion matrix:** `[[10, 4], [2, 12]]` (rows=actual, cols=predicted;
  order = [Team1 wins, Team2 wins])
- **Train − test gap:** 11.6 points — reasonable for a 137-row dataset, not
  the near-perfect/near-random split that would signal a broken pipeline.

Probabilities are calibrated via 5-fold sigmoid (Platt) calibration
(`CalibratedClassifierCV`) so `predict_match()` outputs meaningful
probabilities, not just a label.

**Honest framing:** 78.6% on 28 test rows has real sampling noise (±1 wrong
prediction moves it by ~3.6 points), and because rows aren't independent of
history in a verifiable way, this number should be read as "meaningfully
better than the ~50% coin-flip baseline, in the 65–80% ballpark" rather than
a precise figure. That matches what's realistic for an 8-team, 137-match
dataset with no raw per-ball data.

## 7. Confidence bands

| Probability margin | Label |
|---|---|
| 50–55% | Very Low |
| 55–60% | Low |
| 60–70% | Medium |
| 70–80% | High |
| 80%+ | Very High |

## 8. Handling unseen teams / venues / matchups

`predict.py` never returns `NaN`. For a team/venue with no history:

- Team stats fall back to a **shrinkage estimate** — observed win rate
  blended with the league average, weighted by a prior of 10 "phantom"
  average matches (so 1–2 observed matches can't produce an unrealistic 0%
  or 100% win rate).
- A team with zero history gets the pure league average.
- Venue stats fall back to league-average venue stats.
- Head-to-head with no shared history defaults to a neutral 50% prior.
- `predict_match()` returns a `warnings` list disclosing exactly which
  fallbacks were used, so the caller knows when a prediction is
  low-information.

## 9. Project structure

```
cricket_prediction/
├── data/Caribbean Premier League.csv
├── models/
│   ├── best_model.pkl            # calibrated champion model (refit on all data)
│   ├── feature_pipeline.pkl      # numeric/categorical column lists
│   ├── feature_columns.json
│   ├── model_metrics.json        # only produced by the earlier evaluation-based train.py; not generated by the current training-only script
│   └── feature_importance.png
├── src/
│   ├── data_preprocessing.py
│   ├── feature_engineering.py
│   ├── train.py                  # full training + evaluation pipeline
│   ├── evaluate.py                # comparison table + feature importance chart
│   └── predict.py                 # predict_match() interface
├── app.py                         # Streamlit UI
├── requirements.txt
└── README.md
```

## 10. Running it

```bash
pip install -r requirements.txt

# retrain everything (prints the full comparison table + final test metrics)
python src/train.py

# regenerate the feature-importance chart / comparison printout
python src/evaluate.py

# quick CLI sanity check of the prediction function
python src/predict.py

# launch the UI
streamlit run app.py
```

`predict_match()` signature:

```python
predict_match(
    team1, team2, venue,
    toss_winner=None, toss_decision=None,      # leave both None for Mode A (before toss)
    temperature=None, humidity=None, rain_probability=None,  # default to league averages if omitted
)
# -> {"team1", "team2", "team1_probability", "team2_probability",
#     "predicted_winner", "confidence", "mode", "warnings"}
```

## 11. Known limitations (please read before deploying this anywhere real)

1. **No genuine out-of-time test.** Every evaluation number here is
   cross-validated/held-out but not chronological, because the source data
   has no dates. If a raw match log with dates becomes available, this whole
   pipeline should be rerun with real `TimeSeriesSplit` validation.
2. **137 rows is small.** CV standard deviations (±0.06–0.11 accuracy) are
   non-trivial — treat the 78.6% test accuracy as a ballpark, not a precise
   figure.
3. **Feature importance shows team identity (`team1`/`team2`) as the single
   strongest signal** — with only 8 teams and ~17 matches per team on
   average, the model is partly learning "which teams are historically
   strong" rather than purely reacting to the engineered stats. This is
   disclosed in `models/feature_importance.png`, not hidden.
4. Weather features (`temperature`, `humidity`, `rain_probability`) showed
   weak correlation with the outcome in this dataset — they're included
   because they were requested and are pre-match-available, but they are not
   doing much work in the current model.
