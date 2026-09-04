import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
from predict import predict_match, compute_defaults
from data_preprocessing import load_raw, clean

st.set_page_config(page_title="CPL Match Predictor", page_icon="🏏", layout="centered")

st.title("🏏 CPL Match Predictor")
st.caption(
    "Built on 137 historical Caribbean Premier League matchups. "
    "The source data has no date column, so this model is validated with "
    "cross-validation rather than genuine chronological hold-out - see README "
    "for details. Treat predictions as directional, not certain."
)

# show + clear any message left behind by an action that triggered a rerun
# (e.g. the add-match-and-retrain button) - shown here so it survives the
# rerun instead of vanishing before it's readable
pending = st.session_state.pop("_last_sync_message", None)
if pending:
    kind, text = pending
    getattr(st, kind)(text)

df = clean(load_raw())
st.caption(f"📊 Training dataset currently has **{len(df)} rows** (starts at 137 - if this "
           f"number doesn't go up after adding a match, the local CSV write isn't happening).")
teams = sorted(set(df["team1"]).union(df["team2"]))
venues = sorted(df["venue"].unique())

# ---------------------------------------------------------------------------
# Live scrape from CREX (experimental - see src/scraper.py for caveats)
# ---------------------------------------------------------------------------
with st.expander("🔴 Fetch live stats from CREX (experimental)"):
    st.caption(
        "Pulls team names, win rate, recent form, head-to-head, toss, weather, "
        "venue and pitch type straight from a CREX match page. This has not "
        "been tested against the live site from this environment - if it "
        "errors, the error message will tell us what to fix. Recent-form "
        "avg runs/wickets need an optional per-tournament URL slug template "
        "(see below) or they'll fall back to historical averages."
    )
    crex_url = st.text_input("CREX match URL", placeholder="https://crex.com/cricket-live-score/.../match-details")
    slug_template = st.text_input(
        "Optional: match-URL slug template (for recent-form scrape)",
        placeholder="https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}/match-details",
    )
    if st.button("Fetch stats from CREX"):
        try:
            import scraper
            scraped = scraper.scrape_match(crex_url, df, slug_template=slug_template or None)
            st.session_state["_scraped"] = scraped
            # pre-fill the stat widgets directly via their keys
            key_map = {
                "t1_wr": "team1_win_rate", "t2_wr": "team2_win_rate",
                "t1_form": "team1_recent_form", "t2_form": "team2_recent_form",
                "t1_runs": "team1_avg_runs_last_5", "t2_runs": "team2_avg_runs_last_5",
                "t1_wkts": "team1_avg_wicket_last_5", "t2_wkts": "team2_avg_wicket_last_5",
                "h2h": "head_to_head_win_rate", "fis": "avg_first_innings_score",
                "chase": "chasing_success_rate",
            }
            for widget_key, scraped_key in key_map.items():
                if scraped.get(scraped_key) is not None:
                    st.session_state[widget_key] = round(float(scraped[scraped_key]), 2)
            st.success(f"Fetched: {scraped['team1']} vs {scraped['team2']} at {scraped['venue']}")
            st.rerun()
        except Exception as e:
            st.error(f"CREX fetch failed: {e}")

    st.markdown("---")
    st.caption(
        "**For a match that's already finished:** this scrapes the result too, "
        "appends the full row to the training CSV, and retrains the model on "
        "the updated dataset (137 rows -> 138, etc.). Only works once CREX "
        "shows a final result on the page - it'll tell you if the match "
        "isn't over yet."
    )
    completed_url = st.text_input(
        "CREX match URL (completed match)",
        placeholder="https://crex.com/cricket-live-score/.../match-details",
        key="completed_url",
    )
    if st.button("Add this match to training data & retrain"):
        from data_preprocessing import append_row, load_added_urls, mark_url_added

        already_added = load_added_urls()
        if completed_url in already_added:
            st.session_state["_last_sync_message"] = (
                "warning", f"This URL was already added before - skipping to avoid a duplicate row. "
                           f"({completed_url})"
            )
            st.rerun()

        try:
            import scraper
            import train as train_module
            row = scraper.scrape_completed_match(completed_url, df, slug_template=slug_template or None)
            if row.get("win") is None:
                st.session_state["_last_sync_message"] = (
                    "error", "This match doesn't have a final result on CREX yet - "
                             "can't add it to training data until it's finished."
                )
            else:
                append_row(row)
                mark_url_added(completed_url)
                winner = row['team2'] if row['win'] == 1 else row['team1']
                with st.spinner("Retraining on the updated dataset..."):
                    train_module.main()

                st.session_state["_last_sync_message"] = (
                    "success",
                    f"Added {row['team1']} vs {row['team2']} (winner: {winner}) and retrained on "
                    f"{len(clean(load_raw()))} rows. This is only on local (ephemeral) disk and WILL "
                    f"be lost on the next reboot - use the 'Download updated files' button below to "
                    f"save it permanently."
                )
            st.rerun()
        except Exception as e:
            st.error(f"Failed to add match / retrain: {e}")

