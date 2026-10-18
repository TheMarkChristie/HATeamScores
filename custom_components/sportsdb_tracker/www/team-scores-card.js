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
 * show_league_logo: true       the competition's logo under the time
 * show_tv: true               the UK and Norwegian channels under each coming game
 * layout: columns             columns: the days side by side when the card is wide enough; list: one long column
 * day_width: 300              the narrowest a day column may be, in pixels
 * show_goals: true             who scored (minute, scorer, assist) in a game's details; tap any game for them
 * show_highlights: true        a Highlights link (YouTube) under a finished game that has one
 * tv_devices: [remote.x, ...]  Google devices (Android TV Remote) a channel can open on: tap a channel, pick the device,
 *                              its app opens there ({entity: remote.x, name: Lounge} to name one)
 * tv_launch_countries: [NO]    only these countries' channels open apps (default: tv_countries)
 * tv_apps: [{match: "^Clan TV", name: Clan TV, app: <package or deep link>, country: UK}]   more channel -> app rows
 * show_tv_button: true         an On TV today button: every game on UK or Norwegian TV today, by time
 * tv_countries: [UK, NO]       which countries' channels to show
 *
 * The integration serves this file and registers it as a dashboard resource; nothing to install.
 * Copyright (c) 2026 Mark Christie. MIT licence. Data provided by TheSportsDB.com.
 */
