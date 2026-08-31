
#!/usr/bin/env python3
"""
Scraper voor Amsterdamse bioscoopprogrammering.
 
Haalt twee databronnen op van filmvandaag.nl:
  1. "Nu draait"   -> https://www.filmvandaag.nl/filmladder/stad/13-amsterdam
     Overzicht per Amsterdamse bioscoop (Pathe-vestigingen EN filmhuizen
     zoals EYE, Kriterion, FilmHallen, Studio K, etc.) met speeltijden.
  2. "Binnenkort"  -> https://www.filmvandaag.nl/nieuwefilms
     Landelijk overzicht van nieuwe/aankomende releases met releasedatum.
 
BELANGRIJK - lees dit voor je het script draait:
Dit script is geschreven zonder dat de ruwe HTML-broncode van de doelpagina's
kon worden geinspecteerd (de omgeving waarin dit script is gebouwd heeft geen
netwerktoegang tot filmvandaag.nl). De parselogica is daarom bewust NIET
gebaseerd op exacte CSS class-namen (die zijn geraden en dus onbetrouwbaar),
maar op de structuur van de pagina: kop-elementen (h1-h5) worden gelezen in
documentvolgorde, bioscoopnamen worden herkend aan een vaste lijst bekende
namen, en films/speeltijden worden er met tekstpatronen (regex) uitgehaald.
 
Dat maakt het script robuuster tegen onbekende class-namen, maar er is een
reele kans dat de site-structuur op punten afwijkt van de aanname hieronder.
CONTROLEER DUS DE EERSTE RUN (via de GitHub Actions-log, of lokaal met
`python scripts/scrape.py --debug`) en pas zo nodig de functies
`parse_now_playing` / `parse_upcoming` aan. Zet dit niet blind op een cron
zonder de eerste output te hebben gecontroleerd.
"""
 
from __future__ import annotations
 
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
 
import requests
from bs4 import BeautifulSoup
 
USER_AGENT = (
    "Mozilla/5.0 (compatible; AmsBioscoopBot/1.0; "
    "+https://github.com/) AmsterdamCinemaTracker"
)
 
NOW_PLAYING_URL = "https://www.filmvandaag.nl/filmladder/stad/13-amsterdam"
UPCOMING_URL = "https://www.filmvandaag.nl/nieuwefilms"
 
# Posters via TMDB (The Movie Database). Optioneel: als de omgevingsvariabele
# TMDB_API_KEY niet gezet is, wordt poster_url overal None en werkt de rest
# van het script gewoon door. Een gratis API-key vraag je aan op
# https://www.themoviedb.org/settings/api (account aanmaken -> Settings ->
# API -> "API Read Access Token" of de "API Key (v3 auth)").
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
 
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NOW_PLAYING_FILE = DATA_DIR / "now_playing.json"
UPCOMING_FILE = DATA_DIR / "upcoming.json"
 
# Bekende Amsterdamse bioscopen/filmhuizen. Wordt gebruikt om koppen in de
# pagina te herkennen als "dit is een nieuwe bioscoop-sectie" i.p.v. als
# filmtitel. Vul aan als filmvandaag.nl een bioscoop toevoegt/hernoemt.
KNOWN_CINEMAS = [
    "Pathe Amsterdam Noord",
    "Pathe Arena",
    "Pathe City",
    "Pathe de Munt",
    "Pathe Tuschinski",
    "Cinecenter",
    "Cinema De Balie",
    "Cinema De Vlugt",
    "Cinema The Pulse",
    "De FilmHallen",
    "De Uitkijk",
    "EYE",
    "FC Hyena",
    "Filmhuis Cavia",
    "Het Documentaire Paviljoen",
    "Het Ketelhuis",
    "Kriterion",
    "LAB111",
    "Melkweg Cinema",
    "Rialto De Pijp",
    "Rialto VU",
    "Studio K",
    "Studio/K",
    "The Movies",
    "Vue Amsterdam",
]
 
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
YEAR_RE = re.compile(r"\((\d{4})\)")
RATING_RE = re.compile(r"\b(\d[.,]\d)\b")
 
 
def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
 
 
def _looks_like_cinema_heading(text: str) -> str | None:
    """Return the canonical cinema name if `text` matches a known cinema."""
    norm = _normalize(text).lower().replace("é", "e")
    for name in KNOWN_CINEMAS:
        if name.lower().replace("é", "e") in norm:
            return name.replace("Pathe", "Pathé")
    return None
 
 
