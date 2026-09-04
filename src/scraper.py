"""
scraper.py
----------
Scrapes pre-match stats from a CREX (crex.com) match page and maps them onto
the same stat names used by predict.py's override arguments, so a match code
/ URL can auto-fill the Streamlit UI instead of typing everything by hand.

IMPORTANT - READ BEFORE RELYING ON THIS:
  - This has NOT been tested end-to-end in this environment. The sandbox
    that built this project can only reach a fixed allow-list of domains
    (pypi, github, etc.) and crex.com is not on it, so these HTTP calls
    were never actually executed here. The parsing logic below is adapted
    from the scraper code you pasted, with light cleanup, but you need to
    run it against a real match page yourself and report back what breaks.
  - Two of the original functions (`wicket_lost`, `first_inn_scr`) depend on
    a hardcoded match-URL "slug" template (e.g.
    "mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}") that's
    specific to one tournament. That template can't be derived from a bare
    match code for an arbitrary future match - CREX's slug format varies by
    league/season. `scrape_match()` below takes an optional `slug_template`
    parameter for this reason; if you don't supply one, the recent-form
    wicket/run scrape and the venue-average-score scrape are skipped and
    fall back to the historical CSV's column means (same fallback the
    original functions already used for their own edge cases).
"""
import requests
from bs4 import BeautifulSoup

