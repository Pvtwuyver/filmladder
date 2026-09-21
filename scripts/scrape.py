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

KANTTEKENING BIJ DE DAG-TIJDEN-GRID (toegevoegd t.b.v. de "vanavond"/"dit
weekend"-filters):
filmvandaag.nl toont per film een 7-daagse tijden-grid (Vandaag, Morgen,
gevolgd door de 5 eerstvolgende weekdagen bij naam). Dat is bevestigd via een
live paginabezoek, maar dat bezoek leverde alleen platte, geextraheerde
tekst op - geen ruwe HTML met tags/classes. Uit die platte tekst is NIET
betrouwbaar af te leiden welke speeltijd bij welke dag hoort zodra een film
niet op alle 7 dagen draait (lege dagcellen leveren geen tekst op en vallen
daardoor weg, waardoor de resterende tijden niet meer op hun oorspronkelijke
dag-positie staan). De functie `_find_day_grid_texts` hieronder werkt daarom
op de echte elementstructuur (BeautifulSoup-kinderen, met behoud van lege
cellen) in plaats van op platte tekst, maar WELKE elementen precies de
dag-grid vormen is een aanname (zie de docstring van die functie) en dus
ONGEVERIFIEERD. Controleer bij de eerste --debug run specifiek of de datums
bij de juiste speeltijden horen (vergelijk een paar films met de site zelf).
Als de aanname niet klopt, valt een film terug op ongedateerde tijden
("date": null) in plaats van foutieve datums - controleer dus ook of dat
vaker gebeurt dan verwacht.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; AmsBioscoopBot/1.0; "
    "+https://github.com/) AmsterdamCinemaTracker"
)

NOW_PLAYING_URL = "https://www.filmvandaag.nl/filmladder/stad/13-amsterdam"
UPCOMING_URL = "https://www.filmvandaag.nl/nieuwefilms"

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

