#!/usr/bin/env python3
"""
Daily Digest v3 — Morning briefing for Fort Bliss / El Paso.
Author: John W. Clements / JANUS Research Group

SECTIONS:
  1.  Market Snapshot       — DJI · S&P 500 · WTI Crude
  2.  El Paso / Fort Bliss  — Local news (4 stories)
  3.  Movies in El Paso     — By theater, by showtime
  4.  Weather               — El Paso/Fort Bliss · Ellensburg WA · Pearl River LA
  5.  LSU Sports            — All active sports, scores + stories
  6.  Louisiana             — Dedicated block: NOLA · Baton Rouge · Northshore / St. Tammany
  7.  Great Books Quotes    — 2-3 rotating philosophers from the Western canon
  8.  Word of the Day       — Latin / Cajun French / Military term of art
  9.  On This Day           — Historical note for today's date
  10. DoD / Army News       — Defense News, Breaking Defense, Army Times
  11. Defense Budget        — Congressional / NDAA / M&S funding tracker
  12. World / EU News       — Major international stories with region badges
  13. Military Tech Links   — Clickable URLs, emphasis on M&S capabilities
  14. Ingredient of the Day — Louisiana focused, Clebeaux-voiced
  15. Regional News         — Ellensburg WA · Pearl River LA

Runs free on GitHub Actions. See README.md for setup.
"""

import os, json, smtplib, requests, time, random
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Env vars (GitHub Secrets) ──────────────────────────────────────────────────
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER    = os.environ["GMAIL_USER"]
GMAIL_PASS    = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL      = os.environ["TO_EMAIL"]

# ── Weather locations ──────────────────────────────────────────────────────────
LOCATIONS = {
    "El Paso / Fort Bliss, TX": (31.7619, -106.4850),
    "Ellensburg, WA":           (46.9965, -120.5478),
    "Pearl River, LA":          (30.3690, -89.7523),
}

# ── WMO weather codes ──────────────────────────────────────────────────────────
WMO = {
    0: "☀️ Clear", 1: "🌤 Mainly clear", 2: "⛅ Partly cloudy", 3: "☁️ Overcast",
    45: "🌫 Foggy", 48: "🌫 Icy fog",
    51: "🌦 Light drizzle", 53: "🌧 Drizzle", 55: "🌧 Heavy drizzle",
    61: "🌧 Light rain", 63: "🌧 Rain", 65: "🌧 Heavy rain",
    71: "🌨 Light snow", 73: "❄️ Snow", 75: "❄️ Heavy snow",
    80: "🌦 Showers", 81: "🌧 Heavy showers", 82: "⛈ Violent showers",
    95: "⛈ Thunderstorm", 99: "⛈ Hail storm",
}

# ── Great Books philosopher pool ───────────────────────────────────────────────
GREAT_BOOKS_AUTHORS = [
    "Plato (Republic or Symposium)",
    "Aristotle (Nicomachean Ethics or Politics)",
    "Marcus Aurelius (Meditations)",
    "Epicurus (Letter to Menoeceus)",
    "Lucretius (On the Nature of Things)",
    "Francis Bacon (Novum Organum)",
    "René Descartes (Meditations on First Philosophy)",
    "Baruch Spinoza (Ethics)",
    "John Locke (An Essay Concerning Human Understanding)",
    "David Hume (An Enquiry Concerning Human Understanding)",
    "Immanuel Kant (Critique of Pure Reason or Groundwork of the Metaphysics of Morals)",
    "Jean-Jacques Rousseau (The Social Contract)",
    "Georg Wilhelm Friedrich Hegel (Phenomenology of Spirit)",
    "Friedrich Nietzsche (Beyond Good and Evil or Thus Spoke Zarathustra)",
    "William James (Principles of Psychology)",
    "Karl Marx (Capital)",
    "Sigmund Freud (The Interpretation of Dreams)",
    "Thucydides (History of the Peloponnesian War)",
    "Plutarch (Parallel Lives)",
    "Adam Smith (The Wealth of Nations)",
    "Thomas Hobbes (Leviathan)",
    "Montaigne (Essays)",
    "Pascal (Pensées)",
    "Tocqueville (Democracy in America)",
]


# ══════════════════════════════════════════════════════════════════════════════
#  CLAUDE API CORE
# ══════════════════════════════════════════════════════════════════════════════

def _claude(prompt: str, use_search: bool = True, max_tokens: int = 1400) -> str:
    """Call Claude, optionally with web search. Returns all text block content."""
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if use_search else []
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if tools:
        payload["tools"] = tools

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            data = resp.json()
            # Print API errors so they show up in GitHub Actions logs
            if "error" in data:
                print(f"    ⚠️  API error: {data['error']}")
                time.sleep(6)
                continue
            return "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ).strip()
        except Exception as e:
            print(f"    ⚠️  Claude attempt {attempt + 1} failed: {e}")
            time.sleep(6)
    return "[]"


def _parse_json(raw: str) -> object:
    """Strip markdown fences and parse JSON safely."""
    text = raw.strip()
    if "```" in text:
        for p in text.split("```"):
            p = p.strip().lstrip("json").strip()
            if p.startswith(("[", "{")):
                text = p
                break
    start = min((text.find(c) for c in ("[", "{") if text.find(c) != -1), default=-1)
    end   = max(text.rfind("]"), text.rfind("}"))
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        print(f"    ⚠️  JSON parse error: {e} | Raw: {raw[:200]}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
#  DATA FETCHERS
# ══════════════════════════════════════════════════════════════════════════════

def get_news(topic: str, count: int) -> list:
    text = _claude(
        f"Search for the {count} most recent local news stories about {topic} "
        f"from today or the last 48 hours. "
        f"Return ONLY a valid JSON array. Each element: 'headline' and 'summary' (1-2 sentences). "
        f"No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": f"News unavailable — {topic}", "summary": "Could not retrieve at this time."}
    ]


def get_movies_el_paso() -> list:
    today = date.today().strftime("%A, %B %d, %Y")
    text = _claude(
        f"Search Fandango, AMC, Cinemark, and Regal for current movie showtimes in El Paso Texas "
        f"for today {today}. Include AMC Cielo Vista, Cinemark El Paso 16, Cinemark Movies 8, "
        f"Regal Bassett Place, and any others found. "
        f"Return ONLY a valid JSON array. Each element: 'theater' (name), 'address', "
        f"'movies' (array of objects: 'title', 'rating', 'times' array of strings like '7:30 PM'). "
        f"Only movies with at least one showtime. No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) else []


def get_weather(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
        f"&temperature_unit=fahrenheit&timezone=auto&forecast_days=3"
    )
    try:
        return requests.get(url, timeout=15).json()
    except Exception:
        return {}


def get_markets() -> dict:
    """Fetch DJI, S&P 500, and WTI Crude from Yahoo Finance."""
    tickers = {"dji": "%5EDJI", "sp500": "%5EGSPC", "wti": "CL%3DF"}
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DailyDigest/3.0)"}
    for key, symbol in tickers.items():
        try:
            url  = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            meta = requests.get(url, headers=headers, timeout=15).json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev  = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            chg   = price - prev
            pct   = (chg / prev * 100) if prev else 0
            results[key] = (price, chg, pct)
        except Exception as e:
            print(f"    ⚠️  Market fetch failed for {key}: {e}")
            results[key] = (0, 0, 0)
    return results


