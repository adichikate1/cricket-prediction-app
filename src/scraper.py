"""
scraper.py
----------
The functions below (find_team_name, find_win_rate, h2h_win_rate,
recent_form, link, wicket_lost, first_inn_scr, chase_win_rate, toss,
temperature, humidity, rain_prob, venue, pitch_type, win) are kept EXACTLY
as given - no changes, no cleanup, no bug fixes. This includes known
issues that were NOT altered per explicit instruction:

  - `link()` and `wicket_lost()` have HARDCODED match-URL slugs specific to
    two particular tournaments ("...the-hundred-2026-men-match-updates-"
    and "...major-league-cricket-2026-match-updates-"). For a CPL match (or
    any other tournament), these will very likely construct wrong URLs,
    since neither hardcoded slug matches CPL's actual URL pattern. This is
    almost certainly why wicket/avg-runs scraping was coming out wrong -
    but per instruction this is left unchanged.
  - `first_inn_scr(r)` takes an already-fetched `requests.Response` for a
    page whose URL isn't specified anywhere in the given code - nothing
    below calls it automatically, since there's no way to know what to
    fetch. Call it yourself with the right response if you have that URL.
  - `toss(script, soup)` takes only 2 args (it calls find_team_name(script)
    internally itself) - not 3.
  - None of these functions send a custom User-Agent header (matching the
    original exactly); only the orchestrator glue below (which is NOT one
    of the pasted functions) sets one for its own top-level page fetch.

This has NOT been tested against the live site from this environment - the
sandbox that built this project can only reach a fixed allow-list of
domains (pypi, github, etc.) and crex.com is not on it.
"""
import requests
from bs4 import BeautifulSoup


def find_team_name(script,flag=0):
    corrector_index = script.find("team1:") + 6
    corrector_last_index = script[corrector_index:].find(",")
    corrector_name = script[corrector_index : corrector_index + corrector_last_index]


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
        temp = team1_name
        team1_name = team1_short_name
        team1_short_name = temp
    if len(team2_name) < len(team2_short_name):
        temp = team2_name
        team2_name = team2_short_name
        team2_short_name = temp


    if flag == 0:
        team1_points = 0
        team2_points = 0
        for ch in corrector_name:
            team1_count = team1_name.count(ch)
            team1_points += team1_count
            team2_count = team2_name.count(ch)
            team2_points += team2_count


        if team1_points < team2_points:
            temp = team1_short_name
            team1_short_name = team2_short_name
            team2_short_name = temp

            temp = team1_name
            team1_name = team2_name
            team2_name = temp


    return [team1_name,team1_short_name,team2_name,team2_short_name]



# team_names = team_name(script)



def find_win_rate(script):
    index = script.find("tcd:") + 7
    last_index = script[index:].find("]}") + 1
    modi_script = script[index:last_index + index]
    # print(modi_script)


    start = 0
    win_rate = []
    avg_runs = []
    while True:
        tm_index = modi_script.find("tm:",start)
        modi_tm = modi_script[tm_index + 3:]
        tm_last_index = modi_tm.find(",")
        total_match = modi_tm[:tm_last_index]
        w_index = modi_tm.find("w:")
        modi_win = modi_tm[w_index + 2:]
        w_last_index = modi_win.find(",")
        wins = modi_win[:w_last_index]
        avg_index = modi_win.find("avg:")
        modi_avg = modi_win[avg_index + 4:]
        avg_last_index = modi_avg.find(",")
        avg = modi_avg[:avg_last_index]
        if tm_index == -1:
            break
        # if avg == "null":
        #     avg_run = float(sum(avg_runs)/len(avg_runs))
        # else:
        #     avg_run = float(avg)
        # avg_runs.append(avg_run)
        try:
            win_rate.append(float(wins)/float(total_match) * 100)
        except ZeroDivisionError:
            win_rate.append(0)
        start = tm_index + 1


    # return win_rate, avg_runs
    return win_rate



# win_rate, avg_runs = find_win_rate()



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
    else:
        return winners.count(team_names[1].replace("-",""))/len(winners) * 100



# h2h_wr = h2h_win_rate()



def recent_form(script):
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



# team_rf = recent_form()



