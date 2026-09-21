(function () {
  "use strict";

  const EVENING_HOUR = 18; // vanaf dit uur telt een speeltijd als "vanavond"

  const state = {
    now: { generated_at: null, cinemas: [] },
    upcoming: { generated_at: null, films: [] },
    activeTab: "now",
    search: "",
    cinemaFilter: "",
    dayFilter: "all", // "all" | "today" | "weekend"
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
    dayFilterButtons: document.querySelectorAll(".day-filter"),
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

  // --- Datumhelpers voor de "vanavond" / "dit weekend" filters ---
  // Gebaseerd op de kloktijd van de bezoeker (client-side), niet op
  // generated_at van de data.

  function todayDate() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function toISODate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function addDays(d, n) {
    const copy = new Date(d);
    copy.setDate(copy.getDate() + n);
    return copy;
  }

  // Geeft [zaterdag-iso, zondag-iso] voor het eerstvolgende (of lopende) weekend.
  // Op een zondag is het "verstreken" zaterdag niet meer bruikbaar (die data
  // hebben we niet), dus dan telt alleen de zondag zelf.
  function weekendISORange(today) {
    const day = today.getDay(); // 0 = zondag ... 6 = zaterdag
    if (day === 0) return [toISODate(today)];
    const satOffset = 6 - day;
    const sat = addDays(today, satOffset);
    const sun = addDays(sat, 1);
    return [toISODate(sat), toISODate(sun)];
  }

  function dayLabelForISO(iso, todayISO, tomorrowISO) {
    if (iso === todayISO) return "Vandaag";
    if (iso === tomorrowISO) return "Morgen";
    try {
      const d = new Date(iso + "T00:00:00");
      const label = d.toLocaleDateString("nl-NL", { weekday: "long" });
      return label.charAt(0).toUpperCase() + label.slice(1);
    } catch {
      return iso;
    }
  }

  function showtimeMatchesFilter(showtime, filter, todayISO, weekendISOs) {
    if (filter === "today") return showtime.date === todayISO && showtime.time >= `${String(EVENING_HOUR).padStart(2, "0")}:00`;
    if (filter === "weekend") return weekendISOs.includes(showtime.date);
    return true;
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
    const today = todayDate();
    const todayISO = toISODate(today);
    const tomorrowISO = toISODate(addDays(today, 1));
    const weekendISOs = weekendISORange(today);

    const cinemas = state.now.cinemas
      .filter((c) => !state.cinemaFilter || c.name === state.cinemaFilter)
      .map((c) => ({
        ...c,
        movies: c.movies
          .filter((m) => !term || m.title.toLowerCase().includes(term))
          .map((m) => ({
            ...m,
            matchingShowtimes: (m.showtimes || []).filter((s) =>
              showtimeMatchesFilter(s, state.dayFilter, todayISO, weekendISOs)
            ),
          }))
          .filter((m) => state.dayFilter === "all" || m.matchingShowtimes.length > 0),
      }))
      .filter((c) => c.movies.length > 0);

    el.nowView.innerHTML = "";

    if (state.now.cinemas.length === 0) {
      el.status.textContent =
        "Nog geen programmering beschikbaar. Kom later terug, of controleer of de GitHub Action al is gedraaid.";
      return;
    }
    if (cinemas.length === 0) {
      el.status.textContent =
        state.dayFilter === "all"
          ? "Geen films gevonden voor deze zoekopdracht/filter."
          : "Geen films gevonden voor deze zoekopdracht/filter in de geselecteerde periode.";
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

        const showtimesToRender =
          state.dayFilter === "all" ? movie.showtimes || [] : movie.matchingShowtimes;

        if (showtimesToRender.length) {
          row.appendChild(renderShowtimesByDay(showtimesToRender, todayISO, tomorrowISO));
        }

        card.appendChild(row);
      }

      el.nowView.appendChild(card);
    }
  }

  // Groepeert een lijst {date, time} showtimes per dag en rendert per dag
  // een label ("Vandaag", "Morgen", "Woensdag", ...) met de bijbehorende tijden.
  function renderShowtimesByDay(showtimes, todayISO, tomorrowISO) {
    const byDate = new Map();
    for (const s of showtimes) {
      if (!byDate.has(s.date)) byDate.set(s.date, []);
      byDate.get(s.date).push(s.time);
    }
    const dates = [...byDate.keys()].sort();

    const wrap = document.createElement("div");
    wrap.className = "showtimes-by-day";

    for (const date of dates) {
      const group = document.createElement("div");
      group.className = "showtime-day-group";

      const label = document.createElement("span");
      label.className = "showtime-day-label";
      label.textContent = dayLabelForISO(date, todayISO, tomorrowISO);
      group.appendChild(label);

      const times = document.createElement("div");
      times.className = "showtimes";
      for (const t of byDate.get(date).sort()) {
        const span = document.createElement("span");
        span.className = "showtime";
        span.textContent = t;
        times.appendChild(span);
      }
      group.appendChild(times);

      wrap.appendChild(group);
    }

    return wrap;
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
    el.cinemaFilter.hidden = tab !== "now";
    document.querySelector(".day-filters").hidden = tab !== "now";
    render();
  }

  function setDayFilter(filter) {
    state.dayFilter = filter;
    el.dayFilterButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.dayFilter === filter);
    });
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
  el.dayFilterButtons.forEach((btn) => {
    btn.addEventListener("click", () => setDayFilter(btn.dataset.dayFilter));
  });

  loadData();
})();