def get_lsu_sports() -> dict:
    text = _claude(
        f"Search for the latest LSU Tigers sports scores and news from the last 7 days. "
        f"Cover all active sports: football, basketball men's and women's, baseball, softball, "
        f"track, gymnastics, swimming, or any currently in season. "
        f"Return ONLY a valid JSON object with two keys: "
        f"'scores' (array: sport, opponent, result like 'W 8-3' or 'L 72-75', date) "
        f"and 'stories' (array of 2-3 objects: headline, summary — 1-2 sentences each). "
        f"No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) else {
        "scores": [], "stories": [{"headline": "LSU sports data unavailable", "summary": ""}]
    }


def get_louisiana_news() -> list:
    text = _claude(
        f"Search for the 4 most important and recent news stories from Louisiana — "
        f"focus on New Orleans, Baton Rouge, and the Northshore / St. Tammany Parish area. "
        f"Cover local politics, crime, weather events, coastal issues, business, culture, or sports. "
        f"Return ONLY a valid JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        f"'area' (e.g. 'New Orleans', 'Baton Rouge', 'Northshore', 'Statewide'). "
        f"No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "Louisiana news unavailable", "summary": "", "area": ""}
    ]


def get_philosopher_quotes() -> list:
    random.seed(date.today().toordinal())
    chosen = random.sample(GREAT_BOOKS_AUTHORS, 3)
    text = _claude(
        f"Today is {date.today().strftime('%B %d')}. Select 2 or 3 genuine, accurate philosophical "
        f"quotes — one from each of these authors/works from the Great Books of the Western World: "
        f"{', '.join(chosen)}. Prefer timeless, thought-provoking lines. "
        f"Return ONLY a valid JSON array. Each element: 'author', 'work', 'quote' (exact quotation), "
        f"'context' (one sentence on why it matters). No markdown, no preamble. Pure JSON.",
        use_search=False,
        max_tokens=900,
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"author": "Marcus Aurelius", "work": "Meditations",
         "quote": "You have power over your mind, not outside events. Realize this, and you will find strength.",
         "context": "A Stoic reminder that inner discipline is the only true freedom."}
    ]


def get_word_of_the_day() -> dict:
    today_str = date.today().strftime("%B %d")
    text = _claude(
        f"Today is {today_str}. Choose one interesting word or phrase of the day, rotating among "
        f"these three categories (vary by date): (1) Latin philosophical or legal term, "
        f"(2) Cajun French or Louisiana Creole word or expression, "
        f"(3) Military or defense term of art (especially simulation, joint ops, or doctrine). "
        f"Return ONLY a valid JSON object with exactly four string fields: "
        f"'word' (the term itself), 'category' (which of the three types it is), "
        f"'pronunciation' (phonetic guide, if helpful), "
        f"'definition' (2-3 sentences: meaning, origin, and how it's used). "
        f"No markdown, no preamble. Pure JSON.",
        use_search=False,
        max_tokens=400,
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) and r.get("word") else {
        "word": "Simulacrum", "category": "Latin philosophical term",
        "pronunciation": "sim-yoo-LAY-krum",
        "definition": "From Latin, meaning a likeness or image. In philosophy (Plato, Baudrillard), "
                      "a copy that has lost its connection to the original. In DoD modeling and simulation, "
                      "the concept underpins synthetic training environments."
    }


def get_on_this_day() -> dict:
    today_str = date.today().strftime("%B %d")
    text = _claude(
        f"What is one notable historical event that occurred on {today_str}? "
        f"Prefer events related to military history, science, philosophy, exploration, or American history. "
        f"Return ONLY a valid JSON object with three string fields: "
        f"'year', 'headline' (one line), 'story' (2-3 sentences of context and significance). "
        f"No markdown, no preamble. Pure JSON.",
        use_search=False,
        max_tokens=400,
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) and r.get("year") else {
        "year": "—", "headline": "Historical note unavailable",
        "story": "Could not retrieve today's historical entry."
    }


def get_louisiana_festivals() -> list:
    """Fetch Louisiana festivals and events in the next 30 days."""
    today_str = date.today().strftime("%B %d, %Y")
    text = _claude(
        f"Today is {today_str}. Search for Louisiana festivals, fairs, cultural events, food events, "
        f"music festivals, and community celebrations happening in the next 30 days anywhere in Louisiana — "
        f"especially New Orleans, Baton Rouge, the Northshore / St. Tammany Parish area, "
        f"Acadiana, the River Parishes, and the Gulf Coast. "
        f"Return ONLY a valid JSON array of 6-8 events. Each element must have exactly five string fields: "
        f"'name' (event name), 'location' (city or venue), 'dates' (e.g. 'April 25-27' or 'May 3'), "
        f"'description' (1-2 sentences on what it is and why it's worth attending), "
        f"'url' (event website or ticketing URL if available, otherwise empty string). "
        f"Sort by date ascending. No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"name": "Festival data unavailable", "location": "", "dates": "",
         "description": "Could not retrieve Louisiana festival listings.", "url": ""}
    ]


def get_el_paso_weekend() -> list:
    """Fetch El Paso / Fort Bliss area things to do this coming weekend."""
    from datetime import timedelta
    today     = date.today()
    today_str = today.strftime("%B %d, %Y")
    days_to_fri = (4 - today.weekday()) % 7
    if days_to_fri == 0:
        days_to_fri = 7
    fri = (today + timedelta(days=days_to_fri)).strftime("%B %d")
    sun = (today + timedelta(days=days_to_fri + 2)).strftime("%B %d")
    weekend_str = f"{fri}–{sun}"

    text = _claude(
        f"Today is {today_str}. Search for things to do in El Paso Texas and the surrounding area "
        f"this weekend ({weekend_str}). Include: concerts, festivals, markets, sporting events, "
        f"outdoor activities, art shows, food events, family activities, Fort Bliss community events, "
        f"and anything happening in Juárez that draws El Paso visitors. "
        f"Return ONLY a valid JSON array of 6-8 events or activities. "
        f"Each element must have exactly five string fields: "
        f"'name' (event or activity name), 'venue' (location or neighborhood), "
        f"'when' (day and time, e.g. 'Saturday 7:00 PM' or 'Saturday–Sunday'), "
        f"'description' (1-2 sentences), "
        f"'url' (event or venue website if available, otherwise empty string). "
        f"Sort by date/time. No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"name": "Weekend listings unavailable", "venue": "", "when": "",
         "description": "Could not retrieve El Paso weekend events.", "url": ""}
    ]