def link(word, script, flag=0):
    index = script.find(word) + 4
    if word == "t1f":
        last_index = script.find("t2f:")
    else:
        last_index = script.find("tb:")
    all_matches_codes = script[index:last_index].replace(",", "|")

    # print(all_matches_codes)


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
        if correct_code[0] == "^":
            correct_code = correct_code[1:]
        match_hash_codes.append(correct_code)
        start = match_last_index + 1


    new_match_hash_codes = []
    for mc in match_hash_codes:
        if "Semi Final " in mc:
            new_match_hash_codes.append(mc.replace("Semi Final ", ""))
        elif "Eliminator" in mc:
            new_match_hash_codes.append(mc.replace("Eliminator", ""))
        elif "Qualifier" in mc:
            new_match_hash_codes.append(mc.replace("Qualifier", ""))
        else:
            new_match_hash_codes.append(mc)


    match_nos = []
    match_codes = []
    for i in range(5):
        try :
            match_hash_code = new_match_hash_codes[i]

            if match_hash_code[1] == "2" and match_hash_code[2] == "2":
                match_no = match_hash_code[:2]
            elif match_hash_code[2] == "2":
                match_no = match_hash_code[:2]
            else:
                match_no = match_hash_code[:1]


            len_match_no = len(match_no)
            match_code = new_match_hash_codes[i][len_match_no + 1: len_match_no + 1 + 4]
            if str(match_code[0]).isalpha():
                match_code = match_code[:-1]
            if "^" in match_no:
                match_no = match_no[1]
            match_nos.append(match_no)
            match_codes.append(match_code)

        except IndexError:
            break


    # if flag == "back":
    #     new_match_codes = []
    #     for code in match_codes:
    #         if len(code) == 4:
    #             new_match_codes.append(code[:-1])
    #         else:
    #             new_match_codes.append(code)
    # elif flag == "front":
    #     new_match_codes = []
    #     for code in match_codes:
    #         if len(code) == 4:
    #             new_match_codes.append(code[1:])
    #         else:
    #             new_match_codes.append(code)
    #     match_codes = new_match_codes
    print(match_codes)
    links = []
    new_match_codes = []
    for n,c in zip(match_nos,match_codes):
        l_r = requests.get(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{c}/match-details")
        l_soup = BeautifulSoup(l_r.text, 'html.parser')
        l_script = str(l_soup.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")
        # with open(".json", "w", encoding="utf-8") as f:
        #     f.write(l_script)
        if l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.32.5,cookies:system-theme=,embedId:}}<script>' and l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.34.2,cookies:system-theme=,embedId:}}<script>' and l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.34.2,cookies:system-theme=,embedId:,appReferrer:}}<script>':
            links.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{c}/match-details")
            print(c)
            new_match_codes.append(c)
        else:
            l_r = requests.get(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{c[:-1]}/match-details")
            l_soup = BeautifulSoup(l_r.text, 'html.parser')
            l_script = str(l_soup.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")
            if l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.32.5,cookies:system-theme=,embedId:}}<script>' and l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.34.2,cookies:system-theme=,embedId:}}<script>' and l_script != '<script id="app-root-state" type="applicationjson">{ssr-bootstrap-v1:{theme:light,isMobile:false,baseHref:,platform:web,userAgent:python-requests2.34.2,cookies:system-theme=,embedId:,appReferrer:}}<script>':
                links.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{c[1:]}/match-details")
                print(c[1:])
                new_match_codes.append(c[1:])
            else:
                links.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{c[:-1]}/match-details")
                print(c[:-1])
                new_match_codes.append(c[:-1])

    return links, new_match_codes