(function () {
  const ATTRIBUTION = "Data provided by TheSportsDB.com";
  const DAY_MS = 86400000;

  const CSS = `
    :host { display: block; }
    ha-card { padding: 4px 0 10px; container-type: inline-size; }
    /* every day is its own panel with a gap between, so the days stand apart on a phone as well */
    .days { display: flex; flex-direction: column; gap: 12px; padding: 6px 8px 0; }
    .dayblock { min-width: 0; border-radius: 12px; padding-bottom: 4px;
                background: var(--secondary-background-color, rgba(127,127,127,0.08)); }
    /* wide enough for two days side by side: each day becomes its own column */
    @container (min-width: 620px) {
      .days.columns { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--tsc-day-width, 300px), 1fr));
                      gap: 10px; padding: 6px 10px 0; align-items: start; }
    }
    .head { padding: 12px 16px 4px; font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
    .day { display: flex; align-items: baseline; flex-wrap: wrap; column-gap: 8px; padding: 11px 14px 7px 16px;
           font-size: 0.8em; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--primary-text-color);
           border-bottom: 1px solid var(--divider-color, rgba(127,127,127,0.2)); }
    .day .date { font-weight: 400; letter-spacing: 0.03em; color: var(--secondary-text-color); }
    .row { display: grid; grid-template-columns: 3.2em minmax(0, 1fr) auto; column-gap: 8px; row-gap: 3px;
           grid-template-areas: "time home hs" "time away as" "time sub sub" "time tv tv" "detail detail detail"; align-items: center;
           padding: 8px 14px 8px 16px; border-top: 1px solid var(--divider-color, rgba(127,127,127,0.2));
           overflow: hidden; }
    .row.first { border-top: none; }
    .time { grid-area: time; align-self: start; padding-top: 3px; font-size: 0.9em; color: var(--secondary-text-color);
            font-variant-numeric: tabular-nums; white-space: nowrap; }
    .time .lg { display: block; width: 22px; height: 22px; margin-top: 7px; object-fit: contain; object-position: left center; }
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
    .tv { grid-area: tv; min-width: 0; font-size: 0.78em; color: var(--primary-text-color); line-height: 1.6; }
    .tv .flag { display: inline-block; width: 18px; height: 12px; margin-right: 5px; vertical-align: -1px; border-radius: 2px;
                box-shadow: 0 0 0 1px rgba(127,127,127,0.35); }
    .tv .grp { display: inline; margin-right: 10px; }
    .row.click { cursor: pointer; }
    .row.click:hover { background: var(--secondary-background-color, rgba(127,127,127,0.06)); }
    .more { color: var(--primary-color); white-space: nowrap; padding: 0 4px; border-radius: 4px; }
    .more:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--primary-color); }
    .hl a { display: inline-flex; align-items: center; gap: 6px; color: var(--primary-text-color); text-decoration: none; border-radius: 4px; }
    .hl a:hover span { text-decoration: underline; }
    .hl a:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
    .hl svg { width: 20px; height: 14px; flex: 0 0 20px; }
    .sub { display: flex; gap: 6px; }
    .sub .subt { min-width: 0; flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sub .more { flex: 0 0 auto; }
    .detail { grid-area: detail; padding: 6px 0 2px; min-width: 0; }
    .goal { display: grid; grid-template-columns: 3.2em 18px minmax(0, 1fr); column-gap: 8px; align-items: start;
            padding: 3px 0; font-size: 0.85em; color: var(--primary-text-color); }
    .goal.long { grid-template-columns: 4.4em 18px minmax(0, 1fr); }
    .goal .min { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; white-space: nowrap; padding-top: 1px; }
    .goal .b { width: 16px; height: 16px; object-fit: contain; margin-top: 1px; }
    .goal .b.none { display: inline-block; border-radius: 50%; background: var(--divider-color, rgba(127,127,127,0.3)); }
    .goal .who { min-width: 0; overflow-wrap: anywhere; }
    .goal .ast { display: block; font-size: 0.9em; color: var(--secondary-text-color); }
    .goal .note { color: var(--secondary-text-color); }
    .detail .gap { font-size: 0.78em; color: var(--secondary-text-color); padding-top: 3px; }
    .facts { display: grid; grid-template-columns: auto minmax(0, 1fr); column-gap: 10px; row-gap: 4px; font-size: 0.85em;
             margin-left: calc(3.2em + 8px); padding-top: 2px; }
    .goal + .facts, .gap + .facts { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--divider-color, rgba(127,127,127,0.3)); }
    .facts .k { color: var(--secondary-text-color); }
    .facts .v { min-width: 0; overflow-wrap: anywhere; color: var(--primary-text-color); }
    .facts .v .grp { display: block; }
    .facts .flag { display: inline-block; width: 18px; height: 12px; margin-right: 6px; vertical-align: -1px; border-radius: 2px;
                   box-shadow: 0 0 0 1px rgba(127,127,127,0.35); }
    .facts a { color: var(--primary-color); }
    .ch { font: inherit; color: var(--primary-color); background: none; border: 0; padding: 2px 0; margin: 0; cursor: pointer;
          text-decoration: underline; text-underline-offset: 2px; }
    .ch:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; border-radius: 2px; }
    .launch { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0 2px; font-size: 1.15em; }
    .launch .lt { flex: 1 0 100%; color: var(--secondary-text-color); }
    .launch button { font: inherit; padding: 7px 12px; border-radius: 16px; cursor: pointer; background: transparent;
                     border: 1px solid var(--divider-color, rgba(127,127,127,0.35)); color: var(--primary-text-color); }
    .launch button.dev { border-color: var(--primary-color); }
    .launch button:disabled { opacity: 0.5; cursor: default; }
    .launch button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    .launch .msg { flex: 1 0 100%; color: var(--primary-text-color); outline: none; }
    .bar { display: flex; align-items: center; gap: 8px; padding: 8px 12px 2px 16px; min-height: 36px; }
    .bar .head { padding: 0; flex: 1 1 auto; min-width: 0; }
    .tvbtn { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font: inherit; font-size: 0.85em; cursor: pointer;
             padding: 6px 12px; border-radius: 16px; border: 1px solid var(--divider-color, rgba(127,127,127,0.35));
             background: transparent; color: var(--primary-text-color); white-space: nowrap; }
    .tvbtn svg { width: 16px; height: 16px; }
    .tvbtn[aria-pressed="true"] { background: var(--primary-color); border-color: transparent; color: var(--text-primary-color, #fff); }
    .tvbtn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    .tvhead { padding: 10px 16px 2px; font-size: 0.78em; letter-spacing: 0.06em; text-transform: uppercase; color: var(--secondary-text-color); }
    .tvlist { padding: 2px 0; }
    @container (min-width: 620px) {
      .tvlist { columns: auto 340px; column-gap: 14px; padding: 2px 10px; }
      .tvlist .row { break-inside: avoid; }
    }
    .empty { padding: 12px 16px; color: var(--secondary-text-color); }
  `;

  /* the app that shows a channel, by its name and country, for opening it on a Google device (Android TV Remote's
   * remote.turn_on with an activity). An app is a package name (checked on the Play Store, 18 Oct 2026) or a deep link;
   * tv_apps in the card's settings comes first, so a link that works better on a device can replace one here. */
  const APPS = [
    { country: "NO", match: /^TV ?2\b/i, name: "TV 2 Play", app: "no.tv2.sumo" },
    { country: "NO", match: /^(V ?sport|Viaplay)/i, name: "Viaplay", app: "com.viaplay.android" },
    { country: "NO", match: /^NRK/i, name: "NRK TV", app: "no.nrk.tv" },
    { country: "NO", match: /^Eurosport/i, name: "Max", app: "com.wbd.stream" },
    { country: "", match: /^DAZN/i, name: "DAZN", app: "com.dazn" },
    { country: "UK", match: /^Sky Sports/i, name: "Sky Go", app: "com.bskyb.skygo" },
    { country: "UK", match: /^ITV/i, name: "ITVX", app: "air.ITVMobilePlayer" },
  ];

  /* the flag beside each country's channels: the saltire for the UK listings (the household's home there is Scotland),
   * the Norwegian cross for Norway. Drawn inline, so nothing is fetched and every device shows the same thing. */
  const FLAGS = {
    UK: { label: "Scotland", svg: '<svg class="flag" viewBox="0 0 30 20" role="img" aria-label="Scotland"><rect width="30" height="20" fill="#0065BD"/>' +
      '<path d="M0 0L30 20M30 0L0 20" stroke="#fff" stroke-width="4"/></svg>' },
    NO: { label: "Norway", svg: '<svg class="flag" viewBox="0 0 22 16" role="img" aria-label="Norway"><rect width="22" height="16" fill="#BA0C2F"/>' +
      '<path d="M6 0h4v16h-4zM0 6h22v4h-22z" fill="#fff"/><path d="M7 0h2v16h-2zM0 7h22v2h-22z" fill="#00205B"/></svg>' },
  };
  const flag = (cc) => (FLAGS[cc] ? FLAGS[cc].svg : `<span>${esc(cc)}</span>`);

  /* TheSportsDB serves a small copy of each image at <url>/tiny */
  function tiny(url) {
    return /^https?:\/\/[^/]*thesportsdb\.com\/images\/.+\.(png|jpe?g)$/i.test(url) ? url + "/tiny" : url;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  /* redraw the card without moving the page: the scroll position of every scrolling parent (through Home Assistant's
     shadow roots) and of the window is put back afterwards */
  function keepScroll(el, draw) {
    const saved = [];
    for (let n = el.parentNode || el.host; n; n = n.parentNode || n.host) {
      if (n.scrollTop > 0) saved.push([n, n.scrollTop]);
    }
    const x = window.scrollX, y = window.scrollY;
    draw();
    for (const [n, top] of saved) if (n.scrollTop !== top) n.scrollTop = top;
    if (window.scrollY !== y) window.scrollTo(x, y);
  }

  class TeamScoresCard extends HTMLElement {
    static getStubConfig() {
      return { title: "Scores", days_ahead: 14, results_days: 1 };
    }

    constructor() {
      super();
      this._open = new Set();
      this._rowArgs = new Map();
      const toggle = (row) => {
        const key = row.dataset.ev;
        if (this._open.has(key)) this._open.delete(key); else this._open.add(key);
        const again = this._redrawRow(key);
        const marker = again && again.querySelector(".more");
        if (marker) marker.focus({ preventScroll: true });
      };
      this._mode = "scores";
      this._tv = null;
      this._tvLoading = false;
      this._tvTimer = null;
      this._launch = null;
      this.addEventListener("click", (e) => {
        if (!e.target.closest) return;
        if (e.target.closest(".tvbtn")) { this._toggleTv(); return; }
        const ch = e.target.closest(".ch");
        if (ch) { this._askDevice(ch.dataset.ev, ch.dataset.ch, ch.dataset.cc); return; }
        const dev = e.target.closest(".launch .dev");
        if (dev) { this._launchOn(dev.dataset.dev); return; }
        if (e.target.closest(".launch .cancel")) { this._closeLaunch(); return; }
        if (e.target.closest("a, button, .launch")) return;   // a link or button does its own thing, not the goals
        const row = e.target.closest(".row.click");
        if (row) toggle(row);
      });
      this.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this._launch) { this._closeLaunch(); return; }
        if (e.key !== "Enter" && e.key !== " ") return;
        const marker = e.target.closest && e.target.closest(".row.click .more");
        if (marker) { e.preventDefault(); toggle(marker.closest(".row.click")); }
      });
    }

    disconnectedCallback() {
      if (this._tvTimer) { clearInterval(this._tvTimer); this._tvTimer = null; }
    }

    /* a channel opens its app on a Google device (Android TV Remote): tapping it asks which device, every time */
    _appFor(channel, cc) {
      const own = (this._config.tv_apps || []).map((a) => Object.assign({}, a, { match: new RegExp(a.match, "i") }));
      return [...own, ...APPS].find((a) => (!a.country || a.country === cc) && a.match.test(channel)) || null;
    }

    _devices() {
      return (this._config.tv_devices || []).map((d) => {
        const entity = typeof d === "string" ? d : d.entity;
        const st = this._hass && this._hass.states[entity];
        return { entity, name: (typeof d === "object" && d.name) || (st && st.attributes.friendly_name) || entity,
                 ok: !!st && st.state !== "unavailable" };
      });
    }

    _launchable(channel, cc) {
      const countries = this._config.tv_launch_countries || this._config.tv_countries || ["UK", "NO"];
      return this._devices().length > 0 && countries.includes(cc) && !!this._appFor(channel, cc);
    }

    _chan(channel, cc, key) {
      if (!this._launchable(channel, cc)) return esc(channel);
      const app = this._appFor(channel, cc);
      return `<button class="ch" data-ev="${esc(key)}" data-ch="${esc(channel)}" data-cc="${esc(cc)}"` +
        ` aria-label="${esc(`${channel}: open ${app.name} on a TV`)}">${esc(channel)}</button>`;
    }

    _askDevice(key, channel, cc) {
      const app = this._appFor(channel, cc);
      if (!app) return;
      const before = this._launch && this._launch.key;
      this._launch = { key, channel, app, msg: "" };
      if (before && before !== key) this._redrawRow(before);
      const row = this._redrawRow(key);
      const first = row && (row.querySelector(".launch .dev:not([disabled])") || row.querySelector(".launch .cancel"));
      if (first) first.focus({ preventScroll: true });
    }

    _closeLaunch() {
      const key = this._launch && this._launch.key;
      this._launch = null;
      const row = key && this._redrawRow(key);
      const ch = row && row.querySelector(".ch");
      if (ch) ch.focus({ preventScroll: true });
    }

    async _launchOn(entity) {
      const l = this._launch;
      if (!l || !this._hass) return;
      const dev = this._devices().find((d) => d.entity === entity);
      try {
        await this._hass.callService("remote", "turn_on", { entity_id: entity, activity: l.app.app });
        l.msg = `Opening ${l.app.name} on ${dev ? dev.name : entity}.`;
        setTimeout(() => { if (this._launch === l) this._closeLaunch(); }, 4000);
      } catch (err) {
        l.msg = `${l.app.name} could not be opened: ${(err && err.message) || err}`;
      }
      const row = this._redrawRow(l.key);
      const msg = row && row.querySelector(".launch .msg");
      if (msg) msg.focus({ preventScroll: true });
    }

    _launchPanel(key) {
      const l = this._launch;
      if (!l || l.key !== key) return "";
      const devs = this._devices().map((d) =>
        `<button class="dev" data-dev="${esc(d.entity)}"${d.ok ? "" : " disabled"}>${esc(d.name)}${d.ok ? "" : " (unavailable)"}</button>`).join("");
      return `<div class="launch" role="group" aria-label="${esc(`Open ${l.app.name} on`)}">` +
        `<span class="lt">Open ${esc(l.app.name)} (${esc(l.channel)}) on</span>${devs}<button class="cancel">Cancel</button>` +
        (l.msg ? `<span class="msg" role="status" tabindex="-1">${esc(l.msg)}</span>` : "") + `</div>`;
    }

    /* the On TV today view: opened and closed by the button, read again every ten minutes while open */
    _toggleTv() {
      if (this._mode === "tv") {
        this._mode = "scores";
        if (this._tvTimer) { clearInterval(this._tvTimer); this._tvTimer = null; }
      } else {
        this._mode = "tv";
        this._fetchTv();
        this._tvTimer = setInterval(() => this._fetchTv(), 600000);
      }
      this._sig = null;
      this._render();
      const btn = this.querySelector(".tvbtn");
      if (btn) btn.focus({ preventScroll: true });
    }

    async _fetchTv() {
      if (!this._hass) return;
      this._tvLoading = true;
      this._sig = null;
      this._render();
      try {
        this._tv = await this._hass.callWS({ type: "sportsdb_tracker/tv_today" });
      } catch (err) {
        this._tv = { status: "error", games: [], message: (err && err.message) || String(err) };
      }
      this._tvLoading = false;
      this._sig = null;
      this._render();
    }

    _tvView(mine, fmt) {
      const tv = this._tv;
      let html = `<div class="tvhead">On TV today</div>`;
      if (!tv) return html + `<div class="empty">Loading the TV guides...</div>`;
      if (tv.status === "guides_loading") return html + `<div class="empty">The TV guides are still downloading. Try again in a minute.</div>`;
      if (tv.status === "error") return html + `<div class="empty">Today's TV could not be read (${esc(tv.message || "")}).</div>`;
      const wanted = this._config.tv_countries || ["UK", "NO"];
      const games = (tv.games || []).filter((g) => (g.tv || []).some((i) => wanted.includes(i.country)));
      if (!games.length) html += `<div class="empty">Nothing on UK or Norwegian TV today that the guides list.</div>`;
      html += `<div class="tvlist">`;
      games.forEach((g, i) => { html += this._row(Object.assign({}, g, { finished: false, live: false, goals: [] }), Date.parse(g.date), mine, fmt, i === 0); });
      html += `</div>`;
      if (tv.premium === false) html += `<div class="empty" style="font-size:0.8em">A premium TheSportsDB key lists every game; the free key lists a few.</div>`;
      return html;
    }

    setConfig(config) {
      this._config = Object.assign({ title: "", days_ahead: 14, results_days: 1, prefixes: null, entities: null,
                                     show_venue: true, show_league: true, show_league_logo: true, show_tv: true, tv_countries: ["UK", "NO"],
                                     layout: "columns", day_width: 300, show_goals: true, show_tv_button: true,
                                     show_highlights: true, tv_devices: [], tv_launch_countries: null, tv_apps: [] }, config || {});
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
      const add = (g) => {
        if (!g || !g.date) return;
        const key = g.event_id || g.name + g.date;
        const prev = games.get(key);
        if (!prev) { games.set(key, Object.assign({}, g)); return; }
        // the fuller record wins; badges and ids fill in from whichever copy has them
        const better = (g.finished && !prev.finished) || (g.home_score != null && prev.home_score == null) || (g.live && !prev.live);
        const merged = better ? Object.assign({}, prev, g) : Object.assign({}, g, prev);
        for (const k of ["home_badge", "away_badge", "home_id", "away_id", "venue", "league"]) if (merged[k] == null) merged[k] = g[k] != null ? g[k] : prev[k];
        if (!(merged.tv && merged.tv.length)) merged.tv = (g.tv && g.tv.length) ? g.tv : prev.tv;
        if (!(merged.goals && merged.goals.length)) {
          const src = (g.goals && g.goals.length) ? g : prev;
          merged.goals = src.goals; merged.goals_complete = src.goals_complete;
        }
        games.set(key, merged);
      };
      for (const id of this._entities()) {
        const a = states[id].attributes || {};
        if (a.team_id) mine.add(String(a.team_id));
        // the game the sensor shows, the ones either side of it, and its fixtures and results lists: all of them,
        // deduplicated by event id, so a sensor whose lists are still filling (or an older sensor) shows its game
        const st = states[id].state;
        const home = a.team_homeaway === "home";
        if (a.date) add({ event_id: a.event_id, name: a.event_name, date: a.date, venue: a.venue, league: a.league, sport: a.sport,
          home_id: home ? a.team_id : a.opponent_id, away_id: home ? a.opponent_id : a.team_id,
          home: home ? a.team_name : a.opponent_name, away: home ? a.opponent_name : a.team_name,
          home_badge: home ? a.team_logo : a.opponent_logo, away_badge: home ? a.opponent_logo : a.team_logo,
          home_score: home ? a.team_score : a.opponent_score, away_score: home ? a.opponent_score : a.team_score,
          finished: st === "POST" && a.team_score != null, live: st === "IN" });
        add(a.last_game); add(a.next_game);
        (a.results || []).forEach((g) => add(g));
        (a.fixtures || []).forEach((g) => add(g));
      }
      return { games: [...games.values()], mine };
    }

    _render() {
      if (!this._hass || !this._config) return;
      const sig = this._entities().map((id) => id + "@" + this._hass.states[id].last_updated).join("|") + "#" + Math.floor(Date.now() / 60000) +
        "#" + this._mode + (this._tvLoading ? "L" : "");
      if (sig === this._sig) return;
      this._sig = sig;
      this._rowArgs = new Map();

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

      let html = "";
      const button = this._config.show_tv_button
        ? `<button class="tvbtn" aria-pressed="${this._mode === "tv"}" title="Every game on UK or Norwegian TV today">` +
          `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z"/></svg>` +
          `${this._mode === "tv" ? "Back to scores" : "On TV today"}</button>` : "";
      if (this._config.title || button) html += `<div class="bar">${this._config.title ? `<div class="head">${esc(this._config.title)}</div>` : ""}${button}</div>`;
      if (this._mode === "tv") {
        this._paint(html + this._tvView(mine, fmt));
        return;
      }
      if (!rows.length) html += `<div class="empty">No games in the next ${this._config.days_ahead} days.</div>`;
      const columns = this._config.layout !== "list";
      const width = Math.max(220, Number(this._config.day_width) || 300);
      html += `<div class="days${columns ? " columns" : ""}" style="--tsc-day-width:${width}px">`;
      for (const [key, list] of byDay) {
        const named = key === todayKey ? "Today" : key === yesterdayKey ? "Yesterday" : key === tomorrowKey ? "Tomorrow" : "";
        const date = fmt.head.format(list[0].t);
        html += `<section class="dayblock"><div class="day" role="heading" aria-level="3">` +
          (named ? `${esc(named)}<span class="date">${esc(date)}</span>` : esc(date)) + `</div>`;
        list.forEach((r, i) => { html += this._row(r.g, r.t, mine, fmt, i === 0); });
        html += `</section>`;
      }
      html += `</div>`;
      this._paint(html);
    }

    /* the card's content into one ha-card that is kept for good. A new ha-card draws its frame a moment after it is
       created and is empty until then: replacing it on every redraw let the page shrink for that moment, and a phone
       scrolled back to the top (Mark, 18 Oct 2026: "it should also not scroll to the top when i open up scorers") */
    _paint(inner) {
      if (!this._card || this._card.parentNode !== this) {
        this.innerHTML = `<style>${CSS}</style><ha-card></ha-card>`;
        this._card = this.querySelector("ha-card");
      }
      keepScroll(this, () => { this._card.innerHTML = inner; });
    }

    /* one game drawn again in place (opened, closed, asked for a device): the rest of the card is left as it is, so
       the page does not move */
    _redrawRow(key) {
      const args = this._rowArgs.get(key);
      const el = [...this.querySelectorAll(".row")].find((r) => r.dataset.ev === key);
      if (!args || !el) {
        this._sig = null;
        this._render();
        return [...this.querySelectorAll(".row")].find((r) => r.dataset.ev === key);
      }
      const tmp = document.createElement("div");
      tmp.innerHTML = this._row(...args);
      const fresh = tmp.firstElementChild;
      el.replaceWith(fresh);
      return fresh;
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
      // the league's name is on the line underneath unless that is switched off; then the logo carries it
      const logo = this._config.show_league_logo && g.league_logo
        ? `<img class="lg" src="${esc(tiny(g.league_logo))}" alt="${this._config.show_league ? "" : esc(g.league || "")}"` +
          ` title="${esc(g.league || "")}" loading="lazy">` : "";
      const key = String(g.event_id || (g.name || "") + g.date);
      this._rowArgs.set(key, [g, t, mine, fmt, first]);       // so the row can be drawn again on its own
      const goals = this._config.show_goals && Array.isArray(g.goals) ? g.goals : [];
      const open = this._open.has(key);
      const word = goals.length ? (g.sport === "American Football" ? "Scoring" : "Goals") : "Details";
      const more = `<span class="more" role="button" tabindex="0" aria-expanded="${open}"` +
          ` aria-label="${esc(`${g.home} v ${g.away}: ${open ? "hide" : "show"} ${word.toLowerCase()}`)}">` +
          `${open ? `${word} &#9652;` : `${word} &#9662;`}</span>`;
      const subText = esc(subParts.join(" · "));
      const sub = `<div class="sub"><span class="subt">${subText}</span>${more}</div>`;
      const detail = open ? this._details(g, goals, t, fmt) : "";
      let tv = "";
      if (this._config.show_tv && !g.finished && Array.isArray(g.tv) && g.tv.length) {
        const groups = [];
        for (const cc of this._config.tv_countries || ["UK", "NO"]) {
          const names = g.tv.filter((i) => i.country === cc).map((i) => i.channel);
          if (!names.length) continue;
          const shown = names.slice(0, 3).map((n) => this._chan(n, cc, key)).join(", ") + (names.length > 3 ? ` +${names.length - 3}` : "");
          groups.push(`<span class="grp">${flag(cc)}${shown}</span>`);
        }
        if (groups.length) tv = `<div class="tv">${groups.join("")}</div>`;
      }
      // the device question for a tapped channel, under the channels
      const launch = this._launchPanel(key);
      if (launch) tv = tv ? tv.replace(/<\/div>$/, `${launch}</div>`) : `<div class="tv">${launch}</div>`;
      // a finished game's highlights go where a coming game's channels are
      if (this._config.show_highlights && g.finished && /^https?:\/\//i.test(g.video || "")) {
        tv = `<div class="tv hl"><a href="${esc(g.video)}" target="_blank" rel="noopener noreferrer"` +
          ` aria-label="${esc(`${g.home} v ${g.away}: highlights (opens in a new tab)`)}">` +
          `<svg viewBox="0 0 28 20" aria-hidden="true"><rect width="28" height="20" rx="5" fill="#f00"/><path d="M11 5.5v9l8-4.5z" fill="#fff"/></svg>` +
          `<span>Highlights</span></a></div>`;
      }
      return `<div class="row click${first ? " first" : ""}" data-ev="${esc(key)}">` +
        `<div class="time ${timeCls}">${esc(time)}${logo}</div>` +
        side("home", g.home_id, g.home, g.home_badge, homeLost) +
        `<div class="score hs ${scoreCls}${homeLost ? " loser" : ""}">${hs}</div>` +
        side("away", g.away_id, g.away, g.away_badge, awayLost) +
        `<div class="score as ${scoreCls}${awayLost ? " loser" : ""}">${as}</div>` +
        sub + tv + detail + `</div>`;
    }

    /* who scored, in match order: the time, the scoring side's badge, the scorer (the NFL: the play), the assist under it */
    _goals(g, goals) {
      const long = goals.some((x) => String(x.time).length > 4);         // "P1 17:56", "Q2 8:00" need a wider column
      const badge = (side) => {
        const b = side === "home" ? g.home_badge : side === "away" ? g.away_badge : null;
        const name = side === "home" ? g.home : side === "away" ? g.away : "";
        return b ? `<img class="b" src="${esc(b)}" alt="${esc(name)}">` : `<i class="b none" title="${esc(name)}"></i>`;
      };
      let html = "";
      for (const x of goals) {
        html += `<div class="goal${long ? " long" : ""}"><span class="min">${esc(x.time)}</span>${badge(x.side)}<span class="who">${esc(x.player)}` +
          (x.note ? ` <span class="note">(${esc(x.note)})</span>` : "") +
          (x.assist ? `<span class="ast">${esc(x.assist)}</span>` : "") + `</span></div>`;
      }
      if (g.goals_complete === false) html += `<div class="gap">Not every goal is listed for this game.</div>`;
      return html;
    }

    /* what tapping a game opens: who scored, then the competition and round, when, where, every channel (not only the
       first three per country), the match page on TheSportsDB */
    _details(g, goals, t, fmt) {
      const key = String(g.event_id || (g.name || "") + g.date);
      const facts = [];
      const round = Number(g.round);
      const comp = [g.league, round > 0 && round < 100 ? `Round ${round}` : ""].filter(Boolean).join(" · ");
      if (comp) facts.push(["Competition", esc(comp)]);
      const when = new Date(t);
      facts.push(["When", esc(`${fmt.head.format(when)}, ${g.time || fmt.time.format(when)}`)]);
      const where = [g.venue, g.country].filter(Boolean).join(", ");
      if (where) facts.push(["Venue", esc(where)]);
      if (!g.finished && Array.isArray(g.tv) && g.tv.length) {
        const groups = [];
        for (const cc of this._config.tv_countries || ["UK", "NO"]) {
          const names = g.tv.filter((i) => i.country === cc).map((i) => i.channel);
          if (names.length) groups.push(`<span class="grp">${flag(cc)}${names.map((n) => this._chan(n, cc, key)).join(", ")}</span>`);
        }
        if (groups.length) facts.push(["TV", groups.join("")]);
      }
      if (g.event_id) {
        const url = `https://www.thesportsdb.com/event/${encodeURIComponent(g.event_id)}`;
        facts.push(["More", `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Match page on TheSportsDB</a>`]);
      }
      return `<div class="detail">${goals.length ? this._goals(g, goals) : ""}<div class="facts">` +
        facts.map(([k, v]) => `<span class="k">${k}</span><span class="v">${v}</span>`).join("") + `</div></div>`;
    }
  }

  /* Home Assistant's frontend replaces the custom element registry's methods as it starts (its scoped-registry
   * polyfill keeps its own table), so an element defined before that point is reported as not existing afterwards.
   * This file is imported by the page alongside the frontend itself, so it can run first: register once the frontend's
   * root element is known, which is immediate when the file arrives as a dashboard resource. */
  function whenFrontendReady(fn) {
    const ready = () => !!customElements.get("home-assistant");
    if (ready()) { fn(); return; }
    let tries = 0;
    const timer = setInterval(() => {
      if (ready() || ++tries > 600) { clearInterval(timer); fn(); }
    }, 50);
  }
  whenFrontendReady(() => {
    if (!customElements.get("team-scores-card")) customElements.define("team-scores-card", TeamScoresCard);
    window.customCards = window.customCards || [];
    if (!window.customCards.some((c) => c.type === "team-scores-card"))
      window.customCards.push({ type: "team-scores-card", name: "Team Scores", preview: true,
        description: "Yesterday's results and the coming fixtures of your TheSportsDB Tracker teams, by day." });
  });
})();