CREX_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_script_and_soup(url):
    r = requests.get(url, headers=CREX_HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")
    script = (
        str(soup.find("script", {"id": "app-root-state"}))
        .replace("&q;", "")
        .replace("&a;", "")
        .replace("/", "")
        .replace("&s;", "")
    )
    return script, soup, r


# ---------------------------------------------------------------------------
# Team names
# ---------------------------------------------------------------------------
def find_team_name(script, flag=0):
    corrector_index = script.find("team1:") + 6
    corrector_last_index = script[corrector_index:].find(",")
    corrector_name = script[corrector_index: corrector_index + corrector_last_index]

    script_index = script.find("https:api.goscorer.comapiv3getSV3")
    if script_index == -1:
        script_index = script.find("apiphpgetSV3")
    modi_script = script[script_index:]
    start_index = modi_script.find("team1:")
    last_index = modi_script.find("team2short:") + 15
    names_line = modi_script[start_index:last_index]

    team1_index = names_line.find("team1_f_n:") + 10
    team1_last_index = names_line[team1_index:].find(",")
    team1_name = names_line[team1_index: team1_index + team1_last_index]
    if team1_name == "null":
        team1_index = names_line.find("team1short:") + 11
        team1_last_index = names_line[team1_index:].find(",")
        team1_name = names_line[team1_index: team1_index + team1_last_index]

    team1_short_name_index = names_line.find("team1:") + 6
    team1_short_name_last_index = names_line[team1_short_name_index:].find(",")
    team1_short_name = names_line[team1_short_name_index:team1_short_name_index + team1_short_name_last_index]

    team2_index = names_line.find("team2_f_n") + 10
    team2_last_index = names_line[team2_index:].find(",")
    team2_name = names_line[team2_index:team2_index + team2_last_index]
    if team2_name == "null":
        team2_index = names_line.find("team2short:") + 11
        team2_last_index = names_line[team2_index:].find(",")
        team2_name = names_line[team2_index:team2_index + team2_last_index]

    team2_short_name_index = names_line.find("team2:") + 6
    team2_short_name_last_index = names_line[team2_short_name_index:].find(",")
    team2_short_name = names_line[team2_short_name_index:team2_short_name_index + team2_short_name_last_index]

    if len(team1_name) < len(team1_short_name):
        team1_name, team1_short_name = team1_short_name, team1_name
    if len(team2_name) < len(team2_short_name):
        team2_name, team2_short_name = team2_short_name, team2_name

    if flag == 0:
        team1_points = 0
        team2_points = 0
        for ch in corrector_name:
            team1_points += team1_name.count(ch)
            team2_points += team2_name.count(ch)
        if team1_points < team2_points:
            team1_short_name, team2_short_name = team2_short_name, team1_short_name
            team1_name, team2_name = team2_name, team1_name

    return [team1_name, team1_short_name, team2_name, team2_short_name]


# ---------------------------------------------------------------------------
# Win rate / recent form / head-to-head
# ---------------------------------------------------------------------------
def find_win_rate(script):
    """Returns [team1_win_rate, team2_win_rate] as percentages, in that order
    (unverified against a live page in this environment - confirm order
    matches your existing scraper's usage)."""
    index = script.find("tcd:") + 7
    last_index = script[index:].find("]}") + 1
    modi_script = script[index:last_index + index]

    start = 0
    win_rate = []
    while True:
        tm_index = modi_script.find("tm:", start)
        if tm_index == -1:
            break
        modi_tm = modi_script[tm_index + 3:]
        tm_last_index = modi_tm.find(",")
        total_match = modi_tm[:tm_last_index]
        w_index = modi_tm.find("w:")
        modi_win = modi_tm[w_index + 2:]
        w_last_index = modi_win.find(",")
        wins = modi_win[:w_last_index]
        try:
            win_rate.append(float(wins) / float(total_match) * 100)
        except (ZeroDivisionError, ValueError):
            win_rate.append(0)
        start = tm_index + 1

    return win_rate


def h2h_win_rate(script, team_names):
    index = script.find("https:stats.crickapi.comlivegetPreLiveStats:") + 48
    last_index = script[index:].find("]") + 1
    modi_script = script[index:index + last_index]

    start = 0
    winners = []
    while True:
        result_index = modi_script.find("result:", start)
        if result_index == -1:
            break
        m_script = modi_script[result_index + 7:]
        coma_index = m_script.find("}")
        result_line = m_script[:coma_index]
        won_index = result_line.find(" Won by")
        if won_index == -1:
            won_index = result_line.find(" Won (DLS Method)")
        winner = result_line[:won_index].replace("-", "")
        winners.append(winner)
        start = result_index + 1

    if len(winners) == 0:
        return 0
    return winners.count(team_names[1].replace("-", "")) / len(winners) * 100


def recent_form(script):
    """Returns [team1_recent_form, team2_recent_form] as win counts."""
    index = script.find("tf:") + 3
    modi_script = script[index:]
    last_index = modi_script.find(",")
    rf_line = modi_script[:last_index + 1]

    i = 0
    team_rf = 0
    teams_rf = []
    while i < len(rf_line):
        if rf_line[i] == "W":
            team_rf += int(rf_line[i + 1])
        elif rf_line[i] in ["-", ","]:
            teams_rf.append(team_rf)
            team_rf = 0
        i += 1

    return teams_rf


# ---------------------------------------------------------------------------
# Toss / weather / venue / pitch
# ---------------------------------------------------------------------------
def toss(script, soup, team_names):
    string_soup = str(soup)
    index = string_soup.find("won the toss and chose to")
    if index == -1:
        return None, None  # toss hasn't happened yet - Mode A (before toss)
    new_text = string_soup[index - 10:index - 10 + 80]

    toss_index = new_text.find(">")
    toss_last_index = new_text.find("<")
    toss_line = new_text[toss_index + 1: toss_last_index]

    space_index = toss_line.find(" ")
    toss_winner_raw = toss_line[:space_index]
    to_index = toss_line.find(" chose")
    toss_decision = toss_line[to_index + 10:].capitalize()

    team1 = team_names[0].lower()
    team2 = team_names[2].lower()
    team1_points = sum(team1.count(ch) for ch in toss_winner_raw.lower())
    team2_points = sum(team2.count(ch) for ch in toss_winner_raw.lower())

    if team1_points < team2_points:
        toss_winner = team2.upper() if "-" in team2 else team2.title()
    else:
        toss_winner = team1.upper() if "-" in team1 else team1.title()

    return toss_winner, toss_decision


def temperature(script, df):
    index = script.find("crT:")
    text = script[index + 4:]
    last_index = text.find("˚")
    try:
        return float(text[:last_index])
    except ValueError:
        return df["temperature"].mean()


def humidity(script, df):
    index = script.find("hum:")
    try:
        return float(script[index + 4:index + 6])
    except ValueError:
        return df["humidity"].mean()


def rain_prob(script, df):
    index = script.find("rP:")
    try:
        return float(script[index + 3:index + 5])
    except ValueError:
        return df["rain_probability"].mean()


def venue(script):
    index = script.find("v:")
    modi_script = script[index + 2:]
    coma_index = modi_script.find(",")
    venue_name = modi_script[:coma_index]

    replacements = [
        ("Cricket", ""), ("  ", " "),
    ]
    if "Cricket" in venue_name:
        venue_name = venue_name.replace("Cricket", "").replace("  ", " ")
    if "Hambantota" in venue_name:
        venue_name = venue_name.replace(" Hambantota", "")
    if " Lords Ground" in venue_name:
        venue_name = venue_name.replace(" Lords Ground", "Lords Ground")
    if venue_name == "Lords":
        venue_name = "Lords Ground"
    if "Manchester" in venue_name:
        venue_name = venue_name.replace("Manchester", "").replace("  ", "")[:-1]
    if "Ground" in venue_name:
        venue_name = venue_name.replace("Ground", "").replace(" ", "")
    if "London" in venue_name:
        venue_name = venue_name.replace("London", "")[:-1]
    if "Cardiff" in venue_name:
        venue_name = venue_name.replace("Cardiff", "")[:-2]
    if "Southampton" in venue_name:
        venue_name = venue_name.replace("Southampton", "")[:-1]
    if venue_name == "Sophia Garden":
        venue_name = "Sophia Gardens"

    return venue_name


def pitch_type(script):
    index = script.find("prt:") + 5
    last_index = script.find(",pitch_report:")
    pitch_full_line = script[index:last_index]

    batting_score_index = pitch_full_line.find("batting_pitch_score:")
    modi_batting_score = pitch_full_line[batting_score_index + 20:]
    batting_score_last_index = modi_batting_score.find(",")

    try:
        batting_score = float(modi_batting_score[:batting_score_last_index])

        swing_score_index = pitch_full_line.find("swing_pitch_score:")
        modi_swing_score = pitch_full_line[swing_score_index + 18:]
        swing_score = float(modi_swing_score[:modi_swing_score.find(",")])

        pitch_score_index = pitch_full_line.find("pace_pitch_score:")
        modi_pitch_score = pitch_full_line[pitch_score_index + 17:]
        pitch_score = float(modi_pitch_score[:modi_pitch_score.find(",")])

        seam_score_index = pitch_full_line.find("seam_pitch_score:")
        modi_seam_score = pitch_full_line[seam_score_index + 17:]
        seam_score = float(modi_seam_score[:modi_seam_score.find(",")])

        bounce_score_index = pitch_full_line.find("bounce_pitch_score:")
        modi_bounce_score = pitch_full_line[bounce_score_index + 19:]
        bounce_score = float(modi_bounce_score[:modi_bounce_score.find(",")])

        spin_score = float(pitch_full_line[-1])

        bowling_avg = (swing_score + pitch_score + seam_score + bounce_score + spin_score) / 5

        if batting_score == bowling_avg:
            return "Balanced"
        elif batting_score < bowling_avg:
            return "Bowling"
        else:
            return "Batting"
    except ValueError:
        return "Balanced"


def chase_win_rate(script, df):
    index = script.find("tm:")
    modi_script = script[index:]
    last_index = modi_script.find("}")
    modi_script = modi_script[:last_index]

    tm_index = modi_script.find(":")
    modi_script = modi_script[tm_index + 1:]
    tm_last_index = modi_script.find(",")
    try:
        tm = float(modi_script[:tm_last_index])
        y_index = modi_script.find("y:")
        y = float(modi_script[y_index + 2:])
        return y / tm * 100
    except (ValueError, ZeroDivisionError):
        return df["chasing_success_rate"].mean()


# ---------------------------------------------------------------------------
# Recent-form (avg runs / wickets, last 5) - TOURNAMENT-SPECIFIC
# ---------------------------------------------------------------------------
# These need to visit each team's last few match pages individually, and the
# match-page URL is "https://crex.com/cricket-live-score/<slug>-<code>/match-details"
# where <slug> (e.g. "mil-vs-tr-25th-match-the-hundred-2026-men-match-updates")
# is specific to one league/season and NOT derivable from a bare match code.
# Pass slug_template="https://crex.com/cricket-live-score/{slug}-{code}/match-details"
# with the correct <slug> for your tournament to enable this; otherwise
# scrape_match() falls back to the historical CSV's column means, same as
# the original code's own ZeroDivisionError fallback.

def _find_recent_match_links(word, script, slug_template):
    index = script.find(word) + 4
    last_index = script.find("t2f:") if word == "t1f:" else script.find("tb:")
    all_matches_codes = script[index:last_index].replace(",", "|")

    match_hash_codes = []
    start = 0
    while True:
        match_last_index = all_matches_codes.find("|", start)
        if match_last_index == -1:
            break
        code_index = match_last_index
        while all_matches_codes[code_index] != "-":
            code_index -= 1
        correct_code = all_matches_codes[code_index + 1:match_last_index]
        if correct_code and correct_code[0] == "^":
            correct_code = correct_code[1:]
        match_hash_codes.append(correct_code)
        start = match_last_index + 1

    new_codes = []
    for mc in match_hash_codes:
        for token in ("Semi Final ", "Eliminator", "Qualifier"):
            if token in mc:
                mc = mc.replace(token, "")
        new_codes.append(mc)

    match_nos, match_codes = [], []
    for i in range(min(5, len(new_codes))):
        mhc = new_codes[i]
        try:
            if len(mhc) > 2 and mhc[1] == "2" and mhc[2] == "2":
                match_no = mhc[:2]
            elif len(mhc) > 2 and mhc[2] == "2":
                match_no = mhc[:2]
            else:
                match_no = mhc[:1]
            len_no = len(match_no)
            match_code = mhc[len_no + 1: len_no + 1 + 4]
            if match_code and str(match_code[0]).isalpha():
                match_code = match_code[:-1]
            if "^" in match_no:
                match_no = match_no[1]
            match_nos.append(match_no)
            match_codes.append(match_code)
        except IndexError:
            break

    links, resolved_codes = [], []
    for code in match_codes:
        url = slug_template.format(code=code)
        r = _try_url(url)
        if r is not None:
            links.append(url)
            resolved_codes.append(code)
            continue
        url2 = slug_template.format(code=code[:-1])
        r2 = _try_url(url2)
        if r2 is not None:
            links.append(url2)
            resolved_codes.append(code[:-1])
            continue
        url3 = slug_template.format(code=code[1:])
        r3 = _try_url(url3)
        if r3 is not None:
            links.append(url3)
            resolved_codes.append(code[1:])

    return links, resolved_codes


def _try_url(url):
    """Returns the response if the page looks like a real match page
    (has a populated app-root-state script), else None."""
    try:
        r = requests.get(url, headers=CREX_HEADERS, timeout=10)
    except requests.RequestException:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", {"id": "app-root-state"})
    if script_tag is None:
        return None
    text = str(script_tag)
    if "ssr-bootstrap-v1" in text and "team1" not in text:
        return None  # empty/placeholder page
    return r


def wicket_lost(team_names, script, df, slug_template):
    """Returns (team1_avg_wickets_last5, team2_avg_wickets_last5,
    team1_avg_runs_last5, team2_avg_runs_last5), falling back to
    historical means wherever a scrape step comes up empty."""
    links1, codes1 = _find_recent_match_links("t1f:", script, slug_template)
    links2, codes2 = _find_recent_match_links("t2f:", script, slug_template)

    team1_runs, team1_wkts, team2_runs, team2_wkts = [], [], [], []

    for lk in links1:
        r = _try_url(lk)
        if r is None:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        s = (
            str(soup.find("script", {"id": "app-root-state"}))
            .replace("&q;", "").replace("&a;", "").replace("/", "")
        )
        try:
            team1short = find_team_name(s, 1)[1]
            key = "score1:" if team1short == team_names[1] else "score2:"
            idx = s.find(key) + len(key)
            modi = s[idx:]
            score = modi[:modi.find(",")]
            dash = score.find("-") + 1
            team1_runs.append(float(score[:dash - 1]))
            team1_wkts.append(float(score[dash:]))
        except (ValueError, IndexError):
            continue

    for lk in links2:
        r = _try_url(lk)
        if r is None:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        s = (
            str(soup.find("script", {"id": "app-root-state"}))
            .replace("&q;", "").replace("&a;", "").replace("/", "")
        )
        try:
            team2short = find_team_name(s, 1)[1]
            key = "score1:" if team2short == team_names[3] else "score2:"
            idx = s.find(key) + len(key)
            modi = s[idx:]
            score = modi[:modi.find(",")]
            dash = score.find("-") + 1
            team2_runs.append(float(score[:dash - 1]))
            team2_wkts.append(float(score[dash:]))
        except (ValueError, IndexError):
            continue

    t1_avg_wl = sum(team1_wkts) / len(team1_wkts) if team1_wkts else df["team1_avg_wicket_last_5"].mean()
    t2_avg_wl = sum(team2_wkts) / len(team2_wkts) if team2_wkts else df["team2_avg_wicket_last_5"].mean()
    t1_avg_runs = sum(team1_runs) / len(team1_runs) if team1_runs else df["team1_avg_runs_last_5"].mean()
    t2_avg_runs = sum(team2_runs) / len(team2_runs) if team2_runs else df["team2_avg_runs_last_5"].mean()

    return t1_avg_wl, t2_avg_wl, t1_avg_runs, t2_avg_runs


def first_inn_scr(venue_stats_response, df):
    """venue_stats_response: an already-fetched `requests.Response` for
    CREX's venue-stats page (URL not specified in the original snippet -
    pass it in yourself, or leave unused and rely on the df mean fallback)."""
    try:
        text = str(venue_stats_response.text)
        index = text.find('class="venue-avg-val"') + 22
        modi_text = text[index:]
        last_index = modi_text.find("<")
        return float(modi_text[:last_index])
    except (AttributeError, ValueError):
        return df["avg_first_innings_score"].mean()


# ---------------------------------------------------------------------------
# Orchestrator - call this one from the UI
# ---------------------------------------------------------------------------
def scrape_match(match_url, league_df, slug_template=None):
    """
    match_url: full CREX match-details URL, e.g.
        "https://crex.com/cricket-live-score/<slug>-<code>/match-details"
    league_df: the historical CPL dataframe (used for fallback means, exactly
        like the original functions' `df` argument)
    slug_template: OPTIONAL. Needed only for the recent-form wicket/run scrape
        and the venue-average-first-innings-score scrape, which walk a team's
        last few match pages. Those need a URL template specific to the
        tournament, e.g. "https://crex.com/cricket-live-score/{slug}-{{code}}/match-details".
        Without it, team1/team2 avg_runs_last_5 / avg_wicket_last_5 and
        avg_first_innings_score fall back to the historical CSV's column
        means, same as the original code's own ZeroDivisionError fallback.

    Returns a dict shaped to feed straight into predict.predict_match(**kwargs)
    as overrides, plus 'team1'/'team2'/'venue' for the UI to pre-select.
    """
    script, soup, _ = _get_script_and_soup(match_url)

    team_names = find_team_name(script)
    team1, team2 = team_names[0], team_names[2]

    win_rates = find_win_rate(script)
    team1_win_rate = win_rates[0] if len(win_rates) > 0 else league_df["team1_win_rate"].mean()
    team2_win_rate = win_rates[1] if len(win_rates) > 1 else league_df["team2_win_rate"].mean()

    h2h = h2h_win_rate(script, team_names)

    forms = recent_form(script)
    team1_recent_form = forms[0] if len(forms) > 0 else league_df["team1_recent_form"].mean()
    team2_recent_form = forms[1] if len(forms) > 1 else league_df["team2_recent_form"].mean()

    toss_winner, toss_decision = toss(script, soup, team_names)

    temp = temperature(script, league_df)
    hum = humidity(script, league_df)
    rain = rain_prob(script, league_df)
    venue_name = venue(script)
    p_type = pitch_type(script)
    chase_wr = chase_win_rate(script, league_df)

    # These two need the extra per-match-page scrape (slug_template) - without
    # it, fall back to historical means (matches the original functions'
    # own fallback behaviour on ZeroDivisionError).
    t1_avg_runs = league_df["team1_avg_runs_last_5"].mean()
    t2_avg_runs = league_df["team2_avg_runs_last_5"].mean()
    t1_avg_wkts = league_df["team1_avg_wicket_last_5"].mean()
    t2_avg_wkts = league_df["team2_avg_wicket_last_5"].mean()
    avg_first_innings = league_df["avg_first_innings_score"].mean()

    if slug_template:
        try:
            t1_avg_wkts, t2_avg_wkts, t1_avg_runs, t2_avg_runs = wicket_lost(
                team_names, script, league_df, slug_template
            )
        except Exception as e:
            print(f"[scraper] recent-form scrape failed ({e}); using historical means instead")

    return {
        "team1": team1, "team2": team2, "venue": venue_name, "pitch_type": p_type,
        "team1_win_rate": team1_win_rate, "team2_win_rate": team2_win_rate,
        "head_to_head_win_rate": h2h,
        "team1_recent_form": team1_recent_form, "team2_recent_form": team2_recent_form,
        "team1_avg_runs_last_5": t1_avg_runs, "team2_avg_runs_last_5": t2_avg_runs,
        "team1_avg_wicket_last_5": t1_avg_wkts, "team2_avg_wicket_last_5": t2_avg_wkts,
        "avg_first_innings_score": avg_first_innings,
        "chasing_success_rate": chase_wr,
        "toss_winner": toss_winner, "toss_decision": toss_decision,
        "temperature": temp, "humidity": hum, "rain_probability": rain,
    }


def win(script, team_names):
    """Only works on a COMPLETED match's page (post-match result section).
    Returns 1 if team2 won, 0 if team1 won, per the same convention as the
    training CSV's `win` column. Returns None if the match hasn't finished
    yet (no result section found) - use scrape_match() alone for pre-match
    prediction, and this only when adding a finished match to the CSV."""
    index = script.find("B:")
    if index == -1:
        return None
    modi_script = script[index + 2:]
    last_index = modi_script.find(" won ")
    if last_index == -1:
        return None
    winner = modi_script[:last_index]

    # a couple of known CREX/actual-franchise-name mismatches from the
    # original scraper (kept here in case they recur in other leagues)
    rename_map = {
        "Oval Invincibles": "MI London",
        "Oval Invincibles Women": "MI London Women",
        "Northern Superchargers": "Sunrisers Leeds",
        "Northern Superchargers Women": "Sunrisers Leeds Women",
    }
    winner = rename_map.get(winner, winner)

    team1 = team_names[0].upper()
    team2 = team_names[2].upper()
    team1points = sum(team1.count(ch) for ch in winner.upper())
    team2points = sum(team2.count(ch) for ch in winner.upper())
    winner = team1 if team1points > team2points else team2

    return 0 if winner == team1 else 1


def scrape_completed_match(match_url, league_df, slug_template=None):
    """Like scrape_match(), but for a FINISHED match: also scrapes the
    result and fills in the two venue-win-rate columns (which the live
    pre-match scrape doesn't cover) from historical data, so the result is
    a CSV-ready row. Returns None for 'win' if the match isn't finished
    yet - check for that before appending to the training CSV."""
    script, soup, _ = _get_script_and_soup(match_url)
    stats = scrape_match(match_url, league_df, slug_template=slug_template)

    team_names = find_team_name(script)
    result = win(script, team_names)

    t1 = league_df[(league_df["team1"] == stats["team1"])]["team1_venue_win_rate"]
    t2 = league_df[(league_df["team2"] == stats["team2"])]["team2_venue_win_rate"]
    stats["team1_venue_win_rate"] = float(t1.mean()) if len(t1) else float(league_df["team1_venue_win_rate"].mean())
    stats["team2_venue_win_rate"] = float(t2.mean()) if len(t2) else float(league_df["team2_venue_win_rate"].mean())
    stats["win"] = result

    return stats


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <crex_match_url>")
        sys.exit(1)
    from data_preprocessing import load_raw, clean
    df = clean(load_raw())
    result = scrape_match(sys.argv[1], df)
    import json
    print(json.dumps(result, indent=2, default=str))
