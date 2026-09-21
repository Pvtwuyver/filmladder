// Genereert data/movies.json: filmtitels, posters en plot-embeddings.
// Wordt uitgevoerd tijdens de build (lokaal of via GitHub Actions), nooit in de browser.
// Vereist de omgevingsvariabele TMDB_API_KEY.

import { pipeline } from "@huggingface/transformers";
import { writeFile, mkdir } from "node:fs/promises";

const TMDB_API_KEY = process.env.TMDB_API_KEY;
if (!TMDB_API_KEY) {
  console.error("TMDB_API_KEY ontbreekt. Zet deze als omgevingsvariabele of GitHub Secret.");
  process.exit(1);
}

// Hetzelfde model als index.html gebruikt voor de zoekopdracht van de bezoeker.
// Moet identiek blijven, anders zijn de vectoren niet vergelijkbaar.
const MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";

// 20 films per TMDb-pagina. 50 pagina's ≈ 1000 films. Aanpasbaar via env var.
const PAGES = Number(process.env.TMDB_PAGES || 50);
const IMAGE_BASE = "https://image.tmdb.org/t/p/w342";
const OUTPUT_PATH = new URL("../data/movies.json", import.meta.url);

// Gelijktijdige aanvragen bij het ophalen van keywords per film.
const KEYWORD_CONCURRENCY = 5;

async function fetchPopularMovies() {
  const movies = [];
  for (let page = 1; page <= PAGES; page++) {
    const url = `https://api.themoviedb.org/3/discover/movie?api_key=${TMDB_API_KEY}&sort_by=popularity.desc&include_adult=false&page=${page}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`TMDb-fout op pagina ${page}: ${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    for (const m of data.results) {
      if (!m.overview || !m.poster_path) continue; // films zonder plot of poster zijn niet bruikbaar
      movies.push({
        id: m.id,
        title: m.title,
        year: m.release_date ? m.release_date.slice(0, 4) : null,
        overview: m.overview,
        poster: `${IMAGE_BASE}${m.poster_path}`,
      });
    }
    console.log(`Pagina ${page}/${PAGES} opgehaald (${movies.length} films tot nu toe).`);
  }
  return movies;
}

async function fetchKeywords(movieId) {
  const url = `https://api.themoviedb.org/3/movie/${movieId}/keywords?api_key=${TMDB_API_KEY}`;
  const res = await fetch(url);
  if (!res.ok) {
    console.warn(`Kon kernwoorden niet ophalen voor film ${movieId}: ${res.status}`);
    return [];
  }
  const data = await res.json();
  return (data.keywords || []).map((k) => k.name);
}

// TMDb's overview is vaak een korte marketingtekst zonder specifieke plotdetails
// (dieren, voorwerpen, tijdsperiode). De keywords-endpoint geeft die details wel,
// en verbetert daarmee de match op specifieke omschrijvingen zoals "met slangen".
async function enrichWithKeywords(movies) {
  const queue = [...movies];
  const enriched = [];
  let done = 0;

  async function worker() {
    while (queue.length) {
      const movie = queue.shift();
      const keywords = await fetchKeywords(movie.id);
      enriched.push({ ...movie, keywords });
      done++;
      if (done % 50 === 0) {
        console.log(`${done}/${movies.length} films van kernwoorden voorzien.`);
      }
    }
  }

  await Promise.all(Array.from({ length: KEYWORD_CONCURRENCY }, worker));
  return enriched;
}

function buildEmbeddingText(movie) {
  const keywordsText = movie.keywords && movie.keywords.length ? ` Kernwoorden: ${movie.keywords.join(", ")}.` : "";
  return `${movie.overview}${keywordsText}`;
}

async function embedMovies(movies) {
  console.log("Embedding-model laden…");
  const extractor = await pipeline("feature-extraction", MODEL_ID, { dtype: "q8" });
  const results = [];
  for (const [i, movie] of movies.entries()) {
    const output = await extractor(buildEmbeddingText(movie), { pooling: "mean", normalize: true });
    // Afronden op 5 decimalen om het uiteindelijke JSON-bestand kleiner te houden.
    const embedding = Array.from(output.data).map((v) => Math.round(v * 1e5) / 1e5);
    results.push({ ...movie, embedding });
    if ((i + 1) % 50 === 0) {
      console.log(`${i + 1}/${movies.length} films ge-embed.`);
    }
  }
  return results;
}

async function main() {
  const rawMovies = await fetchPopularMovies();
  console.log(`${rawMovies.length} films met plot en poster gevonden.`);
  console.log("Kernwoorden ophalen per film…");
  const withKeywords = await enrichWithKeywords(rawMovies);
  const withEmbeddings = await embedMovies(withKeywords);
  await mkdir(new URL("../data", import.meta.url), { recursive: true });
  await writeFile(OUTPUT_PATH, JSON.stringify(withEmbeddings));
  console.log(`Dataset geschreven naar data/movies.json (${withEmbeddings.length} films).`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
