# Amsterdamse bioscoopagenda

Statische pagina met films die nu draaien en binnenkort uitkomen in de
bioscopen en filmhuizen van Amsterdam (Pathé-vestigingen en filmhuizen zoals
EYE, Kriterion, FilmHallen, Studio K). Data wordt dagelijks automatisch
ververst via GitHub Actions en gehost via GitHub Pages — geen eigen server
nodig. Op het tabblad "Nu draait" kun je filteren op titel, bioscoop, en op
periode ("Alle dagen" / "Vanavond" / "Dit weekend").

## Belangrijke kanttekening

De scraper (`scripts/scrape.py`) haalt data op van filmvandaag.nl. Deze is
geschreven zonder de ruwe HTML-broncode van die site te kunnen inspecteren,
dus de parselogica is gebaseerd op een aanname van de paginastructuur, niet
op geverifieerde CSS-selectors. Voordat je de automatische update aanzet:

1. Draai de scraper eenmalig handmatig (zie hieronder) en controleer of
   `data/now_playing.json` en `data/upcoming.json` er zinnig uitzien.
2. Als er weinig/geen resultaten uitkomen, is de aanname in
   `parse_now_playing` / `parse_upcoming` niet correct voor de echte pagina.
   Bekijk dan de paginabron van filmvandaag.nl in de browser (rechtermuisknop
   → Weergeven paginabron) en pas de functies aan. `scripts/test_fixture.py`
   bevat een lokale test die niet van internet afhankelijk is, handig om je
   aanpassingen snel te checken.

### Extra kanttekening: datums bij speeltijden ("Vanavond" / "Dit weekend")

Om op "vanavond" en "dit weekend" te kunnen filteren, moet elke speeltijd een
datum hebben. filmvandaag.nl toont per film een 7-daagse grid (Vandaag,
Morgen, en 5 weekdagen bij naam); de functie `_find_day_grid_texts` in
`scripts/scrape.py` probeert die grid te vinden en er datums uit af te
leiden. **Dit is nog niet geverifieerd tegen de echte site** — hij is
geschreven op basis van platte, via een tekst-extractie opgehaalde pagina,
niet op basis van de ruwe HTML-tags. Controleer dit dus specifiek bij de
eerste `--debug`-run:

- Vergelijk voor een paar films de datums in `data/now_playing.json` met de
  speeltijden zoals ze op filmvandaag.nl zelf staan.
- Als een film geen dag-grid wordt gevonden, krijgen de speeltijden
  `"date": null` in plaats van een (mogelijk foutieve) datum — die film
  verschijnt dan altijd onder "Alle dagen", maar nooit onder "Vanavond" of
  "Dit weekend". Kijk in de `--debug`-uitvoer hoe vaak dat gebeurt.
- Klopt de datum-toewijzing niet, pas dan `_find_day_grid_texts` aan op basis
  van de echte HTML rond één film met meerdere speeldata (rechtermuisknop →
  Weergeven paginabron, zoek op de filmtitel).

`scripts/test_fixture.py` test alleen dat de parselogica correct werkt
gegeven HTML die aan de aanname voldoet — niet of die aanname klopt voor de
echte site.

## Installatie

1. Maak een nieuwe GitHub-repository aan (bijvoorbeeld `ams-bioscoop`) en
   voeg alle bestanden uit deze map toe.
2. Ga naar **Settings → Actions → General → Workflow permissions** en zet
   dit op **"Read and write permissions"**. Dit is nodig zodat de
   scheduled workflow de ververste data kan terugcommitten.
3. Ga naar **Settings → Pages** en kies bij "Build and deployment":
   Source = **Deploy from a branch**, Branch = **main**, map = **/ (root)**.
4. Draai de workflow eenmalig handmatig: **Actions → Update bioscoopdata →
   Run workflow**. Controleer daarna of `data/now_playing.json` een gevulde
   lijst met bioscopen bevat (zie kanttekening hierboven als dat niet zo is).
5. Je site is na een paar minuten bereikbaar op
   `https://<jouw-gebruikersnaam>.github.io/<repo-naam>/`.

De workflow (`.github/workflows/update-data.yml`) draait daarna dagelijks om
06:00 UTC en commit alleen als de data daadwerkelijk is gewijzigd.

## Lokaal testen

```bash
pip install -r requirements.txt
python scripts/scrape.py --debug          # haalt echte data op, print voortgang
python scripts/test_fixture.py            # test parselogica zonder internet
python -m http.server 8000                # bekijk de site op localhost:8000
```

## Structuur

```
index.html, style.css, script.js   Front-end (leest data/*.json)
scripts/scrape.py                  Scraper: filmvandaag.nl -> data/*.json
scripts/test_fixture.py            Lokale test van de parselogica
data/now_playing.json              "Nu draait" per bioscoop
data/upcoming.json                 "Binnenkort" landelijk, met releasedatum
.github/workflows/update-data.yml  Dagelijkse automatische update
```

### Schema `data/now_playing.json`

```json
{
  "schema_version": 2,
  "generated_at": "2026-09-21T06:00:00+00:00",
  "source": "https://www.filmvandaag.nl/filmladder/stad/13-amsterdam",
  "cinemas": [
    {
      "name": "Kriterion",
      "movies": [
        {
          "title": "The Odyssey",
          "year": 2026,
          "genre": "avontuur / fantasy",
          "rating": 8.4,
          "showtimes": [
            {"date": "2026-09-21", "time": "18:20"},
            {"date": "2026-09-22", "time": "18:20"}
          ]
        }
      ]
    }
  ]
}
```

`showtimes[].date` is `null` wanneer de scraper voor die film geen dag-grid
kon vinden (zie kanttekening hierboven) — zo'n speeltijd telt niet mee voor
de "Vanavond"/"Dit weekend"-filters, maar blijft wel zichtbaar onder "Alle
dagen".

## Uitbreidingsideeën

- Filmposters toevoegen (bijvoorbeeld via de TMDB API, met de titel als
  zoekterm).
- Losse bioscoop-pagina's genereren.
- Meldingen (bijv. via een RSS-feed die je zelf genereert uit
  `upcoming.json`) wanneer een specifieke film wordt aangekondigd.
