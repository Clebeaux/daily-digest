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
            if "error" in data:
                err = data["error"]
                print(f"    ⚠️  API error: {err}")
                # Rate limit — wait longer before retry
                if "rate_limit" in str(err.get("type","")):
                    wait = 65 + (attempt * 30)
                    print(f"    ⏳ Rate limit hit, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    time.sleep(10)
                continue
            return "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ).strip()
        except Exception as e:
            print(f"    ⚠️  Claude attempt {attempt + 1} failed: {e}")
            time.sleep(10)
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

# ── El Paso local news RSS feeds ──────────────────────────────────────────────
EP_NEWS_RSS = [
    ("KVIA ABC-7", "https://kvia.com/feed/"),
    ("KTSM NBC-9", "https://www.ktsm.com/feed/"),
    ("KDBC CBS-4", "https://kdbc.com/feed/"),
    ("El Paso Matters", "https://elpasomatters.org/feed/"),
]

# ── Military tech / defense RSS feeds ─────────────────────────────────────────
MILTECH_RSS = [
    ("C4ISRNET",        "https://www.c4isrnet.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Defense One",     "https://www.defenseone.com/rss/all/"),
    ("War on the Rocks","https://warontherocks.com/feed/"),
    ("AUSA",            "https://www.ausa.org/rss.xml"),
    ("Breaking Defense","https://breakingdefense.com/feed/"),
    ("Defense Post",    "https://thedefensepost.com/feed/"),
]

# Keywords to flag as M&S / LVC relevant for category tagging
MS_KEYWORDS   = ["simulation","synthetic","lvc","hla","dis","tena","constructive",
                  "digital twin","modeling","emulation","federation","jlvc","jlcctc"]
AI_KEYWORDS   = ["artificial intelligence","machine learning","ai ","autonomous","algorithm"]
HYPER_WORDS   = ["hypersonic","mach ","glide vehicle"]
DE_KEYWORDS   = ["directed energy","laser","high energy","microwave"]
CYBER_WORDS   = ["cyber","hack","electronic warfare","ew ","jamming"]
AUTO_WORDS    = ["drone","uav","uas","unmanned","robot","autonomous system"]


def _tag_miltech_category(headline: str, summary: str) -> str:
    text = (headline + " " + summary).lower()
    if any(k in text for k in MS_KEYWORDS):   return "Modeling & Simulation"
    if any(k in text for k in AI_KEYWORDS):   return "AI/ML"
    if any(k in text for k in AUTO_WORDS):    return "Autonomous Systems"
    if any(k in text for k in HYPER_WORDS):   return "Hypersonics"
    if any(k in text for k in DE_KEYWORDS):   return "Directed Energy"
    if any(k in text for k in CYBER_WORDS):   return "Cybersecurity"
    return "Defense Tech"


def get_news(topic: str, count: int) -> list:
    """Generic Claude-search news fetch — used for regional/other topics."""
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


COMMON_SPANISH = {
    "el","la","los","las","de","del","en","con","por","para","que","una","uno",
    "su","sus","es","son","fue","ha","han","se","al","más","pero","como","este",
    "esta","estos","estas","está","están","tiene","tienen","según","también",
    "sobre","entre","cuando","donde","cómo","qué","quién","nuevo","nueva",
    "nuevos","ciudad","policía","mujer","hombre","años","caso","tras"
}

def _is_english(text: str) -> bool:
    """Return True if text appears to be English, False if likely Spanish."""
    words = text.lower().split()
    if not words:
        return True
    spanish_hits = sum(1 for w in words if w.strip(".,!?;:\"'") in COMMON_SPANISH)
    return (spanish_hits / len(words)) < 0.15  # >15% Spanish words → reject


def get_ep_news() -> list:
    """
    El Paso local news via RSS from KVIA, KFOX14, KTSM, El Paso Inc.
    Filters out Spanish-language stories.
    Falls back to Claude search if all feeds fail.
    """
    all_items = []
    for source, feed_url in EP_NEWS_RSS:
        items = _fetch_rss(feed_url, max_items=6)
        for item in items:
            item["source"] = source
        all_items.extend(items)

    # Filter Spanish, deduplicate
    seen = set()
    unique = []
    for item in all_items:
        headline = item.get("headline", "")
        if not _is_english(headline):
            continue
        key = headline[:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if unique:
        return unique[:5]

    print("    ⚠️  EP RSS feeds empty, falling back to Claude search")
    return get_news("El Paso Texas Fort Bliss local news", 4)


def get_military_tech_links() -> list:
    """
    Military technology news via RSS from C4ISRNET, Defense One,
    War on the Rocks, AUSA, NDIA, Breaking Defense.
    Auto-tags each story with an M&S/tech category.
    Falls back to Claude search if feeds are empty.
    """
    all_items = []
    for source, feed_url in MILTECH_RSS:
        items = _fetch_rss(feed_url, max_items=5)
        for item in items:
            item["source"]   = source
            item["category"] = _tag_miltech_category(
                item.get("headline", ""), item.get("summary", "")
            )
        all_items.extend(items)

    # Deduplicate
    seen = set()
    unique = []
    for item in all_items:
        key = item.get("headline", "")[:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if unique:
        # Prioritize M&S stories first, then others
        ms_first = sorted(
            unique,
            key=lambda x: 0 if x.get("category") in
                ("Modeling & Simulation", "LVC/Training", "AI/ML") else 1
        )
        return ms_first[:6]

    # Fallback to Claude
    print("    ⚠️  Miltech RSS feeds empty, falling back to Claude search")
    text = _claude(
        "Search for 4-5 recent military technology news articles (last 7 days). "
        "Prioritize M&S, LVC, synthetic training, AI in defense, autonomous systems, hypersonics. "
        "Return ONLY a JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        "'url' (real https URL), 'category'. No markdown. Pure JSON."
    )
    r = _parse_json(text)
    if not isinstance(r, list):
        return []
    return [s for s in r if isinstance(s.get("url",""), str)
            and s["url"].startswith("http") and len(s["url"]) > 20] or r


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


LA_NEWS_RSS = [
    ("WWL-TV",    "https://www.wwltv.com/feeds/syndication/rss/"),
    ("WDSU",      "https://www.wdsu.com/rss"),
    ("WBRZ",      "https://www.wbrz.com/rss/headlines/"),
    ("WVUE",      "https://www.fox8live.com/rss/"),
    ("Nola.com",  "https://www.nola.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc"),
]

LA_AREA_MAP = {
    "new orleans": "New Orleans", "metairie": "New Orleans", "kenner": "New Orleans",
    "baton rouge": "Baton Rouge", "denham springs": "Baton Rouge",
    "slidell": "Northshore",  "covington": "Northshore", "mandeville": "Northshore",
    "hammond": "Northshore",  "talisheek": "Northshore", "bogalusa": "Northshore",
    "st. tammany": "Northshore", "tangipahoa": "Northshore",
}

def _guess_la_area(text: str) -> str:
    t = text.lower()
    for keyword, area in LA_AREA_MAP.items():
        if keyword in t:
            return area
    return "Statewide"


def get_louisiana_news() -> list:
    """Louisiana news via RSS from WWL-TV, WDSU, The Advocate, WAFB, WVUE."""
    all_items = []
    for source, feed_url in LA_NEWS_RSS:
        items = _fetch_rss(feed_url, max_items=4)
        for item in items:
            item["source"] = source
            item["area"]   = _guess_la_area(
                item.get("headline","") + " " + item.get("summary","")
            )
        all_items.extend(items)

    seen = set()
    unique = []
    for item in all_items:
        key = item.get("headline","")[:40].lower()
        if key not in seen and _is_english(item.get("headline","")):
            seen.add(key)
            unique.append(item)

    if unique:
        return unique[:5]

    # Fallback
    print("    ⚠️  Louisiana RSS empty, falling back to Claude")
    text = _claude(
        "Search for 4 recent Louisiana news stories — New Orleans, Baton Rouge, Northshore. "
        "Return ONLY a JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
        "'area' (New Orleans/Baton Rouge/Northshore/Statewide). No markdown. Pure JSON."
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
    """
    Fetch a real historical event from Wikipedia's free On This Day API.
    Falls back to Claude if Wikipedia is unavailable.
    """
    today = date.today()
    month, day = today.month, today.day
    # Prefer military/science/exploration events
    prefer_keywords = [
        "war","battle","military","army","navy","air force","space","moon",
        "expedition","invention","discovery","treaty","constitution","revolution",
        "launched","founded","assassinated","declared","surrender","signed"
    ]
    try:
        url  = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
        resp = requests.get(url, headers={"User-Agent":"DailyDigest/3.0"}, timeout=10)
        data = resp.json()
        events = data.get("events", [])
        # Score events by keyword relevance
        def score(e):
            text = (e.get("text","") + " ".join(
                p.get("title","") for p in e.get("pages",[])
            )).lower()
            return sum(1 for kw in prefer_keywords if kw in text)
        events_sorted = sorted(events, key=score, reverse=True)
        if events_sorted:
            e = events_sorted[0]
            return {
                "year":     str(e.get("year","")),
                "headline": e.get("text","")[:120],
                "story":    e.get("text",""),
            }
    except Exception as ex:
        print(f"    ⚠️  Wikipedia On This Day failed: {ex}")

    # Fallback to Claude
    today_str = date.today().strftime("%B %d")
    text = _claude(
        f"What is one notable historical event that occurred on {today_str}? "
        f"Prefer military history, science, philosophy, or American history. "
        f"Return ONLY a JSON object: 'year', 'headline' (one line), 'story' (2-3 sentences). "
        f"No markdown. Pure JSON.",
        use_search=False, max_tokens=400,
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
    """Fetch El Paso things to do this weekend via Claude search."""
    from datetime import timedelta
    today       = date.today()
    today_str   = today.strftime("%B %d, %Y")
    days_to_fri = (4 - today.weekday()) % 7 or 7
    fri = (today + timedelta(days=days_to_fri)).strftime("%B %d")
    sun = (today + timedelta(days=days_to_fri + 2)).strftime("%B %d")
    weekend_str = f"{fri}–{sun}"

    text = _claude(
        f"Today is {today_str}. Search for things to do in El Paso Texas this weekend "
        f"({weekend_str}). Search ElPasoTX.gov events calendar, eventbrite El Paso, "
        f"Visit El Paso, and local venue websites. Include concerts, festivals, markets, "
        f"sports, outdoor activities, art shows, food events, Fort Bliss MWR events. "
        f"Return ONLY a JSON array of 5-7 items. Each element: "
        f"'name', 'venue', 'when' (e.g. 'Sat 7 PM'), 'description' (1-2 sentences), "
        f"'url' (website if available, else empty string). "
        f"Sort by date/time. No markdown. Pure JSON.",
        max_tokens=1000,
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"name": "Check El Paso events", "venue": "Various",
         "when": "This weekend",
         "description": "Visit visitelpasoTexas.com or eventbrite.com for current listings.",
         "url": "https://www.visitelpasotexas.com/events/"}
    ]


def get_ep_restaurants() -> list:
    """
    El Paso restaurant and bar news — new openings, closings, reviews.
    Uses Claude search targeting local food blogs and news sites.
    """
    today_str = date.today().strftime("%B %d, %Y")
    text = _claude(
        f"Today is {today_str}. Search for recent El Paso Texas restaurant and bar news "
        f"from the last 30 days. Look for: new restaurant openings, bar openings, "
        f"restaurant closings, notable menu changes, new chef announcements, food truck news, "
        f"and dining reviews. Search El Paso Inc, KVIA, KFOX14, Yelp El Paso, "
        f"and local food blogs. "
        f"Return ONLY a JSON array of 4-5 items. Each element: "
        f"'name' (restaurant or bar name), "
        f"'status' (e.g. 'New Opening', 'Closed', 'New Menu', 'Review', 'Food Truck'), "
        f"'location' (neighborhood or street), "
        f"'description' (1-2 sentences — what it is, what's notable), "
        f"'url' (link if available, else empty string). "
        f"No markdown. Pure JSON.",
        max_tokens=900,
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"name": "Restaurant news unavailable", "status": "",
         "location": "", "description": "Could not retrieve local dining news.", "url": ""}
    ]


def _fetch_rss(url: str, max_items: int = 5) -> list:
    """
    Fetch and parse an RSS feed. Returns list of {title, summary, url, source, date}.
    No API key required. Pure HTTP + simple XML parsing.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DailyDigest/3.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        xml = resp.text

        items = []
        # Split on <item> tags
        raw_items = xml.split("<item>")[1:]
        for raw in raw_items[:max_items]:
            def tag(t):
                import re
                m = re.search(rf"<{t}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", raw, re.S)
                return m.group(1).strip() if m else ""

            title   = tag("title")
            link    = tag("link") or tag("guid")
            desc    = tag("description")
            pubdate = tag("pubDate")

            # Strip HTML tags from description
            import re
            desc = re.sub(r"<[^>]+>", "", desc).strip()
            desc = desc[:300] + "…" if len(desc) > 300 else desc

            if title:
                items.append({
                    "headline": title,
                    "summary":  desc or title,
                    "url":      link,
                    "date":     pubdate,
                })
        return items
    except Exception as e:
        print(f"    ⚠️  RSS fetch failed for {url}: {e}")
        return []


# DoD / Army RSS feeds — no paywall, updated continuously
DOD_RSS_FEEDS = [
    ("Defense News",    "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Breaking Defense","https://breakingdefense.com/feed/"),
    ("Army Times",      "https://www.armytimes.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("DoD News",        "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10"),
    ("DVIDS",           "https://www.dvidshub.net/rss/news"),
]

# CRS RSS / search feed
CRS_RSS_URL = "https://crsreports.congress.gov/search/#/?termsToSearch=defense+army+military&orderBy=Date"
CRS_RSS_FEED = "https://crsreports.congress.gov/search/rss?term=defense+military+army&r=1&order=1"


def get_dod_army_news() -> list:
    """Pull DoD/Army news from RSS feeds — no paywall, always has content."""
    all_items = []
    for source, feed_url in DOD_RSS_FEEDS:
        items = _fetch_rss(feed_url, max_items=3)
        for item in items:
            item["source"] = source
        all_items.extend(items)
        if len(all_items) >= 4:
            break

    if not all_items:
        # Fallback to Claude search
        text = _claude(
            "Search Defense News, Breaking Defense, Army Times for 3-4 important DoD/Army "
            "news stories from the last 48 hours. Cover acquisition, readiness, operations, budget. "
            "Return ONLY a JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
            "'source'. No markdown. Pure JSON."
        )
        r = _parse_json(text)
        return r if isinstance(r, list) and r else [
            {"headline": "DoD news unavailable", "summary": "", "source": ""}
        ]

    return all_items[:4]


def get_defense_budget_news() -> list:
    """Pull defense budget news from RSS then filter for budget/M&S relevance via Claude."""
    items = []
    for source, feed_url in DOD_RSS_FEEDS[:3]:
        fetched = _fetch_rss(feed_url, max_items=10)
        for item in fetched:
            item["source"] = source
        items.extend(fetched)

    # Filter for budget/acquisition/M&S relevance
    budget_keywords = [
        "budget", "appropriation", "ndaa", "funding", "contract", "acquisition",
        "simulation", "training", "lvc", "m&s", "congress", "senate", "house",
        "billion", "million", "program", "procurement"
    ]
    relevant = [
        i for i in items
        if any(kw in (i.get("headline","") + i.get("summary","")).lower()
               for kw in budget_keywords)
    ][:3]

    if not relevant:
        # Fallback to Claude
        text = _claude(
            "Search for 2-3 recent stories about US defense budget, NDAA, or M&S/simulation "
            "program funding from the last 7 days. "
            "Return ONLY a JSON array. Each element: 'headline', 'summary' (1-2 sentences), "
            "'relevance' (why it matters to M&S). No markdown. Pure JSON."
        )
        r = _parse_json(text)
        return r if isinstance(r, list) and r else [
            {"headline": "Defense budget news unavailable", "summary": "", "relevance": ""}
        ]

    # Add relevance tag via Claude
    for item in relevant:
        item["relevance"] = ""  # blank is fine — html_stories handles missing relevance
    return relevant


def get_crs_links() -> list:
    """
    Pull CRS reports via their RSS feed.
    Falls back to search page link if RSS is empty.
    """
    items = _fetch_rss(CRS_RSS_FEED, max_items=6)

    # Filter for defense relevance
    def_keywords = [
        "defense", "army", "military", "dod", "navy", "air force", "marine",
        "weapon", "nato", "national security", "simulation", "budget", "ndaa",
        "veteran", "pentagon", "armed forces", "war", "combat", "intelligence"
    ]
    relevant = [
        i for i in items
        if any(kw in (i.get("headline","") + i.get("summary","")).lower()
               for kw in def_keywords)
    ]

    # Format to match expected CRS structure
    results = []
    for item in (relevant or items)[:5]:
        results.append({
            "title":         item.get("headline", ""),
            "short_title":   " ".join(item.get("headline", "").split()[:7]),
            "report_number": "",
            "date":          item.get("date", ""),
            "url":           item.get("url", "https://crsreports.congress.gov"),
        })

    if not results:
        # Return a helpful placeholder pointing to the live search
        results = [{
            "title":         "Browse current DoD-related CRS reports",
            "short_title":   "Search CRS for defense reports",
            "report_number": "",
            "date":          "",
            "url":           "https://crsreports.congress.gov/search/#/?termsToSearch=defense+army&orderBy=Date",
        }]
    return results


WORLD_NEWS_RSS = [
    ("BBC World",  "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Reuters",    "https://feeds.reuters.com/reuters/topNews"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("RFI",        "https://www.rfi.fr/en/rss"),
]

WORLD_REGION_MAP = {
    "ukraine":"Europe","russia":"Europe","germany":"Europe","france":"Europe",
    "britain":"Europe","uk ":"Europe","european":"Europe","nato":"Europe",
    "poland":"Europe","spain":"Europe","italy":"Europe","greece":"Europe",
    "israel":"Middle East","gaza":"Middle East","iran":"Middle East",
    "saudi":"Middle East","iraq":"Middle East","syria":"Middle East",
    "lebanon":"Middle East","palestine":"Middle East","yemen":"Middle East",
    "china":"Asia","japan":"Asia","korea":"Asia","taiwan":"Asia",
    "india":"Asia","pakistan":"Asia","afghanistan":"Asia","vietnam":"Asia",
    "africa":"Africa","nigeria":"Africa","kenya":"Africa","ethiopia":"Africa",
    "egypt":"Africa","south africa":"Africa",
    "canada":"Americas","mexico":"Americas","brazil":"Americas",
    "venezuela":"Americas","colombia":"Americas","argentina":"Americas",
}

def _guess_region(text: str) -> str:
    t = text.lower()
    for keyword, region in WORLD_REGION_MAP.items():
        if keyword in t:
            return region
    return "Global"


def get_world_news() -> list:
    """World news via RSS from BBC, Reuters, AP, Al Jazeera."""
    # Filter out US-only stories
    us_only = ["congress","senate","trump","biden","harris","white house",
               "u.s. army","fort bliss","el paso","texas legislature"]
    all_items = []
    for source, feed_url in WORLD_NEWS_RSS:
        items = _fetch_rss(feed_url, max_items=5)
        for item in items:
            hl = item.get("headline","").lower()
            if any(kw in hl for kw in us_only):
                continue
            item["source"] = source
            item["region"] = _guess_region(
                item.get("headline","") + " " + item.get("summary","")
            )
        all_items.extend(items)

    seen = set()
    unique = []
    for item in all_items:
        key = item.get("headline","")[:40].lower()
        if key not in seen and _is_english(item.get("headline","")):
            seen.add(key)
            unique.append(item)

    if unique:
        return unique[:5]

    # Fallback
    print("    ⚠️  World news RSS empty, falling back to Claude")
    text = _claude(
        "Search for 4 major international news stories (not US domestic) from today. "
        "Return ONLY a JSON array. Each element: 'headline', 'summary' (2 sentences), "
        "'region' (Europe/Middle East/Asia/Africa/Americas/Global). No markdown. Pure JSON."
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "World news unavailable", "summary": "", "region": ""}
    ]


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


def get_louisiana_seafood() -> dict:
    """
    Louisiana seafood market report — crawfish, shrimp, oysters, crab.
    Uses Claude search targeting LDWF, Louisiana Seafood Board, and market sources.
    Returns {crawfish, shrimp, oysters, crab, note}
    """
    today_str = date.today().strftime("%B %d, %Y")
    text = _claude(
        f"Today is {today_str}. Search for current Louisiana seafood availability and market "
        f"conditions. Check Louisiana Seafood Board (louisianaseafood.com), Louisiana Department "
        f"of Wildlife and Fisheries (wlf.louisiana.gov), and Gulf seafood market reports. "
        f"Find current status and approximate price ranges for: crawfish, Gulf shrimp, "
        f"Louisiana oysters, and blue crab. Note if anything is in peak season, scarce, "
        f"or has had recent price changes. "
        f"Return ONLY a valid JSON object with five string fields: "
        f"'crawfish' (availability and price note, 1-2 sentences), "
        f"'shrimp' (availability and price note, 1-2 sentences), "
        f"'oysters' (availability and price note, 1-2 sentences), "
        f"'crab' (availability and price note, 1-2 sentences), "
        f"'note' (one sentence — overall market mood or seasonal highlight). "
        f"No markdown, no preamble. Pure JSON.",
        max_tokens=600,
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) and r.get("crawfish") else {
        "crawfish": "Market data unavailable.",
        "shrimp":   "Market data unavailable.",
        "oysters":  "Market data unavailable.",
        "crab":     "Market data unavailable.",
        "note":     "Could not retrieve Louisiana seafood market report today.",
    }


def get_saints_scores() -> dict:
    """
    New Orleans Saints scores and news. Also Pelicans if NBA season is active.
    Returns {saints_record, saints_recent:[{opponent,result,date}],
             pelicans_recent:[{opponent,result,date}], stories:[{headline,summary}]}
    """
    today_str = date.today().strftime("%B %d, %Y")
    text = _claude(
        f"Today is {today_str}. Search for the latest New Orleans Saints NFL news and scores. "
        f"Also check if the New Orleans Pelicans NBA season is currently active and if so "
        f"get their recent scores. "
        f"Return ONLY a valid JSON object with four keys: "
        f"'saints_record' (string, e.g. '8-9' or 'Offseason'), "
        f"'saints_recent' (array of up to 3 objects: opponent, result like 'W 27-10' or 'L 14-21', date), "
        f"'pelicans_recent' (array of up to 3 objects: opponent, result, date — empty array if offseason), "
        f"'stories' (array of 2-3 objects: headline, summary — 1 sentence each — "
        f"covering Saints/Pelicans news, trades, injuries, draft). "
        f"No markdown, no preamble. Pure JSON.",
        max_tokens=700,
    )
    r = _parse_json(text)
    return r if isinstance(r, dict) else {
        "saints_record": "—",
        "saints_recent": [],
        "pelicans_recent": [],
        "stories": [{"headline": "Saints/Pelicans data unavailable", "summary": ""}],
    }


# TRADOC and exercise-relevant RSS feeds
TRADOC_RSS = [
    ("Army.mil",       "https://www.army.mil/rss/2/"),
    ("FORSCOM",        "https://www.army.mil/rss/112/"),
    ("Army News",      "https://www.army.mil/rss/174/"),
]

EXERCISE_KEYWORDS = [
    "exercise","rotation","jrtc","ntc","joint readiness","national training",
    "fort bliss","fort irwin","fort johnson","bliss","irwin","johnson",
    "combined arms","warfighter","calfex","live fire","brigade combat",
    "division","corps","tradoc","forscom","rotational unit","training event",
    "swift response","defender","iron union","austere challenge","ulchi",
]

TRADOC_KEYWORDS = [
    "tradoc","doctrine","atp ","adp ","fm ","field manual","training circular",
    "tc ","adrp","artep","opord","conops","synthetic training","virtual training",
    "lvc","miles","instrumentation","sim","simulation","synthetic","constructive",
    "readiness","training strategy","force design","force 2025","army futures",
]


def get_exercise_schedule() -> list:
    """
    Fort Bliss / JRTC / NTC exercise and rotation schedule news.
    RSS-first, Claude search fallback.
    """
    all_items = []
    for source, feed_url in TRADOC_RSS:
        items = _fetch_rss(feed_url, max_items=10)
        for item in items:
            item["source"] = source
        all_items.extend(items)

    # Filter for exercise-relevant content
    relevant = [
        i for i in all_items
        if any(kw in (i.get("headline","") + i.get("summary","")).lower()
               for kw in EXERCISE_KEYWORDS)
    ][:4]

    if relevant:
        return relevant

    # Fallback to Claude search
    print("    ⚠️  Exercise RSS empty, falling back to Claude")
    text = _claude(
        f"Search for recent news about upcoming or ongoing Army training exercises and rotations "
        f"at Fort Bliss TX, JRTC Fort Johnson LA, NTC Fort Irwin CA, or other major combat training "
        f"centers. Include exercise names, rotating units, and dates if available. Also search for "
        f"any announced WARFIGHTER exercises, joint exercises, or multinational training events "
        f"involving U.S. Army units. "
        f"Return ONLY a JSON array of 3-5 items. Each element: "
        f"'headline', 'summary' (1-2 sentences), 'source' (publication). "
        f"No markdown. Pure JSON.",
        max_tokens=700,
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "Exercise schedule data unavailable",
         "summary": "Check FORSCOM and installation PAO for current rotation schedules.",
         "source": ""}
    ]


def get_tradoc_news() -> list:
    """
    TRADOC doctrine, training strategy, and Army training news.
    RSS-first with keyword filtering, Claude fallback.
    """
    all_items = []
    for source, feed_url in TRADOC_RSS:
        items = _fetch_rss(feed_url, max_items=10)
        for item in items:
            item["source"] = source
        all_items.extend(items)

    # Filter for TRADOC/doctrine/training relevance
    relevant = [
        i for i in all_items
        if any(kw in (i.get("headline","") + i.get("summary","")).lower()
               for kw in TRADOC_KEYWORDS)
    ][:4]

    if relevant:
        return relevant

    # Fallback
    print("    ⚠️  TRADOC RSS empty, falling back to Claude")
    text = _claude(
        f"Search for recent TRADOC news, Army doctrine updates, new field manuals or training "
        f"circulars, synthetic training environment announcements, LVC program updates, "
        f"or Army Force Design initiatives from the last 14 days. "
        f"Return ONLY a JSON array of 3-4 items. Each element: "
        f"'headline', 'summary' (1-2 sentences), 'source'. "
        f"No markdown. Pure JSON.",
        max_tokens=700,
    )
    r = _parse_json(text)
    return r if isinstance(r, list) and r else [
        {"headline": "TRADOC news unavailable",
         "summary": "Check tradoc.army.mil for current doctrine and training updates.",
         "source": ""}
    ]


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

    seafood   = d.get("seafood", {})
    saints    = d.get("saints", {})

    content_summary = f"""
MARKETS: DJI {price_dji:,.0f} ({pct_dji:+.1f}%), S&P {price_sp:,.0f} ({pct_sp:+.1f}%), WTI crude ${price_wti:.2f} ({pct_wti:+.1f}%)
EL PASO NEWS: {headlines(d.get('ep_news', []))}
EL PASO WEATHER (today): {weather_summary}
LSU SPORTS: {lsu_scores(d.get('lsu', {}))}
SAINTS RECORD: {saints.get('saints_record','—')} | Recent: {", ".join(f"{s.get('opponent','')} {s.get('result','')}" for s in saints.get('saints_recent',[])[:2]) or 'none'}
LOUISIANA SEAFOOD: Crawfish — {seafood.get('crawfish','')[:60]} | Shrimp — {seafood.get('shrimp','')[:60]}
LOUISIANA NEWS: {headlines(d.get('louisiana', []))}
LOUISIANA FESTIVALS (next 30 days): {festival_names(d.get('la_festivals', []))}
EL PASO WEEKEND EVENTS: {weekend_events(d.get('ep_weekend', []))}
DOD/ARMY NEWS: {headlines(d.get('dod_news', []))}
TRADOC NEWS: {headlines(d.get('tradoc_news', []))}
EXERCISE SCHEDULE: {headlines(d.get('exercise_schedule', []))}
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
- Saints commentary should reflect actual record and season status.
- Seafood comments should react to actual prices/availability — crawfish season is sacred.
- Weather comments should react to the actual El Paso forecast.
- Markets comments can react to actual direction (up/down/flat).
- Exercise schedule comments can reference the absurdity or significance of Army bureaucracy.
- TRADOC comments can gently mock doctrine-speak while respecting the mission.
- Occasionally make a Divorce Era cookbook joke if something fits.
- Return ONLY a valid JSON object with exactly these keys:
  markets, ep_news, weather, lsu, saints, seafood, louisiana, la_festivals, ep_weekend,
  ep_restaurants, dod_news, tradoc_news, exercise_schedule, budget_news, world_news,
  miltech, word_of_day, on_this_day, ingredient
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
          <div style="font-family:Georgia,serif;font-size:18px;font-weight:bold;
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
                font-size:15px;color:{CYPRESS};line-height:1.5;">
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
                     f'padding:2px 8px;font-size:13px;font-weight:bold;letter-spacing:.3px;'
                     f'margin-right:8px;border:1px solid {GOLD_LT};">{val}</span>')
        source = ""
        if s.get("source"):
            source = (f'<span style="font-size:13px;color:{GOLD};font-style:italic;'
                      f'margin-left:8px;">— {s["source"]}</span>')
        relevance = ""
        if s.get("relevance"):
            relevance = (f'<div style="font-size:14px;color:{GREEN};margin-top:5px;'
                         f'font-style:italic;padding-left:10px;border-left:2px solid {GOLD};">'
                         f'↳ {s["relevance"]}</div>')
        out += f"""
        <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #E8DFC8;">
          <div style="font-size:17px;font-weight:bold;color:{IRON};line-height:1.5;">
            {badge}{s.get('headline','')}{source}
          </div>
          <div style="font-size:15px;color:#5a5040;margin-top:6px;line-height:1.6;">
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
                     f'padding:2px 8px;font-size:13px;font-weight:bold;letter-spacing:.3px;'
                     f'margin-right:8px;border:1px solid {GOLD_LT};">{val}</span>')
        source = ""
        if s.get("source"):
            source = (f'<span style="font-size:13px;color:{GOLD};font-style:italic;'
                      f'margin-left:8px;">— {s["source"]}</span>')
        relevance = ""
        if s.get("relevance"):
            relevance = (f'<div style="font-size:14px;color:{GREEN};margin-top:5px;'
                         f'font-style:italic;padding-left:10px;border-left:2px solid {GOLD};">'
                         f'↳ {s["relevance"]}</div>')
        out += f"""
        <div style="margin-bottom:16px;padding-bottom:16px;
                    border-bottom:1px solid #E8DFC8;">
          <div style="font-size:17px;font-weight:bold;color:{IRON};line-height:1.5;">
            {badge}{s.get('headline','')}{source}
          </div>
          <div style="font-size:15px;color:#5a5040;margin-top:6px;line-height:1.6;">
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
            chg_str = (f'<div style="font-size:15px;color:{chg_color};font-weight:bold;">'
                       f'{arrow} {abs(chg):,.2f} ({pct:+.2f}%)</div>')
        br = f"border-right:1px solid {GOLD};" if border else ""
        return f"""
        <td style="width:33%;text-align:center;padding:16px 8px;vertical-align:top;{br}">
          <div style="font-size:12px;color:{GOLD_LT};text-transform:uppercase;
                      letter-spacing:1.2px;margin-bottom:4px;">{label}</div>
          <div style="font-size:24px;font-weight:bold;color:#FAF3E0;">{val}</div>
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
      <div style="text-align:center;font-size:13px;color:{GOLD};padding:6px;
                  border-top:1px solid rgba(200,164,0,.3);letter-spacing:.5px;">
        Most recent close &nbsp;·&nbsp; Yahoo Finance
      </div>
    </div>"""


def html_movies(theaters: list) -> str:
    if not theaters:
        return (f'<p style="color:{MOSS};font-size:15px;font-style:italic;">Showtime data not available. '
                f'Check <a href="https://www.fandango.com/el-paso_tx_movies" style="color:{GOLD};">Fandango</a>.</p>')
    out = ""
    for t in theaters:
        movies_html = ""
        for m in t.get("movies", []):
            times = " &nbsp;".join(
                f'<span style="background:{GREEN};color:{GOLD_LT};padding:2px 9px;'
                f'border-radius:12px;font-size:13px;font-weight:bold;">{tm}</span>'
                for tm in m.get("times", [])
            )
            rating = m.get("rating", "")
            badge = (f'<span style="background:{PURPLE};color:{GOLD_LT};padding:1px 7px;'
                     f'border-radius:3px;font-size:12px;margin-left:7px;font-weight:bold;">{rating}</span>'
                     if rating else "")
            movies_html += f"""
            <div style="margin-bottom:12px;padding-bottom:10px;border-bottom:1px dashed #E8DFC8;">
              <span style="font-size:16px;font-weight:bold;color:{IRON};">{m.get('title','')}</span>{badge}
              <div style="margin-top:5px;">{times}</div>
            </div>"""
        out += f"""
        <div style="margin-bottom:18px;padding:16px;background:{IVORY};
                    border-radius:6px;border-left:4px solid {GOLD};
                    border:1px solid #E8DFC8;border-left:4px solid {GOLD};">
          <div style="font-weight:bold;font-size:17px;color:{PURPLE};">{t.get('theater','')}</div>
          <div style="font-size:14px;color:{CYPRESS};margin-bottom:12px;font-style:italic;">
            📍 {t.get('address','')}
          </div>
          {movies_html}
        </div>"""
    return out


def html_weather(weather: dict) -> str:
    out = ""
    for city, forecast in weather.items():
        d = forecast.get("daily", {})
        out += (f'<div style="font-size:15px;font-weight:bold;color:{PURPLE};'
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
              <div style="font-size:13px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;letter-spacing:.5px;">{day}</div>
              <div style="font-size:24px;font-weight:bold;color:#FAF3E0;margin:5px 0;">
                {hi}° <span style="color:rgba(250,243,224,.5);font-size:16px;">/ {lo}°</span>
              </div>
              <div style="font-size:13px;color:#B8D4C0;">{cond}</div>
              <div style="font-size:13px;color:{GOLD};margin-top:3px;">💧 {pop}%</div>
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
          <td style="padding:9px 12px;font-weight:bold;font-size:15px;color:{PURPLE};">
            {s.get('sport','')}
          </td>
          <td style="padding:9px 12px;font-size:15px;color:{IRON};">
            vs {s.get('opponent','')}
          </td>
          <td style="padding:9px 12px;font-size:14px;color:{CYPRESS};font-style:italic;">
            {s.get('date','')}
          </td>
          <td style="padding:9px 12px;text-align:center;">
            <span style="background:{bg};color:{clr};font-weight:bold;
                         padding:3px 12px;border-radius:12px;font-size:15px;">
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
              <th style="padding:10px 12px;text-align:left;font-size:13px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">SPORT</th>
              <th style="padding:10px 12px;text-align:left;font-size:13px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">OPPONENT</th>
              <th style="padding:10px 12px;text-align:left;font-size:13px;
                         color:{GOLD_LT};letter-spacing:.8px;font-weight:bold;">DATE</th>
              <th style="padding:10px 12px;text-align:center;font-size:13px;
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
          <div style="font-style:italic;font-size:17px;color:#222;line-height:1.7;">
            &ldquo;{q.get('quote','')}&rdquo;
          </div>
          <div style="margin-top:10px;font-size:15px;font-weight:bold;color:#444;">
            — {q.get('author','')}
            <span style="font-weight:normal;font-style:italic;"> ({q.get('work','')})</span>
          </div>
          <div style="margin-top:6px;font-size:14px;color:#666;">{q.get('context','')}</div>
        </div>"""
    return out


def html_word(w: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{PURPLE} 0%,#2A0A50 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:12px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:8px;">⚜ &nbsp; {w.get('category','')}</div>
      <div style="font-size:28px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;">
        {w.get('word','')}
      </div>
      <div style="font-size:15px;color:rgba(200,180,120,.8);margin:4px 0 12px;font-style:italic;">
        {w.get('pronunciation','')}
      </div>
      <div style="font-size:16px;color:#D8C8A8;line-height:1.7;">{w.get('definition','')}</div>
    </div>"""


def html_on_this_day(e: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:12px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:6px;">⚜ &nbsp; {date.today().strftime('%B %d').upper()}</div>
      <div style="font-size:24px;font-weight:bold;color:{GOLD_LT};margin-bottom:4px;">
        {e.get('year','')}
      </div>
      <div style="font-size:17px;font-weight:bold;color:#FAF3E0;margin-bottom:10px;line-height:1.4;">
        {e.get('headline','')}
      </div>
      <div style="font-size:16px;color:#C8B890;line-height:1.7;border-top:1px solid rgba(200,164,0,.3);
                  padding-top:10px;">{e.get('story','')}</div>
    </div>"""


def html_miltech(stories: list) -> str:
    if not stories:
        return f'<p style="color:{MOSS};font-size:15px;font-style:italic;">No military tech stories retrieved today.</p>'
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
                         font-size:13px;font-weight:bold;letter-spacing:.3px;
                         border:1px solid {GOLD_LT};">{cat}</span>
          </div>
          <div style="font-size:17px;font-weight:bold;line-height:1.4;margin-bottom:6px;">
            <a href="{url}" style="color:{PURPLE};text-decoration:none;">{s.get('headline','')}</a>
          </div>
          <div style="font-size:15px;color:#5a5040;line-height:1.6;margin-bottom:6px;">
            {s.get('summary','')}
          </div>
          <div style="font-size:13px;">
            <a href="{url}" style="color:{GOLD};text-decoration:none;">🔗 {url}</a>
          </div>
        </div>"""
    return out


def html_louisiana_festivals(events: list) -> str:
    if not events:
        return f'<p style="color:{MOSS};font-size:15px;font-style:italic;">No festival listings found for the next 30 days.</p>'
    out = ""
    for e in events:
        url_html = ""
        if e.get("url"):
            url_html = (f'<a href="{e["url"]}" style="font-size:14px;color:{GOLD};'
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
              <div style="font-size:14px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;letter-spacing:.5px;">{date_top}</div>
              <div style="font-size:12px;color:rgba(212,175,55,.7);margin-top:2px;">{date_rest}</div>
            </div>
          </div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-size:17px;font-weight:bold;color:{PURPLE};">{e.get('name','')}</div>
            <div style="font-size:14px;color:{CYPRESS};margin:3px 0;font-style:italic;">
              📍 {e.get('location','')} &nbsp;·&nbsp; {e.get('dates','')}
            </div>
            <div style="font-size:15px;color:#5a5040;margin-top:5px;line-height:1.5;">
              {e.get('description','')}
            </div>
            <div style="margin-top:7px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_el_paso_weekend(events: list) -> str:
    if not events:
        return f'<p style="color:{MOSS};font-size:15px;font-style:italic;">No weekend listings found.</p>'
    out = ""
    for e in events:
        url_html = ""
        if e.get("url"):
            url_html = (f'<a href="{e["url"]}" style="font-size:14px;color:{GOLD};'
                        f'font-weight:bold;text-decoration:none;">Details →</a>')
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;
                    display:table;width:100%;box-sizing:border-box;">
          <div style="display:table-cell;width:78px;vertical-align:top;padding-right:14px;">
            <div style="background:linear-gradient(135deg,{GREEN} 0%,#1A3D2E 100%);
                        border-radius:6px;padding:8px 4px;text-align:center;
                        border:1px solid {GOLD};">
              <div style="font-size:12px;font-weight:bold;color:{GOLD_LT};
                          text-transform:uppercase;line-height:1.4;letter-spacing:.3px;">
                {e.get('when','')}
              </div>
            </div>
          </div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-size:17px;font-weight:bold;color:{PURPLE};">{e.get('name','')}</div>
            <div style="font-size:14px;color:{CYPRESS};margin:3px 0;font-style:italic;">
              📍 {e.get('venue','')}
            </div>
            <div style="font-size:15px;color:#5a5040;margin-top:5px;line-height:1.5;">
              {e.get('description','')}
            </div>
            <div style="margin-top:7px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_ep_restaurants(items: list) -> str:
    if not items:
        return f'<p style="color:{MOSS};font-size:15px;font-style:italic;">No restaurant news found.</p>'

    STATUS_COLORS = {
        "New Opening": (f"linear-gradient(135deg,{GREEN} 0%,#1A3D2E 100%)", GOLD_LT),
        "Closed":      (f"linear-gradient(135deg,#8B1A00 0%,#4A0000 100%)", "#FFD0C0"),
        "New Menu":    (f"linear-gradient(135deg,{PURPLE} 0%,#2A0A50 100%)", GOLD_LT),
        "Review":      (f"linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%)", GOLD_LT),
        "Food Truck":  (f"linear-gradient(135deg,{MOSS} 0%,#2A3A10 100%)", GOLD_LT),
    }
    out = ""
    for item in items:
        status = item.get("status", "News")
        bg, fg = STATUS_COLORS.get(status, (f"linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%)", GOLD_LT))
        url_html = ""
        if item.get("url"):
            url_html = (f'<a href="{item["url"]}" style="font-size:14px;color:{GOLD};'
                        f'font-weight:bold;text-decoration:none;">More info ⚜</a>')
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;
                    display:table;width:100%;box-sizing:border-box;">
          <div style="display:table-cell;width:84px;vertical-align:top;padding-right:14px;">
            <div style="background:{bg};border-radius:6px;padding:8px 4px;
                        text-align:center;border:1px solid {GOLD};">
              <div style="font-size:11px;font-weight:bold;color:{fg};
                          text-transform:uppercase;line-height:1.4;letter-spacing:.3px;">
                {status}
              </div>
            </div>
          </div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-size:17px;font-weight:bold;color:{PURPLE};">{item.get('name','')}</div>
            <div style="font-size:14px;color:{CYPRESS};margin:3px 0;font-style:italic;">
              📍 {item.get('location','')}
            </div>
            <div style="font-size:15px;color:#5a5040;margin-top:5px;line-height:1.5;">
              {item.get('description','')}
            </div>
            <div style="margin-top:7px;">{url_html}</div>
          </div>
        </div>"""
    return out


def html_seafood(s: dict) -> str:
    items = [
        ("🦞", "Crawfish",  s.get("crawfish", "—")),
        ("🦐", "Shrimp",    s.get("shrimp",   "—")),
        ("🦪", "Oysters",   s.get("oysters",  "—")),
        ("🦀", "Blue Crab", s.get("crab",     "—")),
    ]
    rows = ""
    for emoji, label, note in items:
        rows += f"""
        <tr style="border-bottom:1px solid #E8DFC8;">
          <td style="padding:10px 12px;width:110px;vertical-align:top;">
            <span style="font-size:20px;">{emoji}</span>
            <span style="font-size:14px;font-weight:bold;color:{PURPLE};
                         margin-left:6px;">{label}</span>
          </td>
          <td style="padding:10px 12px;font-size:15px;color:#5a5040;
                     line-height:1.5;vertical-align:top;">{note}</td>
        </tr>"""
    note_bar = ""
    if s.get("note"):
        note_bar = f"""
        <div style="background:linear-gradient(90deg,{GREEN},#1A3D2E);
                    padding:10px 14px;margin-top:2px;border-radius:0 0 6px 6px;">
          <span style="font-size:14px;font-style:italic;color:{GOLD_LT};">
            ⚜ {s['note']}
          </span>
        </div>"""
    return f"""
    <div style="border:1px solid {GOLD};border-radius:8px;overflow:hidden;margin-bottom:8px;">
      <div style="background:linear-gradient(135deg,{GREEN} 0%,#1A3D2E 100%);
                  padding:8px 14px;">
        <span style="font-size:13px;font-weight:bold;color:{GOLD_LT};
                     text-transform:uppercase;letter-spacing:.8px;">
          ⚜ Louisiana Gulf Seafood Market Report
        </span>
      </div>
      <table style="width:100%;border-collapse:collapse;background:{IVORY};">
        {rows}
      </table>
      {note_bar}
    </div>"""


def html_saints(data: dict) -> str:
    record = data.get("saints_record", "—")
    saints_games  = data.get("saints_recent", [])
    pelicans_games = data.get("pelicans_recent", [])
    stories = data.get("stories", [])

    def game_rows(games, team_color):
        out = ""
        for g in games:
            w   = str(g.get("result","")).upper().startswith("W")
            bg  = "#E0F2E9" if w else "#FFE8E0"
            clr = "#1A6B35" if w else "#8B1A00"
            out += f"""
            <tr style="border-bottom:1px solid #E8DFC8;">
              <td style="padding:8px 12px;font-size:15px;color:{IRON};">
                vs {g.get('opponent','')}
              </td>
              <td style="padding:8px 12px;font-size:13px;color:{CYPRESS};font-style:italic;">
                {g.get('date','')}
              </td>
              <td style="padding:8px 12px;text-align:center;">
                <span style="background:{bg};color:{clr};font-weight:bold;
                             padding:3px 12px;border-radius:12px;font-size:14px;">
                  {g.get('result','')}
                </span>
              </td>
            </tr>"""
        return out

    saints_html = ""
    if saints_games:
        saints_html = f"""
        <div style="font-size:13px;font-weight:bold;color:{PURPLE};margin:12px 0 6px;
                    text-transform:uppercase;letter-spacing:.5px;">
          ⚜ Saints &nbsp;·&nbsp;
          <span style="background:{PURPLE};color:{GOLD_LT};padding:2px 10px;
                       border-radius:12px;font-size:12px;">{record}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;background:{IVORY};
                      border-radius:6px;border:1px solid #E8DFC8;margin-bottom:12px;">
          {game_rows(saints_games, PURPLE)}
        </table>"""

    pelicans_html = ""
    if pelicans_games:
        pelicans_html = f"""
        <div style="font-size:13px;font-weight:bold;color:{GREEN};margin:12px 0 6px;
                    text-transform:uppercase;letter-spacing:.5px;">⚜ Pelicans</div>
        <table style="width:100%;border-collapse:collapse;background:{IVORY};
                      border-radius:6px;border:1px solid #E8DFC8;margin-bottom:12px;">
          {game_rows(pelicans_games, GREEN)}
        </table>"""

    return saints_html + pelicans_html + html_stories(stories)


def html_exercise_schedule(items: list) -> str:
    if not items:
        return (f'<p style="color:{MOSS};font-size:15px;font-style:italic;">'
                f'No exercise schedule data found. Check '
                f'<a href="https://www.army.mil/forscom" style="color:{GOLD};">FORSCOM</a> '
                f'for current rotations.</p>')
    out = ""
    for item in items:
        source = item.get("source","")
        src_badge = (f'<span style="font-size:13px;color:{GOLD};font-style:italic;">'
                     f'— {source}</span>' if source else "")
        out += f"""
        <div style="margin-bottom:14px;padding:14px;background:{IVORY};
                    border-radius:6px;border:1px solid #E8DFC8;
                    border-left:4px solid {PURPLE};">
          <div style="font-size:17px;font-weight:bold;color:{PURPLE};
                      line-height:1.4;margin-bottom:5px;">
            {item.get('headline','')} {src_badge}
          </div>
          <div style="font-size:15px;color:#5a5040;line-height:1.6;">
            {item.get('summary','')}
          </div>
        </div>"""
    return out


def html_tradoc_news(items: list) -> str:
    if not items:
        return (f'<p style="color:{MOSS};font-size:15px;font-style:italic;">'
                f'No TRADOC updates found. Check '
                f'<a href="https://www.tradoc.army.mil" style="color:{GOLD};">tradoc.army.mil</a>.</p>')
    return html_stories(items)


def html_crs(reports: list) -> str:
    if not reports:
        return (f'<p style="font-size:15px;color:{MOSS};font-style:italic;">No recent CRS reports retrieved. '
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
          <div style="font-size:16px;font-weight:bold;margin-bottom:4px;">
            <a href="{url}" style="color:{PURPLE};text-decoration:none;">
              {r.get('short_title', r.get('title',''))}
            </a>
          </div>
          <div style="font-size:14px;color:{CYPRESS};font-style:italic;margin-bottom:5px;">
            {r.get('title','')}
          </div>
          <div style="font-size:13px;color:#A09070;">{meta}
            &nbsp;·&nbsp; <a href="{url}" style="color:{GOLD};text-decoration:none;">🔗 View report</a>
          </div>
        </div>"""
    out += (f'<div style="text-align:right;font-size:14px;margin-top:6px;">'
            f'<a href="https://crsreports.congress.gov" style="color:{GOLD};">'
            f'Browse all CRS reports ⚜</a></div>')
    return out


def html_ingredient(ing: dict) -> str:
    return f"""
    <div style="background:linear-gradient(135deg,{CYPRESS} 0%,#3A1800 100%);
                border-radius:8px;padding:20px 22px;border:1px solid {GOLD};">
      <div style="font-size:12px;color:{GOLD};text-transform:uppercase;letter-spacing:1.5px;
                  margin-bottom:8px;">⚜ &nbsp; Clebeaux's Kitchen — {ing.get('season','')}</div>
      <div style="font-size:26px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;
                  margin-bottom:12px;">
        {ing.get('ingredient','')}
      </div>
      <div style="font-size:16px;color:#D8C0A0;line-height:1.8;font-style:italic;
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
        <div style="font-size:15px;font-weight:bold;color:{PURPLE};
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
    <div style="font-size:32px;font-weight:bold;color:{GOLD_LT};font-family:Georgia,serif;
                letter-spacing:2px;text-shadow:0 2px 8px rgba(0,0,0,.5);">
      ⚜ &nbsp; Daily Digest &nbsp; ⚜
    </div>
    <div style="color:rgba(212,175,55,.8);font-size:15px;margin-top:6px;letter-spacing:.8px;">
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

    {h2("🍽️", "El Paso — Restaurant & Bar News")}
    {html_snark(s.get("ep_restaurants",""))}
    {html_ep_restaurants(d["ep_restaurants"])}

    {h2("🎬", "Movies in El Paso — Today's Showtimes")}
    {html_movies(d["movies"])}

    {h2("🌤️", "3-Day Weather Forecast")}
    {html_snark(s.get("weather",""))}
    {html_weather(d["weather"])}

    {h2("🐯", "LSU Tigers Sports")}
    {html_snark(s.get("lsu",""))}
    {html_lsu(d["lsu"])}

    {h2("⚜", "New Orleans Saints & Pelicans")}
    {html_snark(s.get("saints",""))}
    {html_saints(d["saints"])}

    {h2("🌿", "Louisiana — NOLA · Baton Rouge · Northshore")}
    {html_snark(s.get("louisiana",""))}
    {html_stories(d["louisiana"], badge_key="area", badge_colors=AREA_COLORS)}

    {h2("🦞", "Louisiana Seafood Market Report")}
    {html_snark(s.get("seafood",""))}
    {html_seafood(d["seafood"])}

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

    {h2("🎯", "TRADOC — Doctrine & Training News")}
    {html_snark(s.get("tradoc_news",""))}
    {html_tradoc_news(d["tradoc_news"])}

    {h2("📅", "Exercise & Rotation Schedule")}
    {html_snark(s.get("exercise_schedule",""))}
    {html_exercise_schedule(d["exercise_schedule"])}

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
    <div style="color:rgba(212,175,55,.5);font-size:18px;letter-spacing:10px;margin-bottom:8px;">
      ⚜ ⚜ ⚜
    </div>
    <div style="font-size:13px;color:rgba(212,175,55,.6);letter-spacing:.8px;">
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
        ("📈 Markets",               "markets",           get_markets),
        ("⚜  Saints/Pelicans",       "saints",            get_saints_scores),
        ("🦞 LA seafood report",     "seafood",           get_louisiana_seafood),
        ("🎉 Louisiana festivals",   "la_festivals",      get_louisiana_festivals),
        ("🎯 TRADOC news",           "tradoc_news",       get_tradoc_news),
        ("📅 Exercise schedule",     "exercise_schedule", get_exercise_schedule),
        ("🌵 EP weekend events",     "ep_weekend",        get_el_paso_weekend),
        ("🍽️  EP restaurants",       "ep_restaurants",    get_ep_restaurants),
        ("📍 El Paso news",          "ep_news",           get_ep_news),
        ("🎬 Movies",                "movies",            get_movies_el_paso),
        ("🐯 LSU sports",            "lsu",               get_lsu_sports),
        ("🌿 Louisiana news",        "louisiana",         get_louisiana_news),
        ("📚 Philosopher quotes",    "quotes",            get_philosopher_quotes),
        ("🔤 Word of the day",       "word",              get_word_of_the_day),
        ("📅 On this day",           "on_this_day",       get_on_this_day),
        ("🪖 DoD/Army news",         "dod_news",          get_dod_army_news),
        ("💰 Defense budget",        "budget_news",       get_defense_budget_news),
        ("📋 CRS reports",           "crs",               get_crs_links),
        ("🌍 World news",            "world_news",        get_world_news),
        ("🛡️  Military tech links",  "miltech",           get_military_tech_links),
        ("🍳 Ingredient of the day", "ingredient",        get_ingredient_of_the_day),
    ]

    # Safe defaults for every key — build_email never crashes on missing key
    data = {
        "weather": {}, "other_news": {},
        "markets": {}, "saints": {}, "seafood": {}, "la_festivals": [],
        "tradoc_news": [], "exercise_schedule": [], "ep_weekend": [],
        "ep_restaurants": [], "ep_news": [], "movies": [], "lsu": {},
        "louisiana": [], "quotes": [], "word": {}, "on_this_day": {},
        "dod_news": [], "budget_news": [], "crs": [], "world_news": [],
        "miltech": [], "ingredient": {}, "snark": {},
    }

    # Weather (free API, no rate limit)
    print("🌤  Fetching weather...")
    for city, (lat, lon) in LOCATIONS.items():
        print(f"    → {city}")
        data["weather"][city] = get_weather(lat, lon)

    # Regional news (Claude calls — add delay after)
    print("📰 Fetching regional news...")
    data["other_news"] = {
        "Ellensburg, WA":  get_news("Ellensburg Washington local news", 2),
        "Pearl River, LA": get_news("Pearl River Louisiana Slidell Northshore local news", 2),
    }
    time.sleep(5)

    # All other sections — 5s pause after each Claude-based call
    for label, key, fn in steps:
        print(f"{label}...")
        data[key] = fn()
        time.sleep(5)  # breathing room between API calls

    print("😏 Generating snarky commentary...")
    data["snark"] = get_snarky_comments(data)

    print("✉️  Building and sending email...")
    send_email(build_email(data))
    print("✅ Done.")


if __name__ == "__main__":
    main()
