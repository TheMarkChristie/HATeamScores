/*
 * Team Scores card: every tracked team's games laid out by day. Yesterday's results, today (results, games in
 * play, fixtures), then the fixtures of the coming days, each row with the time only, the two teams with their
 * badges, the score once it is in, and the venue underneath. Built for a phone first.
 *
 * type: custom:team-scores-card
 * title: Scores              (optional; omit for no header)
 * days_ahead: 14             fixtures this many days ahead
 * results_days: 1            results from this many days back (1 = yesterday and today)
 * prefixes: [sensor.football_]   only these sensors (default: every TheSportsDB Tracker sensor)
 * entities: [sensor.x, ...]      or an explicit list
 * show_venue: true
 * show_league: true
 *
 * The integration serves this file and registers it as a dashboard resource; nothing to install.
 */
(function () {
  const ATTRIBUTION = "Data provided by TheSportsDB.com";
  const DAY_MS = 86400000;

  const CSS = `
    :host { display: block; }
    ha-card { padding: 4px 0 10px; }
    .head { padding: 12px 16px 4px; font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
    .day { padding: 12px 16px 4px; font-size: 0.78em; letter-spacing: 0.06em; text-transform: uppercase;
           color: var(--secondary-text-color); }
    .row { display: grid; grid-template-columns: 3.2em minmax(0, 1fr) auto; column-gap: 8px; row-gap: 3px;
           grid-template-areas: "time home hs" "time away as" "time sub sub"; align-items: center;
           padding: 8px 14px 8px 16px; border-top: 1px solid var(--divider-color, rgba(127,127,127,0.2));
           overflow: hidden; }
    .row.first { border-top: none; }
    .time { grid-area: time; align-self: start; padding-top: 3px; font-size: 0.9em; color: var(--secondary-text-color);
            font-variant-numeric: tabular-nums; white-space: nowrap; }
    .time.live { color: var(--error-color, #db4437); font-weight: 600; }
    .time.ft { font-weight: 600; }
    .side { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 0.95em; color: var(--primary-text-color); }
    .side.home { grid-area: home; }
    .side.away { grid-area: away; }
    .side span { min-width: 0; flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .side.mine span { font-weight: 600; }
    .side.loser span { color: var(--secondary-text-color); }
    .badge { width: 22px; height: 22px; flex: 0 0 22px; object-fit: contain; }
    .badge.none { display: inline-block; border-radius: 50%; background: var(--divider-color, rgba(127,127,127,0.3)); }
    .score { min-width: 1.4em; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums;
             color: var(--primary-text-color); font-size: 0.95em; }
    .score.hs { grid-area: hs; }
    .score.as { grid-area: as; }
    .score.loser { color: var(--secondary-text-color); font-weight: 400; }
    .score.live { color: var(--error-color, #db4437); }
    .sub { grid-area: sub; min-width: 0; font-size: 0.78em; color: var(--secondary-text-color); overflow: hidden;
           text-overflow: ellipsis; white-space: nowrap; }
    .empty { padding: 12px 16px; color: var(--secondary-text-color); }
  `;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  class TeamScoresCard extends HTMLElement {
    static getStubConfig() {
      return { title: "Scores", days_ahead: 14, results_days: 1 };
    }

    setConfig(config) {
      this._config = Object.assign({ title: "", days_ahead: 14, results_days: 1, prefixes: null, entities: null,
                                     show_venue: true, show_league: true }, config || {});
      this._sig = null;
      if (this._hass) this._render();
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      return 6;
    }

    _entities() {
      const states = this._hass.states;
      let ids;
      if (Array.isArray(this._config.entities)) ids = this._config.entities.filter((id) => states[id]);
      else {
        ids = Object.keys(states).filter((id) => id.startsWith("sensor.") && states[id].attributes &&
          (states[id].attributes.attribution === ATTRIBUTION || states[id].attributes.sport_prefix));
        if (Array.isArray(this._config.prefixes) && this._config.prefixes.length)
          ids = ids.filter((id) => this._config.prefixes.some((p) => id.startsWith(p)));
      }
      return ids.sort();
    }

    _timeZone() {
      const loc = this._hass.locale || {};
      if (loc.time_zone === "server" && this._hass.config && this._hass.config.time_zone) return this._hass.config.time_zone;
      return undefined;                                   // the browser's zone
    }

    _fmt() {
      const loc = this._hass.locale || {};
      const lang = loc.language || navigator.language;
      const tz = this._timeZone();
      const hour12 = loc.time_format === "12" ? true : loc.time_format === "24" ? false : undefined;
      return {
        time: new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit", hour12, timeZone: tz }),
        day: new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: tz }),
        head: new Intl.DateTimeFormat(lang, { weekday: "long", day: "numeric", month: "long", timeZone: tz }),
      };
    }

    /* every game the sensors know, once each, with the ids of the tracked teams for the bold names */
    _games() {
      const states = this._hass.states;
      const mine = new Set();
      const games = new Map();
      const add = (g, teamId) => {
        if (!g || !g.date) return;
        const key = g.event_id || g.name + g.date;
        const prev = games.get(key);
        if (!prev || (g.finished && !prev.finished) || (g.home_score != null && prev.home_score == null)) games.set(key, g);
      };
      for (const id of this._entities()) {
        const a = states[id].attributes || {};
        if (a.team_id) mine.add(String(a.team_id));
        if (Array.isArray(a.fixtures) || Array.isArray(a.results)) {
          (a.results || []).forEach((g) => add(g));
          (a.fixtures || []).forEach((g) => add(g));
        } else {
          // an older sensor: the game it shows, plus the one before or after it
          const st = states[id].state;
          if (a.date) add({ event_id: a.event_id, name: a.event_name, date: a.date, venue: a.venue, league: a.league, sport: a.sport,
            home_id: a.team_homeaway === "home" ? a.team_id : a.opponent_id, away_id: a.team_homeaway === "home" ? a.opponent_id : a.team_id,
            home: a.team_homeaway === "home" ? a.team_name : a.opponent_name, away: a.team_homeaway === "home" ? a.opponent_name : a.team_name,
            home_badge: a.team_homeaway === "home" ? a.team_logo : a.opponent_logo, away_badge: a.team_homeaway === "home" ? a.opponent_logo : a.team_logo,
            home_score: a.team_homeaway === "home" ? a.team_score : a.opponent_score, away_score: a.team_homeaway === "home" ? a.opponent_score : a.team_score,
            finished: st === "POST" && a.team_score != null, live: st === "IN" });
          add(a.last_game); add(a.next_game);
        }
      }
      return { games: [...games.values()], mine };
    }

    _render() {
      if (!this._hass || !this._config) return;
      const sig = this._entities().map((id) => id + "@" + this._hass.states[id].last_updated).join("|") + "#" + Math.floor(Date.now() / 60000);
      if (sig === this._sig) return;
      this._sig = sig;

      const fmt = this._fmt();
      const now = Date.now();
      const todayKey = fmt.day.format(new Date(now));
      const firstKey = fmt.day.format(new Date(now - this._config.results_days * DAY_MS));
      const lastKey = fmt.day.format(new Date(now + this._config.days_ahead * DAY_MS));
      const yesterdayKey = fmt.day.format(new Date(now - DAY_MS));
      const tomorrowKey = fmt.day.format(new Date(now + DAY_MS));

      const { games, mine } = this._games();
      const rows = [];
      for (const g of games) {
        const t = Date.parse(g.date);
        if (isNaN(t)) continue;
        const key = fmt.day.format(new Date(t));
        // a game with both scores is a result whatever an older sensor says; a past game without one is stale
        if (!g.live && g.home_score != null && g.away_score != null) g.finished = true;
        if (g.finished) { if (key < firstKey) continue; }
        else if (g.live) { /* always shown */ }
        else if (t < now - 4 * 3600000 || key > lastKey) continue;
        rows.push({ g, t, key });
      }
      rows.sort((a, b) => a.t - b.t);

      const byDay = new Map();
      for (const r of rows) {
        if (!byDay.has(r.key)) byDay.set(r.key, []);
        byDay.get(r.key).push(r);
      }

      let html = `<style>${CSS}</style><ha-card>`;
      if (this._config.title) html += `<div class="head">${esc(this._config.title)}</div>`;
      if (!rows.length) html += `<div class="empty">No games in the next ${this._config.days_ahead} days.</div>`;
      for (const [key, list] of byDay) {
        const label = key === todayKey ? "Today" : key === yesterdayKey ? "Yesterday" : key === tomorrowKey ? "Tomorrow" : fmt.head.format(list[0].t);
        html += `<div class="day">${esc(label)}</div>`;
        list.forEach((r, i) => { html += this._row(r.g, r.t, mine, fmt, i === 0); });
      }
      html += `</ha-card>`;
      this.innerHTML = html;
    }

    /* two lines, home over away, each with its badge, name and score; the time (or FT, LIVE) on the left */
    _row(g, t, mine, fmt, first) {
      const settled = g.finished && g.home_score != null && g.away_score != null;
      const homeLost = settled && g.home_score < g.away_score;
      const awayLost = settled && g.away_score < g.home_score;
      const side = (cls, id, name, badge, lost) =>
        `<div class="side ${cls}${mine.has(String(id)) ? " mine" : ""}${lost ? " loser" : ""}">` +
        (badge ? `<img class="badge" src="${esc(badge)}" alt="">` : `<i class="badge none"></i>`) +
        `<span>${esc(name)}</span></div>`;
      const num = (v) => (v == null ? "&ndash;" : esc(v));
      let time, timeCls = "", hs = "", as = "", scoreCls = "";
      if (g.live) { time = "LIVE"; timeCls = "live"; scoreCls = "live"; hs = num(g.home_score); as = num(g.away_score); }
      else if (g.finished) { time = "FT"; timeCls = "ft"; hs = num(g.home_score); as = num(g.away_score); }
      else time = g.time || fmt.time.format(new Date(t));
      const subParts = [];
      if (this._config.show_venue && g.venue) subParts.push(g.venue);
      if (this._config.show_league && g.league) subParts.push(g.league);
      const sub = subParts.length ? `<div class="sub">${esc(subParts.join(" · "))}</div>` : "";
      return `<div class="row${first ? " first" : ""}">` +
        `<div class="time ${timeCls}">${esc(time)}</div>` +
        side("home", g.home_id, g.home, g.home_badge, homeLost) +
        `<div class="score hs ${scoreCls}${homeLost ? " loser" : ""}">${hs}</div>` +
        side("away", g.away_id, g.away, g.away_badge, awayLost) +
        `<div class="score as ${scoreCls}${awayLost ? " loser" : ""}">${as}</div>` +
        sub + `</div>`;
    }
  }

  if (!customElements.get("team-scores-card")) customElements.define("team-scores-card", TeamScoresCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === "team-scores-card"))
    window.customCards.push({ type: "team-scores-card", name: "Team Scores", preview: true,
      description: "Yesterday's results and the coming fixtures of your TheSportsDB Tracker teams, by day." });
})();
