# Filmzoeker

Statische zoekmachine die films matcht op een vrije-tekstomschrijving. Geen server: filmdata en embeddings worden vooraf gegenereerd (build-time), het zoeken zelf gebeurt volledig in de browser van de bezoeker.

## Bestanden

- `index.html` — de site zelf.
- `data/movies.json` — filmtitels, posters en plot-embeddings. Leeg tot de workflow is gedraaid.
- `scripts/build-data.js` — haalt filmdata op bij TMDb en berekent de embeddings.
- `.github/workflows/build-data.yml` — draait dat script automatisch en commit het resultaat.

## Inrichten

1. Zet deze bestanden in een nieuwe of bestaande GitHub-repository.
2. Ga naar **Settings > Secrets and variables > Actions** en maak een secret genaamd `TMDB_API_KEY` met je TMDb-sleutel als waarde.
3. Ga naar **Settings > Pages** en stel de bron in op de `main`-branch, map `/ (root)`.
4. Ga naar het tabblad **Actions**, open de workflow "Filmdataset bijwerken" en start hem handmatig (**Run workflow**) voor de eerste keer.
5. Na een paar minuten staat `data/movies.json` gevuld in de repository en toont de gepubliceerde site de films.

De workflow draait daarna automatisch elke maandag; pas de cron-regel in `build-data.yml` aan voor een andere frequentie. Het aantal opgehaalde films is instelbaar via de omgevingsvariabele `TMDB_PAGES` in dat bestand (standaard 50 pagina's × 20 films ≈ 1000 films).

## Let op

- De eerste zoekopdracht op de site duurt langer: de browser downloadt dan het taalmodel (ongeveer 100–150 MB, eenmalig, wordt daarna lokaal gecached).
- Het model is meertalig gekozen zodat Nederlandstalige zoekopdrachten werken. Wil je een kleiner, sneller model en is Engelstalig zoeken acceptabel, vervang dan `Xenova/paraphrase-multilingual-MiniLM-L12-v2` door `Xenova/all-MiniLM-L6-v2` op **beide** plekken (`index.html` én `scripts/build-data.js` — dit moet hetzelfde model zijn, anders zijn de vectoren niet vergelijkbaar) en genereer de dataset opnieuw.
- Deze opzet is niet end-to-end getest in een browser: de omgeving waarin dit is gebouwd heeft geen internettoegang. Test lokaal (bijvoorbeeld met `npx serve`) voordat je live gaat, en controleer met name of de CDN-import in `index.html` (`cdn.jsdelivr.net/npm/@huggingface/transformers@3/+esm`) correct laadt.
- Films zonder plotomschrijving of poster bij TMDb worden overgeslagen.
