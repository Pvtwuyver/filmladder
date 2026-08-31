# Amsterdamse bioscoopagenda

Statische pagina met films die nu draaien en binnenkort uitkomen in de
bioscopen en filmhuizen van Amsterdam (Pathé-vestigingen en filmhuizen zoals
EYE, Kriterion, FilmHallen, Studio K). Data wordt dagelijks automatisch
ververst via GitHub Actions en gehost via GitHub Pages — geen eigen server
nodig.

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

## Uitbreidingsideeën

- Filmposters toevoegen (bijvoorbeeld via de TMDB API, met de titel als
  zoekterm).
- Extra filters, zoals "vanavond" of "dit weekend".
- Losse bioscoop-pagina's genereren.
- Meldingen (bijv. via een RSS-feed die je zelf genereert uit
  `upcoming.json`) wanneer een specifieke film wordt aangekondigd.
