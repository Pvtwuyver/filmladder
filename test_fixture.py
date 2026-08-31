"""
Lokale smoke test met synthetische HTML (geen netwerktoegang nodig).
Test niet of de ECHTE site deze structuur heeft, maar wel dat de parselogica
zelf correct werkt gegeven een pagina die aan de aanname voldoet.
Run: python scripts/test_fixture.py

Handig om te draaien nadat je parse_now_playing/parse_upcoming hebt
aangepast, om snel te checken dat je niets hebt gebroken.
"""
from bs4 import BeautifulSoup
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape import parse_now_playing, parse_upcoming  # noqa: E402

NOW_PLAYING_HTML = """
<html><body>
<h2>Pathé Amsterdam Noord</h2>
<p>Buikslotermeerplein 2003 Amsterdam</p>
<h3>The Odyssey (2026)</h3>
<p>avontuur / fantasy van Christopher Nolan</p>
<p>8,4</p>
<div>Vandaag 11:00 14:10 18:00 19:30</div>

<h3>Spider-Man: Brand New Day (2026)</h3>
<p>actie / sciencefiction</p>
<p>8,0</p>
<div>11:00 13:00 14:20</div>

<h2>Kriterion</h2>
<h3>A Sad and Beautiful World (2025)</h3>
<p>komedie / drama</p>
<p>7,5</p>
<div>19:00</div>
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


def main():
    soup1 = BeautifulSoup(NOW_PLAYING_HTML, "lxml")
    cinemas = parse_now_playing(soup1, debug=True)
    assert len(cinemas) == 2, f"verwacht 2 bioscopen, kreeg {len(cinemas)}"
    assert cinemas[0]["name"] == "Pathé Amsterdam Noord"
    assert len(cinemas[0]["movies"]) == 2
    assert cinemas[0]["movies"][0]["title"] == "The Odyssey"
    assert cinemas[0]["movies"][0]["year"] == 2026
    assert "11:00" in cinemas[0]["movies"][0]["showtimes"]
    assert cinemas[1]["name"] == "Kriterion"
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