def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")
 
 
def parse_now_playing(soup: BeautifulSoup, debug: bool = False) -> list[dict]:
    """
    Loopt door alle kop- en tekstelementen in documentvolgorde. Elke keer dat
    een kop een bekende bioscoopnaam bevat, start een nieuwe sectie. Binnen
    een sectie wordt elke volgende kop als filmtitel beschouwd; de tekst
    ERNA (tot de volgende kop) wordt doorzocht op jaartal, rating en
    speeltijden (HH:MM patronen).
    """
    cinemas: list[dict] = []
    current_cinema: dict | None = None
    current_movie: dict | None = None
 
    body = soup.body or soup
    elements = body.find_all(
        ["h1", "h2", "h3", "h4", "h5", "p", "span", "div", "li"], recursive=True
    )
 
    # Voorkom dubbel werk door geneste elementen: pak alleen elementen die
    # zelf geen van de gezochte tags als kind hebben (d.w.z. "leaf-ish").
    seen_text_blocks = []
    for el in elements:
        if el.find(["h1", "h2", "h3", "h4", "h5"]):
            # container met koppen erin: sla de container zelf over,
            # de koppen worden los bezocht.
            if el.name not in ("h1", "h2", "h3", "h4", "h5"):
                continue
        text = _normalize(el.get_text(" "))
        if not text:
            continue
        seen_text_blocks.append((el.name, text))
 
    for tag_name, text in seen_text_blocks:
        is_heading = tag_name in ("h1", "h2", "h3", "h4", "h5")
 
        if is_heading:
            cinema_name = _looks_like_cinema_heading(text)
            if cinema_name:
                current_cinema = {"name": cinema_name, "movies": []}
                cinemas.append(current_cinema)
                current_movie = None
                continue
 
            if current_cinema is None:
                # Nog geen bioscoop-sectie gevonden, kop negeren.
                continue
 
            # Anders: beschouw als filmtitel.
            year_match = YEAR_RE.search(text)
            title = YEAR_RE.sub("", text).strip(" -")
            if len(title) < 2:
                continue
            current_movie = {
                "title": title,
                "year": int(year_match.group(1)) if year_match else None,
                "genre": None,
                "rating": None,
                "showtimes": [],
            }
            current_cinema["movies"].append(current_movie)
            continue
 
        # Geen kop: mogelijk metadata of speeltijden bij de huidige film.
        if current_movie is None:
            continue
 
        times = TIME_RE.findall(text)
        if times:
            for h, m in times:
                t = f"{int(h):02d}:{m}"
                if t not in current_movie["showtimes"]:
                    current_movie["showtimes"].append(t)
            continue
 
        rating_match = RATING_RE.search(text)
        if rating_match and current_movie["rating"] is None:
            try:
                current_movie["rating"] = float(rating_match.group(1).replace(",", "."))
            except ValueError:
                pass
 
        if current_movie["genre"] is None and (
            "/" in text or any(g in text.lower() for g in ["genre", "actie", "drama", "komedie"])
        ):
            current_movie["genre"] = text
 
    # Ruim bioscopen zonder films op (mislukte matches).
    cinemas = [c for c in cinemas if c["movies"]]
 
    if debug:
        print(f"[debug] {len(cinemas)} bioscoop-secties gevonden", file=sys.stderr)
        for c in cinemas:
            print(f"[debug]   {c['name']}: {len(c['movies'])} films", file=sys.stderr)
 
    return cinemas
 
 
def parse_upcoming(soup: BeautifulSoup, debug: bool = False) -> list[dict]:
    """
    Best-effort parse van de 'nieuwe films' overzichtspagina. Verwacht per
    film een kop (titel + jaartal) gevolgd door tekst met eventueel een
    releasedatum. Datumherkenning is bewust losjes; onherkende datums blijven
    None zodat de front-end ze gewoon zonder datum toont i.p.v. fout te gaan.
    """
    months = {
        "jan": 1, "feb": 2, "mrt": 3, "maart": 3, "apr": 4, "mei": 5, "jun": 6,
        "juni": 6, "jul": 7, "juli": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10,
        "nov": 11, "dec": 12,
    }
    date_re = re.compile(
        r"(\d{1,2})\s+(" + "|".join(months.keys()) + r")\.?\s*(\d{4})?", re.IGNORECASE
    )
 
    films: list[dict] = []
    body = soup.body or soup
    headings = body.find_all(["h2", "h3", "h4"])
 
    for h in headings:
        text = _normalize(h.get_text(" "))
        if not text or len(text) < 2:
            continue
        year_match = YEAR_RE.search(text)
        title = YEAR_RE.sub("", text).strip(" -")
        if len(title) < 2:
            continue
 
        # Zoek releasedatum in de tekst na de kop (volgende paar siblings).
        release_date = None
        node = h.find_next_sibling()
        hops = 0
        while node is not None and hops < 4:
            sib_text = _normalize(node.get_text(" ")) if hasattr(node, "get_text") else ""
            m = date_re.search(sib_text)
            if m:
                day = int(m.group(1))
                month = months[m.group(2).lower()]
                year = int(m.group(3)) if m.group(3) else datetime.now().year
                try:
                    release_date = f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    pass
                break
            hops += 1
            node = node.find_next_sibling()
 
        films.append(
            {
                "title": title,
                "year": int(year_match.group(1)) if year_match else None,
                "release_date": release_date,
            }
        )
 
    if debug:
        print(f"[debug] {len(films)} aankomende films gevonden", file=sys.stderr)
 
    return films
 
 
