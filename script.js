(function () {
  "use strict";

  const state = {
    now: { generated_at: null, cinemas: [] },
    upcoming: { generated_at: null, films: [] },
    activeTab: "now",
    search: "",
    cinemaFilter: "",
  };

  const el = {
    updatedAt: document.getElementById("updated-at"),
    status: document.getElementById("status-message"),
    nowView: document.getElementById("now-view"),
    upcomingView: document.getElementById("upcoming-view"),
    tabs: document.querySelectorAll(".tab"),
    nowControls: document.getElementById("now-controls"),
    search: document.getElementById("search-input"),
    cinemaFilter: document.getElementById("cinema-filter"),
  };

  function fmtDateTime(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toLocaleString("nl-NL", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return null;
    }
  }

  function fmtDate(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso + "T00:00:00");
      return d.toLocaleDateString("nl-NL", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    } catch {
      return null;
    }
  }

  async function loadData() {
    try {
      const [nowResp, upcomingResp] = await Promise.all([
        fetch("data/now_playing.json", { cache: "no-store" }),
        fetch("data/upcoming.json", { cache: "no-store" }),
      ]);
      state.now = await nowResp.json();
      state.upcoming = await upcomingResp.json();
    } catch (err) {
      el.status.textContent =
        "Kon de filmdata niet laden. Werkt deze pagina via GitHub Pages (niet via file://)?";
      console.error(err);
      return;
    }
    populateCinemaFilter();
    updateTimestamp();
    render();
  }

  function updateTimestamp() {
    const ts = fmtDateTime(state.now.generated_at);
    el.updatedAt.textContent = ts
      ? `Laatst bijgewerkt: ${ts}`
      : "Nog geen data opgehaald — de eerste automatische update moet nog draaien.";
  }

  function populateCinemaFilter() {
    const names = state.now.cinemas.map((c) => c.name).sort();
    for (const name of names) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      el.cinemaFilter.appendChild(opt);
    }
  }

  function render() {
    if (state.activeTab === "now") {
      renderNow();
    } else {
      renderUpcoming();
    }
  }

  function renderNow() {
    const term = state.search.trim().toLowerCase();
    const cinemas = state.now.cinemas
      .filter((c) => !state.cinemaFilter || c.name === state.cinemaFilter)
      .map((c) => ({
        ...c,
        movies: c.movies.filter(
          (m) => !term || m.title.toLowerCase().includes(term)
        ),
      }))
      .filter((c) => c.movies.length > 0);

    el.nowView.innerHTML = "";

    if (state.now.cinemas.length === 0) {
      el.status.textContent =
        "Nog geen programmering beschikbaar. Kom later terug, of controleer of de GitHub Action al is gedraaid.";
      return;
    }
    if (cinemas.length === 0) {
      el.status.textContent = "Geen films gevonden voor deze zoekopdracht/filter.";
      return;
    }
    el.status.textContent = "";

    for (const cinema of cinemas) {
      const card = document.createElement("article");
      card.className = "cinema-card";

      const h2 = document.createElement("h2");
      h2.textContent = cinema.name;
      card.appendChild(h2);

      for (const movie of cinema.movies) {
        const row = document.createElement("div");
        row.className = "movie-row";

        const title = document.createElement("p");
        title.className = "movie-title";
        title.textContent = movie.year ? `${movie.title} (${movie.year})` : movie.title;
        row.appendChild(title);

        if (movie.genre || movie.rating) {
          const meta = document.createElement("p");
          meta.className = "movie-meta";
          const parts = [];
          if (movie.genre) parts.push(movie.genre);
          if (movie.rating) parts.push(`${movie.rating}/10`);
          meta.textContent = parts.join(" · ");
          row.appendChild(meta);
        }

        if (movie.showtimes && movie.showtimes.length) {
          const times = document.createElement("div");
          times.className = "showtimes";
          for (const t of movie.showtimes) {
            const span = document.createElement("span");
            span.className = "showtime";
            span.textContent = t;
            times.appendChild(span);
          }
          row.appendChild(times);
        }

        card.appendChild(row);
      }

      el.nowView.appendChild(card);
    }
  }

  function renderUpcoming() {
    const term = state.search.trim().toLowerCase();
    const films = state.upcoming.films
      .filter((f) => !term || f.title.toLowerCase().includes(term))
      .sort((a, b) => (a.release_date || "9999").localeCompare(b.release_date || "9999"));

    el.upcomingView.innerHTML = "";

    if (state.upcoming.films.length === 0) {
      el.status.textContent =
        "Nog geen aankomende films beschikbaar. Kom later terug, of controleer of de GitHub Action al is gedraaid.";
      return;
    }
    if (films.length === 0) {
      el.status.textContent = "Geen films gevonden voor deze zoekopdracht.";
      return;
    }
    el.status.textContent = "";

    for (const film of films) {
      const card = document.createElement("article");
      card.className = "upcoming-card";

      const title = document.createElement("p");
      title.className = "movie-title";
      title.textContent = film.year ? `${film.title} (${film.year})` : film.title;
      card.appendChild(title);

      const date = document.createElement("span");
      date.className = "release-date";
      date.textContent = fmtDate(film.release_date) || "datum onbekend";
      card.appendChild(date);

      el.upcomingView.appendChild(card);
    }
  }

  function switchTab(tab) {
    state.activeTab = tab;
    el.tabs.forEach((btn) => {
      const isActive = btn.dataset.tab === tab;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", String(isActive));
    });
    el.nowView.hidden = tab !== "now";
    el.upcomingView.hidden = tab !== "upcoming";
    el.nowControls.querySelector("#cinema-filter").hidden = tab !== "now";
    render();
  }

  el.tabs.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  el.search.addEventListener("input", (e) => {
    state.search = e.target.value;
    render();
  });
  el.cinemaFilter.addEventListener("change", (e) => {
    state.cinemaFilter = e.target.value;
    render();
  });

  loadData();
})();