scraped = st.session_state.get("_scraped")

col1, col2 = st.columns(2)
with col1:
    t1_options = teams if not scraped else sorted(set(teams) | {scraped["team1"]})
    t1_index = t1_options.index(scraped["team1"]) if scraped and scraped["team1"] in t1_options else 0
    team1 = st.selectbox("Team 1", t1_options, index=t1_index)
with col2:
    t2_options = teams if not scraped else sorted(set(teams) | {scraped["team2"]})
    t2_index = t2_options.index(scraped["team2"]) if scraped and scraped["team2"] in t2_options else 1
    team2 = st.selectbox("Team 2", t2_options, index=t2_index)

v_options = venues if not scraped else sorted(set(venues) | {scraped["venue"]})
v_index = v_options.index(scraped["venue"]) if scraped and scraped["venue"] in v_options else 0
venue = st.selectbox("Venue", v_options, index=v_index)

# Recompute the auto-filled defaults whenever team1/team2/venue changes
defaults_key = (team1, team2, venue)
if st.session_state.get("_defaults_key") != defaults_key:
    st.session_state["_defaults_key"] = defaults_key
    st.session_state["_defaults"] = compute_defaults(team1, team2, venue)
defaults = st.session_state["_defaults"]

st.subheader("Prediction Mode")
default_mode_index = 1 if (scraped and scraped.get("toss_winner")) else 0
mode = st.radio("Choose mode", ["Before Toss", "After Toss"], horizontal=True, index=default_mode_index)

toss_winner, toss_decision = None, None
if mode == "After Toss":
    toss_options = [team1, team2]
    toss_default_index = 0
    if scraped and scraped.get("toss_winner") in toss_options:
        toss_default_index = toss_options.index(scraped["toss_winner"])
    toss_winner = st.selectbox("Toss Winner", toss_options, index=toss_default_index)
    decision_options = ["Bat", "Bowl"]
    decision_index = 0
    if scraped and scraped.get("toss_decision") in decision_options:
        decision_index = decision_options.index(scraped["toss_decision"])
    toss_decision = st.radio("Toss Decision", decision_options, horizontal=True, index=decision_index)