def find_poster_url(title: str, year: int | None, cache: dict) -> str | None:
    """
    Zoekt de posterafbeelding van een film op via de TMDB-zoek-API. Resultaten
    worden gecachet per (titel, jaar) binnen deze run, zodat een film die in
    meerdere bioscopen draait maar 1x wordt opgezocht. Geeft None terug als er
    geen API-key is ingesteld, niets gevonden wordt, of de opzoeking faalt --
    dit mag de rest van het script nooit laten stoppen.
    """
    if not TMDB_API_KEY:
        return None
 
    cache_key = (title.strip().lower(), year)
    if cache_key in cache:
        return cache[cache_key]
 
    poster_url = None
    try:
        params = {"api_key": TMDB_API_KEY, "query": title, "language": "nl-NL"}
        if year:
            params["year"] = year
        resp = requests.get(TMDB_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results and year:
            # Val terug op een zoekopdracht zonder jaartal (releasejaar kan
            # net anders zijn geregistreerd dan op filmvandaag.nl).
            params.pop("year", None)
            resp = requests.get(TMDB_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results") or []
        if results:
            poster_path = results[0].get("poster_path")
            if poster_path:
                poster_url = TMDB_IMAGE_BASE + poster_path
    except Exception as exc:  # noqa: BLE001
        print(f"TMDB-opzoeking mislukt voor '{title}' ({year}): {exc}", file=sys.stderr)
 
    cache[cache_key] = poster_url
    return poster_url
 
 
def enrich_with_posters(cinemas: list[dict], films: list[dict], debug: bool = False) -> None:
    """Vult poster_url in op alle films in `cinemas` en `films`, in-place."""
    if not TMDB_API_KEY:
        if debug:
            print(
                "[debug] TMDB_API_KEY niet gezet, posters worden overgeslagen",
                file=sys.stderr,
            )
        for cinema in cinemas:
            for movie in cinema["movies"]:
                movie["poster_url"] = None
        for film in films:
            film["poster_url"] = None
        return
 
    cache: dict = {}
    lookups = 0
    for cinema in cinemas:
        for movie in cinema["movies"]:
            movie["poster_url"] = find_poster_url(movie["title"], movie["year"], cache)
            lookups += 1
    for film in films:
        film["poster_url"] = find_poster_url(film["title"], film["year"], cache)
        lookups += 1
 
    if debug:
        found = sum(1 for v in cache.values() if v)
        print(
            f"[debug] {lookups} films verwerkt, {len(cache)} unieke opzoekingen, "
            f"{found} posters gevonden",
            file=sys.stderr,
        )
 
 
def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
 
 
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="Print voortgang naar stderr")
    parser.add_argument(
        "--skip-upcoming", action="store_true", help="Alleen 'nu draait' verversen"
    )
    args = parser.parse_args()
 
    now = datetime.now(timezone.utc).isoformat()
 
    try:
        soup = fetch(NOW_PLAYING_URL)
        cinemas = parse_now_playing(soup, debug=args.debug)
    except Exception as exc:  # noqa: BLE001
        print(f"FOUT bij ophalen/parsen 'nu draait': {exc}", file=sys.stderr)
        cinemas = []
 
    films: list[dict] = []
    if not args.skip_upcoming:
        try:
            soup2 = fetch(UPCOMING_URL)
            films = parse_upcoming(soup2, debug=args.debug)
        except Exception as exc:  # noqa: BLE001
            print(f"FOUT bij ophalen/parsen 'binnenkort': {exc}", file=sys.stderr)
            films = []
 
    # Posters ophalen (indien TMDB_API_KEY gezet) voor zowel 'nu draait' als
    # 'binnenkort', voordat we wegschrijven.
    enrich_with_posters(cinemas, films, debug=args.debug)
 
    write_json(
        NOW_PLAYING_FILE,
        {"generated_at": now, "source": NOW_PLAYING_URL, "cinemas": cinemas},
    )
    print(f"now_playing.json geschreven: {len(cinemas)} bioscopen")
 
    if not args.skip_upcoming:
        write_json(
            UPCOMING_FILE,
            {"generated_at": now, "source": UPCOMING_URL, "films": films},
        )
        print(f"upcoming.json geschreven: {len(films)} films")
 
    if not cinemas:
        print(
            "WAARSCHUWING: geen bioscopen gevonden. De paginastructuur wijkt "
            "waarschijnlijk af van de aanname in parse_now_playing(). "
            "Controleer de website handmatig en pas het script aan.",
            file=sys.stderr,
        )
        return 1
 
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())
 
