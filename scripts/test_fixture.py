"""
Lokale smoke test met synthetische HTML (geen netwerktoegang nodig).
Test niet of de ECHTE site deze structuur heeft, maar wel dat de parselogica
zelf correct werkt gegeven een pagina die aan de aanname voldoet - inclusief
de aanname over de dag-tijden-grid (zie de kanttekening bovenaan scrape.py:
die aanname is ONGEVERIFIEERD tegen de echte site).
Run: python scripts/test_fixture.py

Handig om te draaien nadat je parse_now_playing/parse_upcoming hebt
aangepast, om snel te checken dat je niets hebt gebroken.
"""
from datetime import date, timedelta

from bs4 import BeautifulSoup
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape import parse_now_playing, parse_upcoming  # noqa: E402

# Referentiedatum voor de fixture: een vaste maandag, zodat de verwachte
# dag-labels ("Vandaag Morgen Woensdag Donderdag Vrijdag Zaterdag Zondag")
# reproduceerbaar zijn onafhankelijk van de dag waarop de test draait.
BASE_DATE = date(2026, 9, 21)  # een maandag

# Structuurvariant A: 7 label-cellen gevolgd door 7 tijd-cellen (14 kinderen
# in de dag-grid-container). The Odyssey draait alle 7 dagen; Spider-Man
# alleen vandaag en woensdag (met lege cellen ertussen, zodat de positie
# van de niet-lege cellen behouden blijft).
NOW_PLAYING_HTML = f"""
<html><body>
<h2>Pathé Amsterdam Noord</h2>
<p>Buikslotermeerplein 2003 Amsterdam</p>

<h3>The Odyssey (2026)</h3>
<p>avontuur / fantasy van Christopher Nolan</p>
<p>8,4</p>
<div class="day-grid">
  <div>Vandaag</div><div>Morgen</div><div>Woensdag</div><div>Donderdag</div>
  <div>Vrijdag</div><div>Zaterdag</div><div>Zondag</div>
  <div>11:00 14:10</div><div>11:00</div><div>13:00 16:45</div><div></div>
  <div>18:00</div><div>12:00 20:30</div><div>19:30</div>
</div>

<h3>Spider-Man: Brand New Day (2026)</h3>
<p>actie / sciencefiction</p>
<p>8,0</p>
<div class="day-grid">
  <div>Vandaag</div><div>Morgen</div><div>Woensdag</div><div>Donderdag</div>
  <div>Vrijdag</div><div>Zaterdag</div><div>Zondag</div>
  <div>11:00 13:00</div><div></div><div>14:20</div><div></div>
  <div></div><div></div><div></div>
</div>

<h2>Kriterion</h2>
<h3>A Sad and Beautiful World (2025)</h3>
<p>komedie / drama</p>
<p>7,5</p>
<div>Vandaag 19:00</div>
</body></html>
"""

UPCOMING_HTML = """
<html><body>
<h2>Wicked: For Good (2026)</h2>
<p>Releasedatum: 20 nov 2026</p>

<h2>Nog een film (2026)</h2>
<p>Releasedatum: 3 dec. 2026</p>
</body></html>
"""


def _showtimes_by_date(movie):
    by_date = {}
    for s in movie["showtimes"]:
        by_date.setdefault(s["date"], []).append(s["time"])
    return by_date


def main():
    soup1 = BeautifulSoup(NOW_PLAYING_HTML, "lxml")
    cinemas = parse_now_playing(soup1, BASE_DATE, debug=True)
    assert len(cinemas) == 2, f"verwacht 2 bioscopen, kreeg {len(cinemas)}"
    assert cinemas[0]["name"] == "Pathé Amsterdam Noord"
    assert len(cinemas[0]["movies"]) == 2
    odyssey = cinemas[0]["movies"][0]
    assert odyssey["title"] == "The Odyssey"
    assert odyssey["year"] == 2026

    # Dag-grid-variant: iedere speeltijd moet de juiste datum hebben
    # (base_date + kolomindex), inclusief de dag met een lege cel.
    by_date = _showtimes_by_date(odyssey)
    assert by_date[(BASE_DATE + timedelta(days=0)).isoformat()] == ["11:00", "14:10"]
    assert by_date[(BASE_DATE + timedelta(days=1)).isoformat()] == ["11:00"]
    assert by_date[(BASE_DATE + timedelta(days=2)).isoformat()] == ["13:00", "16:45"]
    assert (BASE_DATE + timedelta(days=3)).isoformat() not in by_date, (
        "donderdag had een lege cel en mag dus geen tijden opleveren"
    )
    assert by_date[(BASE_DATE + timedelta(days=4)).isoformat()] == ["18:00"]
    assert by_date[(BASE_DATE + timedelta(days=5)).isoformat()] == ["12:00", "20:30"]
    assert by_date[(BASE_DATE + timedelta(days=6)).isoformat()] == ["19:30"]

    spiderman = cinemas[0]["movies"][1]
    by_date_sm = _showtimes_by_date(spiderman)
    assert by_date_sm[(BASE_DATE + timedelta(days=0)).isoformat()] == ["11:00", "13:00"]
    assert by_date_sm[(BASE_DATE + timedelta(days=2)).isoformat()] == ["14:20"]
    assert len(by_date_sm) == 2, "alleen vandaag en woensdag hebben tijden"

    assert cinemas[1]["name"] == "Kriterion"
    # Terugvalscenario: geen herkenbare dag-grid -> ongedateerde tijden i.p.v.
    # foutieve datums.
    fallback_movie = cinemas[1]["movies"][0]
    assert fallback_movie["showtimes"] == [{"date": None, "time": "19:00"}], (
        f"verwachtte een ongedateerde tijd bij ontbrekende dag-grid, kreeg "
        f"{fallback_movie['showtimes']}"
    )
    print("parse_now_playing: OK ->", cinemas)

    soup2 = BeautifulSoup(UPCOMING_HTML, "lxml")
    films = parse_upcoming(soup2, debug=True)
    assert len(films) == 2, f"verwacht 2 films, kreeg {len(films)}"
    assert films[0]["title"] == "Wicked: For Good"
    assert films[0]["release_date"] == "2026-11-20", films[0]["release_date"]
    print("parse_upcoming: OK ->", films)

    print("\nAlle fixture-tests geslaagd.")


if __name__ == "__main__":
    main()