def wicket_lost(team_names, script, df):
    links1, match_hashcodes1 = link("t1f:", script)
    links2, match_hashcodes2  = link("t2f:", script)


    if len(match_hashcodes1) > len(match_hashcodes2):
        links1 = []
        links2 = []
        for match_hashcode in match_hashcodes2:
            if match_hashcode in match_hashcodes1:
                match_hashcodes1.remove(match_hashcode)
                for code in match_hashcodes1:
                    links1.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}/match-details")
                for code in match_hashcodes2:
                    links2.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}/match-details")
    elif len(match_hashcodes1) < len(match_hashcodes2):
        links2 = []
        links1 = []
        for match_hashcode in match_hashcodes1:
            if match_hashcode in match_hashcodes2:
                match_hashcodes2.remove(match_hashcode)
                for code in match_hashcodes2:
                    links2.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}/match-details")
                for code in match_hashcodes1:
                    links1.append(f"https://crex.com/cricket-live-score/mil-vs-tr-25th-match-the-hundred-2026-men-match-updates-{code}/match-details")


    try :
        team1_wickets = []
        team1_runs = []
        for lk1 in links1:
            r1 = requests.get(lk1)
            soup1 = BeautifulSoup(r1.text, 'html.parser')
            new_script1 = str(soup1.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")

            # with open("data1.json", "w", encoding="utf-8") as f:
            #     f.write(str(new_script1))


            team1main = team_names[1]
            team1short = find_team_name(new_script1, 1)[1]
            if team1short == team1main:
                index_1 = new_script1.find("score1:") + 7
                modi_script1 = new_script1[index_1:]
                coma_index_1 = modi_script1.find(",")
                score1 = modi_script1[:coma_index_1]
                score1_index = score1.find("-") + 1
                run = float(score1[:score1_index - 1])
                wicket = float(score1[score1_index:])
                team1_runs.append(run)
                team1_wickets.append(wicket)
            else:
                index_1 = new_script1.find("score2:") + 7
                modi_script1 = new_script1[index_1:]
                coma_index_1 = modi_script1.find(",")
                score1 = modi_script1[:coma_index_1]
                score1_index = score1.find("-") + 1
                with open(".json", "w", encoding="utf-8") as f:
                    f.write(script)
                run = float(score1[:score1_index - 1])
                wicket = float(score1[score1_index:])
                team1_runs.append(run)
                team1_wickets.append(wicket)


        team2_wickets = []
        team2_runs = []
        for lk2 in links2:
            r2 = requests.get(lk2)
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            new_script2 = str(soup2.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")


            team2main = team_names[3]
            team2short = find_team_name(new_script2, 1)[1]
            if team2short == team2main:
                index_2 = new_script2.find("score1:") + 7
                modi_script2 = new_script2[index_2:]
                coma_index_2 = modi_script2.find(",")
                score2 = modi_script2[:coma_index_2]
                score2_index = score2.find("-") + 1
                run = float(score2[:score2_index - 1])
                wicket = float(score2[score2_index:])
                team2_runs.append(run)
                team2_wickets.append(wicket)
            else:
                index_2 = new_script2.find("score2:") + 7
                modi_script2 = new_script2[index_2:]
                coma_index_2 = modi_script2.find(",")
                score2 = modi_script2[:coma_index_2]
                score2_index = score2.find("-") + 1
                run = float(score2[:score2_index - 1])
                wicket = float(score2[score2_index:])
                team2_runs.append(run)
                team2_wickets.append(wicket)

    except ValueError:

        links1, match_hashcodes1 = link("t1f:", script, "front")
        links2, match_hashcodes2  = link("t2f:", script,"front")

        print(links1)
        print(links2)
        if len(match_hashcodes1) > len(match_hashcodes2):
            print("hello")
            links1 = []
            links2 = []
            for match_hashcode in match_hashcodes2:
                if match_hashcode in match_hashcodes1:
                    match_hashcodes1.remove(match_hashcode)
                    for code in match_hashcodes1:
                        links1.append(f"https://crex.com/cricket-live-score/lakr-vs-so-9th-match-major-league-cricket-2026-match-updates-{code}/match-details")
                    for code in match_hashcodes2:
                        links2.append(f"https://crex.com/cricket-live-score/lakr-vs-so-9th-match-major-league-cricket-2026-match-updates-{code}/match-details")

        elif len(match_hashcodes1) < len(match_hashcodes2):
            print("hello")
            links2 = []
            links1 = []
            for match_hashcode in match_hashcodes1:
                if match_hashcode in match_hashcodes2:
                    match_hashcodes2.remove(match_hashcode)
                    for code in match_hashcodes2:
                        links2.append(f"https://crex.com/cricket-live-score/lakr-vs-so-9th-match-major-league-cricket-2026-match-updates-{code}/match-details")
                    for code in match_hashcodes1:
                        links1.append(f"https://crex.com/cricket-live-score/lakr-vs-so-9th-match-major-league-cricket-2026-match-updates-{code}/match-details")

        team1_wickets = []
        team1_runs = []
        for lk1 in links1:
            r1 = requests.get(lk1)
            soup1 = BeautifulSoup(r1.text, 'html.parser')
            new_script1 = str(soup1.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")

            # with open("data1.json", "w", encoding="utf-8") as f:
            #     f.write(str(new_script1))


            team1main = team_names[1]
            team1short = find_team_name(new_script1, 1)[1]
            if team1short == team1main:
                index_1 = new_script1.find("score1:") + 7
                modi_script1 = new_script1[index_1:]
                coma_index_1 = modi_script1.find(",")
                score1 = modi_script1[:coma_index_1]
                score1_index = score1.find("-") + 1
                run = float(score1[:score1_index - 1])
                wicket = float(score1[score1_index:])
                team1_runs.append(run)
                team1_wickets.append(wicket)
            else:
                index_1 = new_script1.find("score2:") + 7
                modi_script1 = new_script1[index_1:]
                coma_index_1 = modi_script1.find(",")
                score1 = modi_script1[:coma_index_1]
                score1_index = score1.find("-") + 1
                # with open("hello.json", "w",encoding="utf-8") as f:
                #     f.write(new_script1)
                print(lk1)
                print(score1[:score1_index - 1])
                with open(".json", "w", encoding="utf-8") as f:
                    f.write(new_script1)
                run = float(score1[:score1_index - 1])
                wicket = float(score1[score1_index:])
                team1_runs.append(run)
                team1_wickets.append(wicket)


        team2_wickets = []
        team2_runs = []
        for lk2 in links2:
            r2 = requests.get(lk2)
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            new_script2 = str(soup2.find("script",{"id": "app-root-state"})).replace("&q;", "").replace("&a;", "").replace("/", "")


            team2main = team_names[3]
            team2short = find_team_name(new_script2, 1)[1]
            if team2short == team2main:
                index_2 = new_script2.find("score1:") + 7
                modi_script2 = new_script2[index_2:]
                coma_index_2 = modi_script2.find(",")
                score2 = modi_script2[:coma_index_2]
                score2_index = score2.find("-") + 1
                run = float(score2[:score2_index - 1])
                wicket = float(score2[score2_index:])
                team2_runs.append(run)
                team2_wickets.append(wicket)
            else:
                index_2 = new_script2.find("score2:") + 7
                modi_script2 = new_script2[index_2:]
                coma_index_2 = modi_script2.find(",")
                score2 = modi_script2[:coma_index_2]
                score2_index = score2.find("-") + 1
                run = float(score2[:score2_index - 1])
                wicket = float(score2[score2_index:])
                team2_runs.append(run)
                team2_wickets.append(wicket)


    try :
        t1_avg_wl = sum(team1_wickets)/len(match_hashcodes1)
    except ZeroDivisionError: 
        t1_avg_wl = df["team1_avg_wicket_last_5"].mean()

    try :
        t2_avg_wl = sum(team2_wickets)/len(match_hashcodes2)
    except ZeroDivisionError: 
        t2_avg_wl = df["team2_avg_wicket_last_5"].mean()

    try :
        t1_avg_runs = sum(team1_runs)/len(match_hashcodes1)
    except ZeroDivisionError: 
        t1_avg_runs = df["team1_avg_runs_last_5"].mean()

    try :
        t2_avg_runs = sum(team2_runs)/len(match_hashcodes2)
    except ZeroDivisionError: 
        t2_avg_runs = df["team2_avg_runs_last_5"].mean()

    return t1_avg_wl, t2_avg_wl, t1_avg_runs, t2_avg_runs

# team1_avg_wickets, team2_avg_wickets = wicket_lost()



def first_inn_scr(r):
    text = str(r.text)
    index = text.find('class="venue-avg-val"') + 22
    modi_text = text[index:]
    last_index = modi_text.find("<")
    return float(modi_text[:last_index])



def chase_win_rate(script, df):
    index = script.find("tm:")
    modi_script = script[index:]
    last_index = modi_script.find("}")


    modi_script = modi_script[:last_index]
    tm_index = modi_script.find(":")
    modi_script = modi_script[tm_index + 1:]
    tm_last_index = modi_script.find(",")
    tm = float(modi_script[:tm_last_index])


    y_index = modi_script.find("y:")
    y = float(modi_script[y_index + 2:])

    try:
        rate = y/tm * 100
    except ZeroDivisionError:
        rate = df["chasing_success_rate"].mean()
    
    return rate



def toss(script, soup):
    string_soup = str(soup)
    index = string_soup.find("won the toss and chose to")
    new_text = string_soup[index - 10:index - 10 + 80]


    toss_index = new_text.find(">")
    toss_last_index = new_text.find("<")
    toss_line = new_text[toss_index + 1: toss_last_index]


    space_index = toss_line.find(" ")
    toss_winner = toss_line[:space_index]
    to_index = toss_line.find(" chose")
    toss_decision = toss_line[to_index + 10:].capitalize()


    team1_points = 0
    team2_points = 0
    names = find_team_name(script)
    team1 = names[0].lower()
    team2 = names[2].lower()
    for ch in toss_winner.lower():
        team1_count = team1.count(ch)
        team1_points += team1_count
        team2_count = team2.count(ch)
        team2_points += team2_count


    if team1_points < team2_points:
        if "-" in team2:
            return team2.upper(), toss_decision
        else:
            return team2.title(), toss_decision
    else:
        if "-" in team1:
            return team1.upper(), toss_decision
        else:
            return team1.title(), toss_decision



# toss_win, toss_decision = toss()



def temperature(script, df):
    index = script.find("crT:")
    text = script[index + 4:]
    last_index = text.find("˚")
    try:
        temp = float(text[:last_index])
    except ValueError:
        temp = df["temperature"].mean()
    return temp



def humidity(script, df):
    index = script.find("hum:")
    try:
        hum = float(script[index + 4:index + 6])
    except ValueError:
        hum = df["humidity"].mean()
    return hum



def rain_prob(script, df):
    index = script.find("rP:")
    try:
        rain_p = float(script[index + 3:index + 5])
    except ValueError:
        rain_p = df["rain_probability"].mean()
    return rain_p



def venue(script):
    index = script.find("v:")
    modi_script = script[index + 2:]
    coma_index = modi_script.find(",")
    venue_name = modi_script[:coma_index]

    if "Cricket" in venue_name:
        venue_name = venue_name.replace("Cricket", "").replace("  ", " ")
    if "Hambantota" in venue_name:
        venue_name = venue_name.replace(" Hambantota","")
    if " Lords Ground" in venue_name:
        venue_name = venue_name.replace(" Lords Ground","Lords Ground")
    if "Lords" == venue_name:
        venue_name = "Lords Ground"
    if "Manchester" in venue_name:
        venue_name = venue_name.replace("Manchester","").replace("  ", "")[:-1]
    if "Ground" in venue_name:
        venue_name = venue_name.replace("Ground","").replace(" ", "")
    if "London" in venue_name:
        venue_name = venue_name.replace("London","")[:-1]
    if "Cardiff" in venue_name:
        venue_name = venue_name.replace("Cardiff","")[:-2]
    if "Southampton" in venue_name:
        venue_name = venue_name.replace("Southampton","")[:-1]
    if "Sophia Garden" == venue_name:
        venue_name = "Sophia Gardens"

    print(venue_name)

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
        swing_score_last_index = modi_swing_score.find(",")
        swing_score = float(modi_swing_score[:swing_score_last_index])
        

        pitch_score_index = pitch_full_line.find("pace_pitch_score:")
        modi_pitch_score = pitch_full_line[pitch_score_index + 17:]
        pitch_score_last_index = modi_pitch_score.find(",")
        pitch_score = float(modi_pitch_score[:pitch_score_last_index])


        seam_score_index = pitch_full_line.find("seam_pitch_score:")
        modi_seam_score = pitch_full_line[seam_score_index + 17:]
        seam_score_last_index = modi_seam_score.find(",")
        seam_score = float(modi_seam_score[:seam_score_last_index])


        bounce_score_index = pitch_full_line.find("bounce_pitch_score:")
        modi_bounce_score = pitch_full_line[bounce_score_index + 19:]
        bounce_score_last_index = modi_bounce_score.find(",")
        bounce_score = float(modi_bounce_score[:bounce_score_last_index])


        spin_score = float(pitch_full_line[-1])
        

        bowling_avg = (swing_score + pitch_score + seam_score + bounce_score + spin_score)/5


        if batting_score == bowling_avg:
            return "Balanced"
        elif batting_score < bowling_avg:
            return "Bowling"
        else:
            return "Batting"


    except ValueError:
        return "Balanced"



def win(script, team_names):
    index = script.find("B:")
    modi_script = script[index + 2:]
    last_index = modi_script.find(" won ")
    winner = modi_script[:last_index]

    if winner == "Oval Invincibles":
        winner = "MI London"
    elif winner == "Oval Invincibles Women":
        winner = "MI London Women"
    elif winner == "Northern Superchargers":
        winner = "Sunrisers Leeds"
    elif winner == "Northern Superchargers Women":
        winner = "Sunrisers Leeds Women"


    team1 = team_names[0].upper()
    team2 = team_names[2].upper()


    team1points = 0
    team2points = 0
    for ch in winner.upper():
        team1points += team1.count(ch)
        team2points += team2.count(ch)


    if team1points > team2points:
        winner = team1
    else:
        winner = team2

    if winner == team1:
        return 0
    else:
        return 1


# ---------------------------------------------------------------------------
# Orchestrator glue - NOT part of the pasted functions above, just wires them
# together for the Streamlit app. Calls each function with its exact
# original signature (e.g. toss(script, soup) takes 2 args, not 3).
# ---------------------------------------------------------------------------
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


def scrape_match(match_url, league_df):
    """Calls the functions above with their exact original signatures and
    packages the result for predict.predict_match(**kwargs) / the Streamlit
    UI. wicket_lost()'s hardcoded tournament slugs mean avg_runs_last_5 /
    avg_wicket_last_5 will likely be wrong or fail for a non-matching
    tournament - see the module docstring."""
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

    toss_winner, toss_decision = toss(script, soup)

    temp = temperature(script, league_df)
    hum = humidity(script, league_df)
    rain = rain_prob(script, league_df)
    venue_name = venue(script)
    p_type = pitch_type(script)
    chase_wr = chase_win_rate(script, league_df)

    try:
        t1_avg_wkts, t2_avg_wkts, t1_avg_runs, t2_avg_runs = wicket_lost(team_names, script, league_df)
    except Exception as e:
        print(f"[scraper] wicket_lost() raised {type(e).__name__}: {e} - using historical means")
        t1_avg_runs = league_df["team1_avg_runs_last_5"].mean()
        t2_avg_runs = league_df["team2_avg_runs_last_5"].mean()
        t1_avg_wkts = league_df["team1_avg_wicket_last_5"].mean()
        t2_avg_wkts = league_df["team2_avg_wicket_last_5"].mean()

    return {
        "team1": team1, "team2": team2, "venue": venue_name, "pitch_type": p_type,
        "team1_win_rate": team1_win_rate, "team2_win_rate": team2_win_rate,
        "head_to_head_win_rate": h2h,
        "team1_recent_form": team1_recent_form, "team2_recent_form": team2_recent_form,
        "team1_avg_runs_last_5": t1_avg_runs, "team2_avg_runs_last_5": t2_avg_runs,
        "team1_avg_wicket_last_5": t1_avg_wkts, "team2_avg_wicket_last_5": t2_avg_wkts,
        "avg_first_innings_score": league_df["avg_first_innings_score"].mean(),
        "chasing_success_rate": chase_wr,
        "toss_winner": toss_winner, "toss_decision": toss_decision,
        "temperature": temp, "humidity": hum, "rain_probability": rain,
    }


def scrape_completed_match(match_url, league_df):
    script, soup, _ = _get_script_and_soup(match_url)
    stats = scrape_match(match_url, league_df)

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