with st.expander("Match stats (auto-filled from history — edit to override)"):
    st.caption(
        "These are computed from historical data for the teams/venue you picked "
        "above. Change any value to override it — e.g. to reflect a player "
        "injury, a squad change, or stats more recent than this dataset."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{team1}**")
        team1_win_rate = st.number_input("Win rate (%)", value=defaults["team1_win_rate"], key="t1_wr")
        team1_recent_form = st.number_input("Recent form (wins in last N)", value=defaults["team1_recent_form"], key="t1_form")
        team1_venue_win_rate = st.number_input("Venue win rate (%)", value=defaults["team1_venue_win_rate"], key="t1_venue")
        team1_avg_runs_last_5 = st.number_input("Avg runs (last 5)", value=defaults["team1_avg_runs_last_5"], key="t1_runs")
        team1_avg_wicket_last_5 = st.number_input("Avg wickets lost (last 5)", value=defaults["team1_avg_wicket_last_5"], key="t1_wkts")
    with c2:
        st.markdown(f"**{team2}**")
        team2_win_rate = st.number_input("Win rate (%)", value=defaults["team2_win_rate"], key="t2_wr")
        team2_recent_form = st.number_input("Recent form (wins in last N)", value=defaults["team2_recent_form"], key="t2_form")
        team2_venue_win_rate = st.number_input("Venue win rate (%)", value=defaults["team2_venue_win_rate"], key="t2_venue")
        team2_avg_runs_last_5 = st.number_input("Avg runs (last 5)", value=defaults["team2_avg_runs_last_5"], key="t2_runs")
        team2_avg_wicket_last_5 = st.number_input("Avg wickets lost (last 5)", value=defaults["team2_avg_wicket_last_5"], key="t2_wkts")

    st.markdown("**Matchup / venue**")
    c3, c4 = st.columns(2)
    with c3:
        head_to_head_win_rate = st.number_input(f"Head-to-head win rate for {team1} (%)", value=defaults["head_to_head_win_rate"], key="h2h")
        avg_first_innings_score = st.number_input("Avg 1st innings score at venue", value=defaults["avg_first_innings_score"], key="fis")
    with c4:
        chasing_success_rate = st.number_input("Chasing success rate at venue (%)", value=defaults["chasing_success_rate"], key="chase")

    if st.button("Reset stats to auto-computed values"):
        fresh = compute_defaults(team1, team2, venue)
        st.session_state["_defaults"] = fresh
        for widget_key, stat_key in {
            "t1_wr": "team1_win_rate", "t2_wr": "team2_win_rate",
            "t1_form": "team1_recent_form", "t2_form": "team2_recent_form",
            "t1_venue": "team1_venue_win_rate", "t2_venue": "team2_venue_win_rate",
            "t1_runs": "team1_avg_runs_last_5", "t2_runs": "team2_avg_runs_last_5",
            "t1_wkts": "team1_avg_wicket_last_5", "t2_wkts": "team2_avg_wicket_last_5",
            "h2h": "head_to_head_win_rate", "fis": "avg_first_innings_score",
            "chase": "chasing_success_rate",
        }.items():
            st.session_state[widget_key] = fresh[stat_key]
        st.session_state.pop("_scraped", None)
        st.rerun()

with st.expander("Weather (optional - league averages used if left blank)"):
    weather_defaults = scraped or {}
    temperature = st.number_input(
        "Temperature (°C)", value=weather_defaults.get("temperature"), placeholder="e.g. 28.5", key="temp"
    )
    humidity = st.number_input(
        "Humidity (%)", value=weather_defaults.get("humidity"), placeholder="e.g. 80", key="hum"
    )
    rain_probability = st.number_input(
        "Rain probability (%)", value=weather_defaults.get("rain_probability"), placeholder="e.g. 40", key="rain"
    )

if st.button("PREDICT MATCH", type="primary", use_container_width=True):
    if team1 == team2:
        st.error("Team 1 and Team 2 must be different.")
    else:
        result = predict_match(
            team1, team2, venue,
            toss_winner=toss_winner, toss_decision=toss_decision,
            temperature=temperature, humidity=humidity, rain_probability=rain_probability,
            team1_win_rate=team1_win_rate, team2_win_rate=team2_win_rate,
            head_to_head_win_rate=head_to_head_win_rate,
            team1_recent_form=team1_recent_form, team2_recent_form=team2_recent_form,
            team1_venue_win_rate=team1_venue_win_rate, team2_venue_win_rate=team2_venue_win_rate,
            team1_avg_runs_last_5=team1_avg_runs_last_5, team2_avg_runs_last_5=team2_avg_runs_last_5,
            team1_avg_wicket_last_5=team1_avg_wicket_last_5, team2_avg_wicket_last_5=team2_avg_wicket_last_5,
            avg_first_innings_score=avg_first_innings_score, chasing_success_rate=chasing_success_rate,
        )

        st.markdown("---")
        st.markdown("### 🏏 PREDICTION")

        c1, c2 = st.columns(2)
        c1.metric(result["team1"], f"{result['team1_probability']*100:.1f}%")
        c2.metric(result["team2"], f"{result['team2_probability']*100:.1f}%")
        st.progress(result["team1_probability"])

        st.markdown(f"**Predicted Winner:** {result['predicted_winner']}")
        st.markdown(f"**Confidence:** {result['confidence']}")
        st.markdown(f"**Mode:** {'Before Toss' if result['mode']=='before_toss' else 'After Toss'}")

        st.markdown("**Key Factors**")
        st.markdown(
            "- Team win-rate & recent form difference\n"
            "- Venue win-rate\n"
            "- Head-to-head record\n"
            "- Bowling/batting recent averages\n"
            + ("- Toss winner & decision\n" if result["mode"] == "after_toss" else "")
        )

        if result["warnings"]:
            st.info("Notes:\n" + "\n".join(f"- {w}" for w in result["warnings"]))

st.markdown("---")
with st.expander("📥 Download updated data + model (to persist manually on GitHub)"):
    st.caption(
        "Since local changes on Streamlit Community Cloud are wiped on every "
        "reboot, this packages the current CSV, added-match log, and trained "
        "model into a zip. Download it, unzip it, and drag the files into "
        "your GitHub repo (replacing the existing ones) via github.com's "
        "web upload, then commit - that's what makes any added matches "
        "permanent."
    )
    if st.button("Prepare download"):
        import zipfile
        import io as _io

        buf = _io.BytesIO()
        files_to_zip = {
            "data/Caribbean Premier League.csv": "data/Caribbean Premier League.csv",
            "data/added_match_urls.json": "data/added_match_urls.json",
            "models/best_model.pkl": "models/best_model.pkl",
            "models/feature_pipeline.pkl": "models/feature_pipeline.pkl",
            "models/feature_columns.json": "models/feature_columns.json",
        }
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, local_path in files_to_zip.items():
                try:
                    zf.write(local_path, arcname=arcname)
                except FileNotFoundError:
                    pass  # e.g. added_match_urls.json doesn't exist until the first match is added
        buf.seek(0)
        st.download_button(
            "⬇️ Download cpl_updated_data.zip",
            data=buf,
            file_name="cpl_updated_data.zip",
            mime="application/zip",
        )

st.markdown("---")
with st.expander("Model info"):
    import json
    try:
        with open("models/model_metrics.json") as f:
            m = json.load(f)
        st.write(f"**Champion model:** {m['champion']}")
        st.write(f"**Unseen test accuracy:** {m['test_metrics']['accuracy']*100:.1f}%")
        st.write(f"**Test ROC-AUC:** {m['test_metrics']['roc_auc']:.3f}")
        st.write(f"**Validation approach:** {m['note']}")
    except FileNotFoundError:
        st.write("Run `python src/train.py` first to generate model artifacts.")