def get_dod_army_news() -> list:
    text = _claude(
        f"Search Defense News, Breaking Defense, Army Times, and Military.com for the 3-4 most "
        f"important DoD and U.S. Army news stories from the last 48 hours. "
        f"Cover: acquisition, readiness, personnel policy, operations, budget, new programs. "
        f"Return ONLY a valid JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        f"'source' (publication name). No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "DoD news unavailable", "summary": "", "source": ""}
    ]


def get_defense_budget_news() -> list:
    text = _claude(
        f"Search for 2-3 recent news stories (last 7 days) specifically about U.S. defense budget, "
        f"Congressional defense appropriations, NDAA developments, or funding decisions affecting "
        f"Army simulation and training programs, modeling and simulation (M&S) contracts, "
        f"synthetic training environments, or Live Virtual Constructive (LVC) programs. "
        f"Return ONLY a valid JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        f"'relevance' (one phrase — why it matters to M&S/training). "
        f"No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "Defense budget news unavailable", "summary": "", "relevance": ""}
    ]


def get_crs_links() -> list:
    """
    Fetch recent Congressional Research Service (CRS) reports relevant to DoD.
    Returns [{title, short_title, url, date, summary}]
    CRS reports are publicly available at crsreports.congress.gov
    """
    text = _claude(
        f"Search crsreports.congress.gov for the most recent Congressional Research Service (CRS) "
        f"reports published in the last 30 days that are relevant to the Department of Defense. "
        f"Prioritize reports covering: defense appropriations, Army programs, modeling and simulation, "
        f"synthetic training environments, autonomous systems, hypersonics, readiness, "
        f"military personnel policy, acquisition reform, NDAA implementation, or NATO/alliances. "
        f"Return ONLY a valid JSON array of 4-6 items. Each element must have exactly five string fields: "
        f"'title' (full CRS report title), "
        f"'short_title' (5-8 word plain-English summary of what it covers), "
        f"'report_number' (e.g. R47123 or IF12345 — the CRS report ID), "
        f"'date' (publication date), "
        f"'url' (direct URL to the report on crsreports.congress.gov — must be a real URL). "
        f"Only include reports with real, verifiable URLs on crsreports.congress.gov. "
        f"No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    if not isinstance(r, list):
        return []
    # Keep only entries with plausible CRS URLs
    valid = [
        s for s in r
        if isinstance(s.get("url", ""), str)
        and "congress.gov" in s.get("url", "")
        and s.get("title")
    ]
    return valid or r


def get_world_news() -> list:
    text = _claude(
        f"Search for the 4 most important international news stories (excluding the U.S.) "
        f"from today or the last 24 hours. Cover Europe, Middle East, Asia, or global events. "
        f"Return ONLY a valid JSON array. Each element: 'headline', 'summary' (2 sentences), "
        f"'region' (e.g. 'Europe', 'Middle East', 'Asia'). No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "World news unavailable", "summary": "", "region": ""}
    ]


def get_military_tech_links() -> list:
    text = _claude(
        f"Search for 4-5 recent news articles (last 7 days) on new military technology. "
        f"Prioritize: modeling and simulation (M&S), synthetic training environments, digital twins, "
        f"Live Virtual Constructive (LVC), HLA/DIS/TENA interoperability, AI in defense, "
        f"autonomous systems, hypersonics, directed energy, DoD simulation acquisition. "
        f"Return ONLY a valid JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        f"'url' (real full https URL — required, no made-up URLs), "
        f"'category' (e.g. 'Modeling & Simulation', 'Autonomous Systems', 'Hypersonics', "
        f"'AI/ML', 'Directed Energy', 'LVC/Training'). "
        f"Only include entries with a real, verifiable URL. No markdown, no preamble. Pure JSON."
    )
    r = _parse_json(text)
    if not isinstance(r, list):
        return []
    return [s for s in r if isinstance(s.get("url", ""), str)
            and s["url"].startswith("http") and len(s["url"]) > 20] or r


def get_ingredient_of_the_day() -> dict:
    today_str = date.today().strftime("%B %d")
    text = _claude(
        f"Today is {today_str}. You are Clebeaux, a Louisiana cook from St. Tammany Parish "
        f"who grew up on a working farm four miles south of Talisheek. "
        f"Choose one Louisiana ingredient, spice, or technique that is either in season right now "
        f"or worth knowing about — something from the Cajun or Creole pantry: a smoked meat, "
        f"a wild green, a particular pepper, a bayou catch, a canning tradition, a roux technique. "
        f"Write in Clebeaux's voice: personal, direct, a little salty, deeply knowledgeable. "
        f"Return ONLY a valid JSON object with three string fields: "
        f"'ingredient' (name of the ingredient or technique), "
        f"'season' (when it peaks or when to use it), "
        f"'note' (3-4 sentences in Clebeaux's voice — sourcing, flavor, how to use it, "
        f"a memory or opinion). No markdown, no preamble. Pure JSON.",
        use_search=False,
        max_tokens=500,
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) and r.get("ingredient") else {
        "ingredient": "Tasso",
        "season": "Year-round, cure your own in fall",
        "note": "Tasso is not ham and don't let anybody tell you otherwise. It's a heavily spiced, "
                "smoked pork shoulder — lean, intensely seasoned, meant to flavor a pot, not fill a plate. "
                "Richards makes a decent one if you can find it. Jacobs is the real article. "
                "Whatever you do, don't buy the Albertsons version — that's an insult to the pig."
    }


def get_snarky_comments(d: dict) -> dict:
    """
    Read the day's actual content and generate section-specific snarky commentary.
    Voice: Southern wit, Louisiana-flavored, dry, sharp but not cruel.
    Returns a dict keyed by section name with one short comment each.
    """
    # Build a plain-text summary of today's content to pass to Claude
    price_dji, chg_dji, pct_dji = d["markets"].get("dji", (0, 0, 0))
    price_sp,  chg_sp,  pct_sp  = d["markets"].get("sp500", (0, 0, 0))
    price_wti, chg_wti, pct_wti = d["markets"].get("wti", (0, 0, 0))

    def headlines(stories, n=3):
        return " | ".join(s.get("headline", "") for s in (stories or [])[:n]) or "none"

    def lsu_scores(data):
        scores = data.get("scores", [])
        return ", ".join(
            f"{s.get('sport','')} vs {s.get('opponent','')} {s.get('result','')}"
            for s in scores[:4]
        ) or "no recent scores"

    def festival_names(events):
        return ", ".join(e.get("name", "") for e in (events or [])[:4]) or "none found"

    def weekend_events(events):
        return ", ".join(e.get("name", "") for e in (events or [])[:4]) or "none found"

    ep_weather = d.get("weather", {}).get("El Paso / Fort Bliss, TX", {})
    try:
        w_daily = ep_weather.get("daily", {})
        hi0 = round(w_daily["temperature_2m_max"][0])
        lo0 = round(w_daily["temperature_2m_min"][0])
        cond0 = WMO.get(w_daily["weathercode"][0], "unknown")
        weather_summary = f"{cond0}, high {hi0}°F low {lo0}°F"
    except Exception:
        weather_summary = "weather data unavailable"

    word = d.get("word", {})
    ingredient = d.get("ingredient", {})
    on_this_day = d.get("on_this_day", {})

    content_summary = f"""
MARKETS: DJI {price_dji:,.0f} ({pct_dji:+.1f}%), S&P {price_sp:,.0f} ({pct_sp:+.1f}%), WTI crude ${price_wti:.2f} ({pct_wti:+.1f}%)
EL PASO NEWS: {headlines(d.get('ep_news', []))}
EL PASO WEATHER (today): {weather_summary}
LSU SPORTS: {lsu_scores(d.get('lsu', {}))}
LOUISIANA NEWS: {headlines(d.get('louisiana', []))}
LOUISIANA FESTIVALS (next 30 days): {festival_names(d.get('la_festivals', []))}
EL PASO WEEKEND EVENTS: {weekend_events(d.get('ep_weekend', []))}
DOD/ARMY NEWS: {headlines(d.get('dod_news', []))}
DEFENSE BUDGET NEWS: {headlines(d.get('budget_news', []))}
WORLD NEWS: {headlines(d.get('world_news', []))}
MILITARY TECH: {headlines(d.get('miltech', []))}
WORD OF THE DAY: {word.get('word', '')} ({word.get('category', '')}) — {word.get('definition', '')[:80]}
ON THIS DAY: {on_this_day.get('year', '')} — {on_this_day.get('headline', '')}
INGREDIENT OF THE DAY: {ingredient.get('ingredient', '')} — {ingredient.get('note', '')[:80]}
"""

    prompt = f"""You are writing short, snarky, funny commentary for a daily email digest 
read by a man named John (goes by Clebeaux in the kitchen) who grew up on a farm outside 
Talisheek, Louisiana (St. Tammany Parish), now works in Army modeling & simulation 
at Fort Bliss in El Paso, Texas, and is writing a cookbook called 'Divorce Era: A Louisiana 
Survival Cookbook'. He is a well-read, sharp-witted Southerner with two graduate degrees 
and a deep love of LSU, good food, and Louisiana culture. He does not suffer fools.

Here is today's actual content. Write ONE short snarky comment for each section.
Rules:
- Each comment is 1-2 sentences MAX. Short. Punchy.
- Voice: dry Southern wit. Specific to the actual content. Occasionally self-aware 
  about the absurdity of daily news, defense bureaucracy, or living in the West Texas desert 
  while your heart is in South Louisiana.
- Reference the actual headlines/scores/data where possible — not generic.
- Don't be cruel about real people. Punch at institutions, situations, and irony.
- LSU commentary should reflect the actual W/L record shown.
- Weather comments should react to the actual El Paso forecast.
- Markets comments can react to actual direction (up/down/flat).
- Occasionally make a Divorce Era cookbook joke if something fits.
- Return ONLY a valid JSON object with exactly these keys:
  markets, ep_news, weather, lsu, louisiana, la_festivals, ep_weekend, 
  dod_news, budget_news, world_news, miltech, word_of_day, on_this_day, ingredient
Each value is a single string (the comment). No markdown, no preamble. Pure JSON.

TODAY'S CONTENT:
{content_summary}"""

    text = _claude(prompt, use_search=False, max_tokens=1200)
    r = _parse_json(text)
    if not isinstance(r, dict):
        return {}
    return r


# ══════════════════════════════════════════════════════════════════════════════
#  LOUISIANA THEME — COLOR PALETTE
# ══════════════════════════════════════════════════════════════════════════════
#
#  PURPLE  #3D1A6E  — deep Mardi Gras purple
#  GOLD    #C8A400  — antique Mardi Gras gold
#  GREEN   #0B5E2E  — bayou / Mardi Gras green
#  CREAM   #FAF3E0  — magnolia blossom cream
#  IVORY   #FFFDF6  — warm card white
#  CYPRESS #7A5230  — cypress wood brown
#  MOSS    #5C6B3E  — Spanish moss green
#  IRON    #1E1E1E  — wrought iron black

PURPLE  = "#3D1A6E"
GOLD    = "#C8A400"
GOLD_LT = "#D4AF37"
GREEN   = "#0B5E2E"
CREAM   = "#FAF3E0"
IVORY   = "#FFFDF6"
CYPRESS = "#7A5230"
MOSS    = "#5C6B3E"
IRON    = "#1E1E1E"

# ══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def h2(icon: str, title: str) -> str:
    """Louisiana-themed section header with fleur-de-lis accent and gold rule."""
    return f"""
    <table style="width:100%;border-collapse:collapse;margin:30px 0 16px;">
      <tr>
        <td style="padding:0;">
          <div style="border-top:1px solid {GOLD};margin-bottom:10px;"></div>
          <div style="font-family:Georgia,serif;font-size:16px;font-weight:bold;
                      color:{PURPLE};letter-spacing:.5px;">
            <span style="color:{GOLD};margin-right:6px;">⚜</span>{icon}&nbsp; {title}
          </div>
          <div style="border-bottom:2px solid {GOLD};margin-top:8px;"></div>
        </td>
      </tr>
    </table>"""


def html_snark(comment: str) -> str:
    """Renders a snarky comment as a styled callout beneath a section header."""
    if not comment:
        return ""
    return f"""
    <div style="background:linear-gradient(90deg,rgba(61,26,110,.08) 0%,rgba(200,164,0,.06) 100%);
                border-left:3px solid {GOLD};border-radius:0 6px 6px 0;
                padding:9px 14px;margin:-8px 0 16px;font-style:italic;
                font-size:13px;color:{CYPRESS};line-height:1.5;">
      <span style="color:{GOLD};margin-right:6px;">⚜</span>{comment}
    </div>"""


def html_stories(stories: list, badge_key: str = None, badge_colors: dict = None) -> str:
    out = ""
    for s in stories:
        badge = ""
        if badge_key and s.get(badge_key):
            val = s[badge_key]
            bg, fg = (badge_colors or {}).get(val, (CREAM, PURPLE))
            badge = (f'<span style="background:{bg};color:{fg};border-radius:3px;'
                     f'padding:2px 8px;font-size:11px;font-weight:bold;letter-spacing:.3px;'
                     f'margin-right:8px;border:1px solid {GOLD_LT};">{val}</span>')
        source = ""
        if s.get("source"):
            source = (f'<span style="font-size:11px;color:{GOLD};font-style:italic;'
                      f'margin-left:8px;">— {s["source"]}</span>')
        relevance = ""
        if s.get("relevance"):
            relevance = (f'<div style="font-size:12px;color:{GREEN};margin-top:5px;'
                         f'font-style:italic;padding-left:10px;border-left:2px solid {GOLD};">'
                         f'↳ {s["relevance"]}</div>')
        out += f"""
        <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #E8DFC8;">
          <div style="font-size:15px;font-weight:bold;color:{IRON};line-height:1.5;">
            {badge}{s.get('headline','')}{source}
          </div>
          <div style="font-size:13px;color:#5a5040;margin-top:6px;line-height:1.6;">
            {s.get('summary','')}
          </div>
          {relevance}
        </div>"""
    return out
    out = ""
    for s in stories:
        badge = ""
        if badge_key and s.get(badge_key):
            val = s[badge_key]
            bg, fg = (badge_colors or {}).get(val, (CREAM, PURPLE))
            badge = (f'<span style="background:{bg};color:{fg};border-radius:3px;'
                     f'padding:2px 8px;font-size:11px;font-weight:bold;letter-spacing:.3px;'
                     f'margin-right:8px;border:1px solid {GOLD_LT};">{val}</span>')
        source = ""
        if s.get("source"):
            source = (f'<span style="font-size:11px;color:{GOLD};font-style:italic;'
                      f'margin-left:8px;">— {s["source"]}</span>')
        relevance = ""
        if s.get("relevance"):
            relevance = (f'<div style="font-size:12px;color:{GREEN};margin-top:5px;'
                         f'font-style:italic;padding-left:10px;border-left:2px solid {GOLD};">'
                         f'↳ {s["relevance"]}</div>')
        out += f"""
        <div style="margin-bottom:16px;padding-bottom:16px;
                    border-bottom:1px solid #E8DFC8;">
          <div style="font-size:15px;font-weight:bold;color:{IRON};line-height:1.5;">
            {badge}{s.get('headline','')}{source}
          </div>
          <div style="font-size:13px;color:#5a5040;margin-top:6px;line-height:1.6;">
            {s.get('summary','')}
          </div>
          {relevance}
        </div>"""
    return out


REGION_COLORS = {
    "Europe":      ("#EDE0FF", PURPLE),
    "Middle East": ("#FFF6D6", CYPRESS),
    "Asia":        ("#E0F2E9", GREEN),
    "Africa":      ("#FDE8D8", "#8B3A10"),
    "Americas":    (CREAM, MOSS),
}

AREA_COLORS = {
    "New Orleans":  ("#FFF6D6", CYPRESS),
    "Baton Rouge":  ("#F5E6FF", PURPLE),
    "Northshore":   ("#E0F2E9", GREEN),
    "Statewide":    (CREAM, MOSS),
}

CAT_COLORS = {
    "Modeling & Simulation": ("#E0F2E9", GREEN),
    "LVC/Training":          ("#E0F2E9", MOSS),
    "AI/ML":                 ("#EDE0FF", PURPLE),
    "Autonomous Systems":    ("#FDE8D8", "#8B3A10"),
    "Hypersonics":           ("#FFF6D6", CYPRESS),
    "Directed Energy":       ("#F5E6FF", "#5A007A"),
    "Cybersecurity":         ("#FFE8E0", "#8B1A00"),
}


def html_markets(m: dict) -> str:
    def cell(label, key, fmt="index", border=True):
        price, chg, pct = m.get(key, (0, 0, 0))
        arrow = "▲" if chg >= 0 else "▼"
        up_color   = "#1A6B35"
        down_color = "#8B1A00"
        chg_color  = up_color if chg >= 0 else down_color
        val = f"${price:,.2f}" if fmt == "price" else f"{price:,.2f}"
        if not price:
            val, chg_str = "—", ""
        else:
            chg_str = (f'<div style="font-size:13px;color:{chg_color};font-weight:bold;">'
                       f'{arrow} {abs(chg):,.2f} ({pct:+.2f}%)</div>')
        br = f"border-right:1px solid {GOLD};" if border else ""
        return f"""
        <td style="width:33%;text-align:center;padding:16px 8px;vertical-align:top;{br}">
          <div style="font-size:10px;color:{GOLD_LT};text-transform:uppercase;
                      letter-spacing:1.2px;margin-bottom:4px;">{label}</div>
          <div style="font-size:22px;font-weight:bold;color:#FAF3E0;">{val}</div>
          {chg_str}
        </td>"""

    return f"""
    <div style="background:linear-gradient(135deg,{PURPLE} 0%,#1E0A3C 100%);
                border-radius:8px;overflow:hidden;margin-bottom:8px;
                border:1px solid {GOLD};">
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          {cell("Dow Jones", "dji")}
          {cell("S&amp;P 500", "sp500")}
          {cell("WTI Crude", "wti", "price", border=False)}
        </tr>
      </table>
      <div style="text-align:center;font-size:11px;color:{GOLD};padding:6px;
                  border-top:1px solid rgba(200,164,0,.3);letter-spacing:.5px;">
        Most recent close &nbsp;·&nbsp; Yahoo Finance
      </div>
    </div>"""


def html_movies(theaters: list) -> str:
    if not theaters:
        return (f'<p style="color:{MOSS};font-size:13px;font-style:italic;">Showtime data not available. '
                f'Check <a href="https://www.fandango.com/el-paso_tx_movies" style="color:{GOLD};">Fandango</a>.</p>')
    out = ""
    for t in theaters:
        movies_html = ""
        for m in t.get("movies", []):
            times = " &nbsp;".join(
                f'<span style="background:{GREEN};color:{GOLD_LT};padding:2px 9px;'
                f'border-radius:12px;font-size:11px;font-weight:bold;">{tm}</span>'
                for tm in m.get("times", [])
            )
            rating = m.get("rating", "")
            badge = (f'<span style="background:{PURPLE};color:{GOLD_LT};padding:1px 7px;'
                     f'border-radius:3px;font-size:10px;margin-left:7px;font-weight:bold;">{rating}</span>'
                     if rating else "")
            movies_html += f"""
            <div style="margin-bottom:12px;padding-bottom:10px;border-bottom:1px dashed #E8DFC8;">
              <span style="font-size:14px;font-weight:bold;color:{IRON};">{m.get('title','')}</span>{badge}
              <div style="margin-top:5px;">{times}</div>
            </div>"""
        out += f"""
        <div style="margin-bottom:18px;padding:16px;background:{IVORY};
                    border-radius:6px;border-left:4px solid {GOLD};
                    border:1px solid #E8DFC8;border-left:4px solid {GOLD};">
          <div style="font-weight:bold;font-size:15px;color:{PURPLE};">{t.get('theater','')}</div>
          <div style="font-size:12px;color:{CYPRESS};margin-bottom:12px;font-style:italic;">
            📍 {t.get('address','')}
          </div>
          {movies_html}
        </div>"""
    return out


def html_weather(weather: dict) -> str:
    out = ""
    for city, forecast in weather.items():
        d = forecast.get("daily", {})
        out += (f'<div style="font-size:13px;font-weight:bold;color:{PURPLE};'
                f'margin:18px 0 8px;letter-spacing:.3px;">📍 {city}</div>')
        out += (f'<table style="width:100%;border-collapse:collapse;'
                f'background:linear-gradient(135deg,{GREEN} 0%,#1A3D2E 100%);'
                f'border-radius:8px;border:1px solid {GOLD};margin-bottom:6px;"><tr>')
        for i in range(3):
            try:
                day  = datetime.strptime(d["time"][i], "%Y-%m-%d").strftime("%a %b %d")
                hi   = round(d["temperature_2m_max"][i])
                lo   = round(d["temperature_2m_min"][i])
                cond = WMO.get(d["weathercode"][i], "—")
                pop  = d["precipitation_probability_max"][i] or 0
            except Exception:
                day, hi, lo, cond, pop = f"Day {i+1}", "—", "—", "—", 0
            br = f"border-right:1px solid rgba(200,164,0,.4);" if i < 2 else ""
            out += f"""
            <td style="width:33%;text-align:center;padding:14px 6px;vertical-align:top;{br}">
              <div style="font-size:11px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;letter-spacing:.5px;">{day}</div>
              <div style="font-size:22px;font-weight:bold;color:#FAF3E0;margin:5px 0;">
                {hi}° <span style="color:rgba(250,243,224,.5);font-size:14px;">/ {lo}°</span>
              </div>
              <div style="font-size:11px;color:#B8D4C0;">{cond}</div>
              <div style="font-size:11px;color:{GOLD};margin-top:3px;">💧 {pop}%</div>
            </td>"""
        out += "</tr></table>"
    return out


def html_lsu(data: dict) -> str:
    scores = data.get("scores", [])
    rows = ""
    for s in scores:
        w   = s.get("result", "").upper().startswith("W")
        bg  = "#E0F2E9" if w else "#FFE8E0"
        clr = "#1A6B35" if w else "#8B1A00"
        rows += f"""
        <tr style="border-bottom:1px solid #E8DFC8;">
          <td style="padding:9px 12px;font-weight:bold;font-size:13px;color:{PURPLE};">
            {s.get('sport','')}
          </td>
          <td style="padding:9px 12px;font-size:13px;color:{IRON};">
            vs {s.get('opponent','')}
          </td>
          <td style="padding:9px 12px;font-size:12px;color:{CYPRESS};font-style:italic;">
            {s.get('date','')}
          </td>
          <td style="padding:9px 12px;text-align:center;">
            <span style="background:{bg};color:{clr};font-weight:bold;
                         padding:3px 12px;border-radius:12px;font-size:13px;">
              {s.get('result','')}
            </span>
          </td>
        </tr>"""
    table = ""
    if rows:
        table = f"""
        <table style="width:100%;border-collapse:collapse;margin-bottom:18px;
                      border-radius:8px;overflow:hidden;border:1px solid {GOLD};">
          <thead>
            <tr style="background:linear-gradient(90deg,{PURPLE} 0%,#5A2A9A 100%);">
              <th style="padding:10px 12px;text-align:left;font-size:11px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">SPORT</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">OPPONENT</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">DATE</th>
              <th style="padding:10px 12px;text-align:center;font-size:11px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">RESULT</th>
            </tr>
          </thead>
          <tbody style="background:{IVORY};">{rows}</tbody>
        </table>"""
    return table + html_stories(data.get("stories", []))


def html_quotes(quotes: list) -> str:
    palette = [("#e3f2fd","#1565C0"), ("#f3e5f5","#6a1b9a"), ("#fff8e1","#f57f17")]
    out = ""
    for i, q in enumerate(quotes):
        bg, br = palette[i % len(palette)]
        out += f"""
        <div style="background:{bg};border-left:4px solid {br};border-radius:6px;
                    padding:16px 18px;margin-bottom:16px;">
          <div style="font-style:italic;font-size:15px;color:#222;line-height:1.7;">
            &ldquo;{q.get('quote','')}&rdquo;
          </div>
          <div style="margin-top:10px;font-size:13px;font-weight:bold;color:#444;">
            — {q.get('author','')}
            <span style="font-weight:normal;font-style:italic;"> ({q.get('work','')})</span>
          </div>
          <div style="margin-top:6px;font-size:12px;color:#666;">{q.get('context','')}</div>
        </div>"""
    return out


def html_word(w: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{PURPLE} 0%,#2A0A50 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:10px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:8px;">⚜ &nbsp; {w.get('category','')}</div>
      <div style="font-size:26px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;">
        {w.get('word','')}
      </div>
      <div style="font-size:13px;color:rgba(200,180,120,.8);margin:4px 0 12px;font-style:italic;">
        {w.get('pronunciation','')}
      </div>
      <div style="font-size:14px;color:#D8C8A8;line-height:1.7;">{w.get('definition','')}</div>
    </div>"""


def html_on_this_day(e: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:10px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:6px;">⚜ &nbsp; {date.today().strftime('%B %d').upper()}</div>
      <div style="font-size:22px;font-weight:bold;color:{GOLD_LT};margin-bottom:4px;">
        {e.get('year','')}
      </div>
      <div style="font-size:15px;font-weight:bold;color:#FAF3E0;margin-bottom:10px;line-height:1.4;">
        {e.get('headline','')}
      </div>
      <div style="font-size:14px;color:#C8B890;line-height:1.7;border-top:1px solid rgba(200,164,0,.3);
                  padding-top:10px;">{e.get('story','')}</div>
    </div>"""


def html_miltech(stories: list) -> str:
    if not stories:
        return f'<p style="color:{MOSS};font-size:13px;font-style:italic;">No military tech stories retrieved today.</p>'
    out = ""
    for s in stories:
        cat = s.get("category", "Defense Tech")
        bg, fg = CAT_COLORS.get(cat, (CREAM, PURPLE))
        url = s.get("url", "#")
        out += f"""
        <div style="margin-bottom:18px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;border-left:4px solid {GOLD};">
          <div style="margin-bottom:7px;">
            <span style="background:{bg};color:{fg};border-radius:3px;padding:2px 8px;
                         font-size:11px;font-weight:bold;letter-spacing:.3px;
                         border:1px solid {GOLD_LT};">{cat}</span>
          </div>
          <div style="font-size:15px;font-weight:bold;line-height:1.4;margin-bottom:6px;">
            <a href="{url}" style="color:{PURPLE};text-decoration:none;">{s.get('headline','')}</a>
          </div>
          <div style="font-size:13px;color:#5a5040;line-height:1.6;margin-bottom:6px;">
            {s.get('summary','')}
          </div>
          <div style="font-size:11px;">
            <a href="{url}" style="color:{GOLD};text-decoration:none;">🔗 {url}</a>
          </div>
        </div>"""
    return out


def html_louisiana_festivals(events: list) -> str:
    if not events:
        return f'<p style="color:{MOSS};font-size:13px;font-style:italic;">No festival listings found for the next 30 days.</p>'
    out = ""
    for e in events:
        url_html = ""
        if e.get("url"):
            url_html = (f'<a href="{e["url"]}" style="font-size:12px;color:{GOLD};'
                        f'font-weight:bold;text-decoration:none;">More info ⚜</a>')
        date_parts = (e.get("dates") or "").split()
        date_top   = date_parts[0] if date_parts else ""
        date_rest  = " ".join(date_parts[1:]) if len(date_parts) > 1 else ""
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;
                    display:table;width:100%;box-sizing:border-box;">
          <div style="display:table-cell;width:78px;vertical-align:top;padding-right:14px;">
            <div style="background:linear-gradient(135deg,{PURPLE} 0%,#5A2A9A 100%);
                        border-radius:6px;padding:8px 4px;text-align:center;
                        border:1px solid {GOLD};">
              <div style="font-size:12px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;letter-spacing:.5px;">{date_top}</div>
              <div style="font-size:10px;color:rgba(212,175,55,.7);margin-top:2px;">{date_rest}</div>
            </div>
          </div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-size:15px;font-weight:bold;color:{PURPLE};">{e.get('name','')}</div>
            <div style="font-size:12px;color:{CYPRESS};margin:3px 0;font-style:italic;">
              📍 {e.get('location','')} &nbsp;·&nbsp; {e.get('dates','')}
            </div>
            <div style="font-size:13px;color:#5a5040;margin-top:5px;line-height:1.5;">
              {e.get('description','')}
            </div>
            <div style="margin-top:7px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_el_paso_weekend(events: list) -> str:
    if not events:
        return f'<p style="color:{MOSS};font-size:13px;font-style:italic;">No weekend listings found.</p>'
    out = ""
    for e in events:
        url_html = ""
        if e.get("url"):
            url_html = (f'<a href="{e["url"]}" style="font-size:12px;color:{GOLD};'
                        f'font-weight:bold;text-decoration:none;">Details →</a>')
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;
                    display:table;width:100%;box-sizing:border-box;">
          <div style="display:table-cell;width:78px;vertical-align:top;padding-right:14px;">
            <div style="background:linear-gradient(135deg,{GREEN} 0%,#1A3D2E 100%);
                        border-radius:6px;padding:8px 4px;text-align:center;
                        border:1px solid {GOLD};">
              <div style="font-size:10px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;line-height:1.4;letter-spacing:.3px;">
                {e.get('when','')}
              </div>
            </div>
          </div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-size:15px;font-weight:bold;color:{PURPLE};">{e.get('name','')}</div>
            <div style="font-size:12px;color:{CYPRESS};margin:3px 0;font-style:italic;">
              📍 {e.get('venue','')}
            </div>
            <div style="font-size:13px;color:#5a5040;margin-top:5px;line-height:1.5;">
              {e.get('description','')}
            </div>
            <div style="margin-top:7px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_el_paso_weekend(events: list) -> str:
    if not events:
        return '<p style="color:#888;font-size:13px;">No weekend listings found.</p>'
    out = ""
    for e in events:
        url_html = ""
        if e.get("url"):
            url_html = (f'<a href="{e["url"]}" style="font-size:12px;color:#1565C0;'
                        f'text-decoration:none;">Details →</a>')
        out += f"""
        <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #eee;
                    display:flex;gap:14px;align-items:flex-start;">
          <div style="min-width:72px;text-align:center;background:#e3f2fd;border-radius:6px;
                      padding:6px 4px;border:1px solid #90caf9;">
            <div style="font-size:10px;font-weight:bold;color:#1565C0;text-transform:uppercase;
                        line-height:1.3;">{e.get('when','')}</div>
          </div>
          <div style="flex:1;">
            <div style="font-size:15px;font-weight:bold;color:#1a1a1a;">{e.get('name','')}</div>
            <div style="font-size:12px;color:#888;margin:2px 0;">📍 {e.get('venue','')}</div>
            <div style="font-size:13px;color:#555;margin-top:4px;line-height:1.5;">{e.get('description','')}</div>
            <div style="margin-top:5px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_crs(reports: list) -> str:
    if not reports:
        return (f'<p style="font-size:13px;color:{MOSS};font-style:italic;">No recent CRS reports retrieved. '
                f'Browse at <a href="https://crsreports.congress.gov" style="color:{GOLD};">crsreports.congress.gov</a>.</p>')
    out = ""
    for r in reports:
        num  = r.get("report_number", "")
        dt   = r.get("date", "")
        meta = " &nbsp;·&nbsp; ".join(x for x in [num, dt] if x)
        url  = r.get("url", "https://crsreports.congress.gov")
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;border-left:4px solid {PURPLE};">
          <div style="font-size:14px;font-weight:bold;margin-bottom:4px;">
            <a href="{url}" style="color:{PURPLE};text-decoration:none;">
              {r.get('short_title', r.get('title',''))}
            </a>
          </div>
          <div style="font-size:12px;color:{CYPRESS};font-style:italic;margin-bottom:5px;">
            {r.get('title','')}
          </div>
          <div style="font-size:11px;color:#A09070;">{meta}
            &nbsp;·&nbsp; <a href="{url}" style="color:{GOLD};text-decoration:none;">🔗 View report</a>
          </div>
        </div>"""
    out += (f'<div style="text-align:right;font-size:12px;margin-top:6px;">'
            f'<a href="https://crsreports.congress.gov" style="color:{GOLD};">'
            f'Browse all CRS reports ⚜</a></div>')
    return out


def html_ingredient(ing: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:10px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:8px;">⚜ &nbsp; Clebeaux's Kitchen — {ing.get('season','')}</div>
      <div style="font-size:24px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;
                  margin-bottom:12px;">
        {ing.get('ingredient','')}
      </div>
      <div style="font-size:14px;color:#D8C0A0;line-height:1.8;font-style:italic;
                  border-top:1px solid rgba(200,164,0,.3);padding-top:12px;">
        {ing.get('note','')}
      </div>
    </div>"""


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════════

def build_email(d: dict) -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")
    s = d.get("snark", {})  # snarky comments dict

    other_html = ""
    for city, stories in d["other_news"].items():
        other_html += f"""
        <div style="font-size:13px;font-weight:bold;color:{PURPLE};
                    margin:18px 0 8px;border-top:1px solid #E8DFC8;padding-top:14px;">
          ⚜ {city}
        </div>"""
        other_html += html_stories(stories)

    # Fleur-de-lis divider used between major sections in footer
    fdl = f'<div style="text-align:center;color:{GOLD};font-size:18px;margin:4px 0;letter-spacing:8px;">⚜ ⚜ ⚜</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    * {{ box-sizing:border-box; }}
    body {{ margin:0;padding:0;background:#2A1A0A;font-family:Georgia,serif; }}
    a {{ color:{GOLD}; }}
  </style>
</head>
<body>
<div style="max-width:660px;margin:20px auto;background:{CREAM};border-radius:10px;
            overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.5);
            border:2px solid {GOLD};">

  <!-- ══ MASTHEAD ══ -->
  <div style="background:linear-gradient(135deg,{PURPLE} 0%,#1A0A3C 60%,{GREEN} 100%);
              padding:28px;text-align:center;position:relative;border-bottom:3px solid {GOLD};">
    <div style="font-size:30px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;
                letter-spacing:2px;text-shadow:0 2px 8px rgba(0,0,0,.5);">
      ⚜ &nbsp; Daily Digest &nbsp; ⚜
    </div>
    <div style="color:rgba(212,175,55,.8);font-size:13px;margin-top:6px;letter-spacing:.8px;">
      Fort Bliss &nbsp;·&nbsp; El Paso &nbsp;·&nbsp; {today}
    </div>
    <div style="color:rgba(212,175,55,.4);font-size:18px;letter-spacing:12px;margin-top:8px;">
      ⚜ ⚜ ⚜
    </div>
  </div>

  <!-- ══ BODY ══ -->
  <div style="padding:26px 28px;background:{CREAM};">

    {h2("📈", "Market Snapshot")}
    {html_snark(s.get("markets",""))}
    {html_markets(d["markets"])}

    {h2("📍", "El Paso / Fort Bliss — Local News")}
    {html_snark(s.get("ep_news",""))}
    {html_stories(d["ep_news"])}

    {h2("🎉", "Louisiana Festivals — Next 30 Days")}
    {html_snark(s.get("la_festivals",""))}
    {html_louisiana_festivals(d["la_festivals"])}

    {h2("🌵", "El Paso / Fort Bliss — This Weekend")}
    {html_snark(s.get("ep_weekend",""))}
    {html_el_paso_weekend(d["ep_weekend"])}

    {h2("🎬", "Movies in El Paso — Today's Showtimes")}
    {html_movies(d["movies"])}

    {h2("🌤️", "3-Day Weather Forecast")}
    {html_snark(s.get("weather",""))}
    {html_weather(d["weather"])}

    {h2("🐯", "LSU Tigers Sports")}
    {html_snark(s.get("lsu",""))}
    {html_lsu(d["lsu"])}

    {h2("🌿", "Louisiana — NOLA · Baton Rouge · Northshore")}
    {html_snark(s.get("louisiana",""))}
    {html_stories(d["louisiana"], badge_key="area", badge_colors=AREA_COLORS)}

    {h2("📚", "From the Great Books of the Western World")}
    {html_quotes(d["quotes"])}

    {h2("🔤", "Word of the Day")}
    {html_snark(s.get("word_of_day",""))}
    {html_word(d["word"])}

    {h2("📅", "On This Day in History")}
    {html_snark(s.get("on_this_day",""))}
    {html_on_this_day(d["on_this_day"])}

    {h2("🪖", "DoD / Army News")}
    {html_snark(s.get("dod_news",""))}
    {html_stories(d["dod_news"])}

    {h2("💰", "Defense Budget & Congressional Tracker")}
    {html_snark(s.get("budget_news",""))}
    {html_stories(d["budget_news"])}

    {h2("📋", "Congressional Research Service — DoD Reports")}
    {html_crs(d["crs"])}

    {h2("🌍", "Major World & European News")}
    {html_snark(s.get("world_news",""))}
    {html_stories(d["world_news"], badge_key="region", badge_colors=REGION_COLORS)}

    {h2("🛡️", "Military Technology — New Developments")}
    {html_snark(s.get("miltech",""))}
    {html_miltech(d["miltech"])}

    {h2("🍳", "Ingredient of the Day")}
    {html_snark(s.get("ingredient",""))}
    {html_ingredient(d["ingredient"])}

    {h2("📰", "Regional News")}
    {other_html}

  </div>

  <!-- ══ FOOTER ══ -->
  <div style="background:linear-gradient(135deg,{PURPLE} 0%,#1A0A3C 60%,{GREEN} 100%);
              padding:16px;text-align:center;border-top:3px solid {GOLD};">
    <div style="color:rgba(212,175,55,.5);font-size:16px;letter-spacing:10px;margin-bottom:8px;">
      ⚜ ⚜ ⚜
    </div>
    <div style="font-size:11px;color:rgba(212,175,55,.6);letter-spacing:.8px;">
      Daily Digest &nbsp;·&nbsp; Fort Bliss / El Paso &nbsp;·&nbsp; {today}
    </div>
  </div>

</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  SEND
# ══════════════════════════════════════════════════════════════════════════════

def send_email(html_body: str):
    today = datetime.now().strftime("%b %d, %Y")
    recipients = [addr.strip() for addr in TO_EMAIL.split(",") if addr.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Daily Digest — Fort Bliss / El Paso — {today}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"✅ Email sent to {len(recipients)} recipient(s).")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    steps = [
        ("📈 Markets",               "markets",     get_markets),
        ("🎉 Louisiana festivals",   "la_festivals", get_louisiana_festivals),
        ("🌵 EP weekend events",     "ep_weekend",   get_el_paso_weekend),
        ("📍 El Paso news",          "ep_news",      lambda: get_news("El Paso Texas Fort Bliss local news", 4)),
        ("🎬 Movies",                "movies",      get_movies_el_paso),
        ("🐯 LSU sports",            "lsu",         get_lsu_sports),
        ("🌿 Louisiana news",        "louisiana",   get_louisiana_news),
        ("📚 Philosopher quotes",    "quotes",      get_philosopher_quotes),
        ("🔤 Word of the day",       "word",        get_word_of_the_day),
        ("📅 On this day",           "on_this_day", get_on_this_day),
        ("🪖 DoD/Army news",         "dod_news",    get_dod_army_news),
        ("💰 Defense budget",        "budget_news", get_defense_budget_news),
        ("📋 CRS reports",           "crs",         get_crs_links),
        ("🌍 World news",            "world_news",  get_world_news),
        ("🛡️  Military tech links",  "miltech",     get_military_tech_links),
        ("🍳 Ingredient of the day", "ingredient",  get_ingredient_of_the_day),
    ]

    data = {}

    # Weather fetched separately (multiple locations)
    print("🌤  Fetching weather...")
    data["weather"] = {}
    for city, (lat, lon) in LOCATIONS.items():
        print(f"    → {city}")
        data["weather"][city] = get_weather(lat, lon)

    # Regional news
    print("📰 Fetching regional news...")
    data["other_news"] = {
        "Ellensburg, WA":  get_news("Ellensburg Washington local news", 2),
        "Pearl River, LA": get_news("Pearl River Louisiana Slidell Northshore local news", 2),
    }

    # All other sections
    for label, key, fn in steps:
        print(f"{label}...")
        data[key] = fn()

    print("😏 Generating snarky commentary...")
    data["snark"] = get_snarky_comments(data)

    print("✉️  Building and sending email...")
    send_email(build_email(data))
    print("✅ Done.")


if __name__ == "__main__":
    main()