# Aantal dagen dat filmvandaag.nl per film toont: Vandaag, Morgen, en 5
# opeenvolgende weekdagen bij naam.
DAY_COUNT = 7
WEEKDAY_NAMES_NL = [
    "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _dutch_weekday_name(d: date) -> str:
    return WEEKDAY_NAMES_NL[d.weekday()].capitalize()


def _expected_day_labels(base_date: date) -> list[str]:
    """Dag-labels zoals filmvandaag.nl ze toont, offset 0..6 t.o.v. base_date."""
    labels = ["Vandaag", "Morgen"]
    for offset in range(2, DAY_COUNT):
        labels.append(_dutch_weekday_name(base_date + timedelta(days=offset)))
    return labels


def _find_day_grid_texts(heading, expected_labels: list[str], debug: bool = False):
    """
    ONGEVERIFIEERD - zie de kanttekening bovenaan dit bestand.

    Zoekt, uitgaande van een filmtitel-kopelement, het element waarvan de
    (genormaliseerde) tekst begint met de volledige dag-labelreeks
    ("Vandaag Morgen Woensdag ... Zondag"), en neemt aan dat de
    kindelementen daarvan (of van de eerstvolgende sibling) de 7 dagcellen
    zijn - EEN cel per dag, inclusief lege cellen voor dagen zonder
    voorstelling, zodat de positie (index 0..6) behouden blijft.

    Retourneert een lijst van precies DAY_COUNT strings (index i = tekst van
    dag base_date+i, kan leeg zijn), of None als deze structuur niet is
    aangetroffen binnen de eerstvolgende elementen na de kop.
    """
    label_text = " ".join(expected_labels)
    for node in heading.find_all_next(limit=40):
        text = _normalize(node.get_text(" "))
        if not text.startswith(label_text):
            continue

        children = node.find_all(recursive=False)
        if len(children) == 2 * DAY_COUNT:
            # aanname: eerst 7 label-cellen, dan 7 tijd-cellen
            return [_normalize(c.get_text(" ")) for c in children[DAY_COUNT:]]
        if len(children) == DAY_COUNT:
            # aanname: labels en tijden zitten samen in dezelfde 7 cellen
            return [_normalize(c.get_text(" ")) for c in children]

        sibling = node.find_next_sibling()
        if sibling is not None:
            sib_children = sibling.find_all(recursive=False)
            if len(sib_children) == DAY_COUNT:
                # aanname: labels in dit element, tijden in de rij erna
                return [_normalize(c.get_text(" ")) for c in sib_children]

        if debug:
            print(
                "[debug]   dag-labels gevonden maar celstructuur wijkt af "
                f"({len(children)} kindelementen) - val terug op ongedateerde tijden",
                file=sys.stderr,
            )
        return None
    return None


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


def parse_now_playing(
    soup: BeautifulSoup, base_date: date, debug: bool = False
) -> list[dict]:
    """
    Loopt door alle kop- en tekstelementen in documentvolgorde. Elke keer dat
    een kop een bekende bioscoopnaam bevat, start een nieuwe sectie. Binnen
    een sectie wordt elke volgende kop als filmtitel beschouwd.

    Voor elke film wordt eerst geprobeerd de dag-tijden-grid te vinden (zie
    `_find_day_grid_texts` - ONGEVERIFIEERD, zie kanttekening bovenaan dit
    bestand) zodat speeltijden een datum (base_date + 0..6 dagen) krijgen.
    Lukt dat niet, dan valt de film terug op de oude aanpak: alle HH:MM-
    patronen in de tekst NA de titelkop worden als speeltijden zonder datum
    ("date": null) beschouwd. Rating en genre worden op dezelfde manier als
    voorheen uit de tekst na de titel gehaald.
    """
    cinemas: list[dict] = []
    current_cinema: dict | None = None
    current_movie: dict | None = None
    expected_labels = _expected_day_labels(base_date)

    body = soup.body or soup
    elements = body.find_all(
        ["h1", "h2", "h3", "h4", "h5", "p", "span", "div", "li"], recursive=True
    )

    # Voorkom dubbel werk door geneste elementen: pak alleen elementen die
    # zelf geen van de gezochte tags als kind hebben (d.w.z. "leaf-ish").
    # We bewaren ook het element zelf (niet alleen de tekst), zodat we bij
    # filmtitel-koppen de dag-grid kunnen opzoeken in de echte structuur.
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
        seen_text_blocks.append((el.name, text, el))

    for tag_name, text, tag in seen_text_blocks:
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

            grid_texts = _find_day_grid_texts(tag, expected_labels, debug=debug)
            if grid_texts is not None:
                current_movie["_dated"] = True
                total = 0
                for offset, cell_text in enumerate(grid_texts):
                    d = base_date + timedelta(days=offset)
                    for h, m in TIME_RE.findall(cell_text):
                        entry = {"date": d.isoformat(), "time": f"{int(h):02d}:{m}"}
                        if entry not in current_movie["showtimes"]:
                            current_movie["showtimes"].append(entry)
                            total += 1
                if debug:
                    print(
                        f"[debug]   dag-grid gevonden voor '{title}': "
                        f"{total} tijden over {DAY_COUNT} dagen",
                        file=sys.stderr,
                    )
            else:
                current_movie["_dated"] = False
                if debug:
                    print(
                        f"[debug]   GEEN dag-grid gevonden voor '{title}', "
                        "val terug op ongedateerde tijden",
                        file=sys.stderr,
                    )

            current_cinema["movies"].append(current_movie)
            continue

        # Geen kop: mogelijk metadata of speeltijden bij de huidige film.
        if current_movie is None:
            continue

        times = TIME_RE.findall(text)
        if times:
            if not current_movie["_dated"]:
                for h, m in times:
                    entry = {"date": None, "time": f"{int(h):02d}:{m}"}
                    if entry not in current_movie["showtimes"]:
                        current_movie["showtimes"].append(entry)
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

    # Ruim bioscopen zonder films op (mislukte matches) en verwijder het
    # interne "_dated"-werkveld uit de output.
    cinemas = [c for c in cinemas if c["movies"]]
    for c in cinemas:
        for m in c["movies"]:
            m.pop("_dated", None)

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

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    base_date = now_dt.date()

    try:
        soup = fetch(NOW_PLAYING_URL)
        cinemas = parse_now_playing(soup, base_date, debug=args.debug)
    except Exception as exc:  # noqa: BLE001
        print(f"FOUT bij ophalen/parsen 'nu draait': {exc}", file=sys.stderr)
        cinemas = []

    write_json(
        NOW_PLAYING_FILE,
        {
            "schema_version": 2,
            "generated_at": now,
            "source": NOW_PLAYING_URL,
            "cinemas": cinemas,
        },
    )
    print(f"now_playing.json geschreven: {len(cinemas)} bioscopen")

    if not args.skip_upcoming:
        try:
            soup2 = fetch(UPCOMING_URL)
            films = parse_upcoming(soup2, debug=args.debug)
        except Exception as exc:  # noqa: BLE001
            print(f"FOUT bij ophalen/parsen 'binnenkort': {exc}", file=sys.stderr)
            films = []

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
