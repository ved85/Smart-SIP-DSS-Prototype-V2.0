"""
Title: Search-bar overlay for SMART-SIP+ Prototype maps.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

from __future__ import annotations

import os

from branca.element import MacroElement
from jinja2 import Template

ONLINE_DEFAULT = os.getenv("MAP_SEARCH_ONLINE", "1").strip().lower() not in (
    "0", "false", "no", "off")


def build_gazetteer(extra_places: list[dict] | None = None) -> list[dict]:
    """
    Local place list for the search bar.

    ``extra_places``: dicts with ``name``, ``lat``, ``lon`` and optionally
    ``kind`` / ``zoom`` (e.g. saved parcels).
    """
    from data.bangladesh_data import DISTRICTS     # imported lazily: avoids cycles

    places = [
        {"name": str(r["district"]),
         "kind": f"District · {r['division']} Division",
         "lat": round(float(r["lat"]), 5),
         "lon": round(float(r["lon"]), 5),
         "zoom": 11}
        for _, r in DISTRICTS.iterrows()
    ]
    for p in extra_places or []:
        try:
            places.append({
                "name": str(p["name"]),
                "kind": str(p.get("kind", "Saved parcel")),
                "lat": round(float(p["lat"]), 5),
                "lon": round(float(p["lon"]), 5),
                "zoom": int(p.get("zoom", 17)),
            })
        except (KeyError, TypeError, ValueError):
            continue                                     # skip malformed entries
    return sorted(places, key=lambda d: (d["kind"].startswith("District"), d["name"]))


class MapSearch(MacroElement):
    """Search box overlaid on the map (see module docstring)."""

    _template = Template(r"""
{% macro script(this, kwargs) %}
(function () {
  var map = {{ this._parent.get_name() }};
  var cfg = {{ this.options|tojson }};
  var places = {{ this.gazetteer|tojson }};
  if (map.__smartsipSearch) { return; }
  map.__smartsipSearch = true;

  /* ---------- styles (once per document) ---------- */
  if (!document.getElementById('smartsip-search-css')) {
    var st = document.createElement('style');
    st.id = 'smartsip-search-css';
    st.textContent = [
      '.smartsip-search{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;',
      'width:min(380px,calc(100% - 190px));min-width:210px;font:12px monospace,sans-serif;color:#e6edf3}',
      '.smartsip-search .ss-row{display:flex;background:rgba(22,27,34,.96);border:1px solid #30363d;',
      'border-radius:18px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.45)}',
      '.smartsip-search .ss-row:focus-within{border-color:#3fb950}',
      '.smartsip-search input{flex:1;min-width:0;border:0;outline:0;background:transparent;color:#e6edf3;',
      'padding:8px 6px 8px 14px;font:inherit}',
      '.smartsip-search input::placeholder{color:#7d8590}',
      '.smartsip-search button{border:0;background:transparent;color:#7d8590;cursor:pointer;padding:0 10px;font-size:14px}',
      '.smartsip-search button:hover{color:#3fb950}',
      '.smartsip-search button:disabled{opacity:.4;cursor:default}',
      '.smartsip-search .ss-list{display:none;margin-top:4px;max-height:220px;overflow-y:auto;',
      'background:rgba(22,27,34,.97);border:1px solid #30363d;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.45)}',
      '.smartsip-search .ss-item{display:flex;flex-direction:column;padding:6px 12px;cursor:pointer;',
      'border-bottom:1px solid #21262d}',
      '.smartsip-search .ss-item:last-child{border-bottom:0}',
      '.smartsip-search .ss-item:hover{background:#1c2330}',
      '.smartsip-search .ss-name{color:#e6edf3}',
      '.smartsip-search .ss-kind{color:#7d8590;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.smartsip-search .ss-note{padding:7px 12px;color:#7d8590}'
    ].join('');
    document.head.appendChild(st);
  }

  /* ---------- DOM ---------- */
  var box = document.createElement('div');
  box.className = 'smartsip-search';
  var row = document.createElement('div');
  row.className = 'ss-row';
  var input = document.createElement('input');
  input.type = 'text';
  input.placeholder = cfg.placeholder;
  input.setAttribute('autocomplete', 'off');
  input.setAttribute('aria-label', 'Search location');
  var clr = document.createElement('button');
  clr.type = 'button'; clr.title = 'Clear'; clr.textContent = '\u2715'; clr.style.display = 'none';
  var btn = document.createElement('button');
  btn.type = 'button'; btn.title = 'Search'; btn.textContent = '\uD83D\uDD0D';
  var list = document.createElement('div');
  list.className = 'ss-list';
  row.appendChild(input); row.appendChild(clr); row.appendChild(btn);
  box.appendChild(row); box.appendChild(list);
  map.getContainer().appendChild(box);

  /* keep clicks / scrolls / keystrokes from reaching the map (and the draw tool) */
  L.DomEvent.disableClickPropagation(box);
  L.DomEvent.disableScrollPropagation(box);
  ['keydown', 'keyup', 'keypress'].forEach(function (t) {
    L.DomEvent.on(input, t, L.DomEvent.stopPropagation);
  });

  var marker = null;
  var busy = false;

  /* ---------- helpers ---------- */
  function hideList() { list.style.display = 'none'; list.innerHTML = ''; }

  function renderList(items, note) {
    list.innerHTML = '';
    if (note) {
      var n = document.createElement('div');
      n.className = 'ss-note'; n.textContent = note;
      list.appendChild(n);
    }
    items.forEach(function (p) {
      var it = document.createElement('div');
      it.className = 'ss-item';
      var nm = document.createElement('span');
      nm.className = 'ss-name'; nm.textContent = p.name;
      var kd = document.createElement('span');
      kd.className = 'ss-kind'; kd.textContent = p.kind || '';
      it.appendChild(nm); it.appendChild(kd);
      it.addEventListener('click', function () { fly(p); hideList(); });
      list.appendChild(it);
    });
    list.style.display = (items.length || note) ? 'block' : 'none';
  }

  function inBD(la, lo) { return la >= 20 && la <= 27 && lo >= 87 && lo <= 94; }

  function parseCoords(q) {
    var m = q.match(/^(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)$/);
    if (!m) { return null; }
    var a = parseFloat(m[1]), b = parseFloat(m[2]);
    /* Bangladesh app: "88.60, 24.37" (lon, lat) is unambiguous - accept either order */
    if (cfg.country === 'bd' && !inBD(a, b) && inBD(b, a)) { return [b, a]; }
    if (Math.abs(a) <= 90 && Math.abs(b) <= 180) { return [a, b]; }
    if (Math.abs(b) <= 90 && Math.abs(a) <= 180) { return [b, a]; }
    return null;
  }

  function localMatches(q) {
    q = q.trim().toLowerCase();
    if (!q) { return []; }
    var starts = [], inside = [];
    places.forEach(function (p) {
      var n = p.name.toLowerCase();
      if (n.indexOf(q) === 0) { starts.push(p); }
      else if (n.indexOf(q) > -1) { inside.push(p); }
    });
    return starts.concat(inside).slice(0, 6);
  }

  function fly(p) {
    if (marker) { map.removeLayer(marker); marker = null; }
    if (p.bounds) { map.fitBounds(p.bounds, { maxZoom: 18 }); }
    else { map.setView([p.lat, p.lon], p.zoom || cfg.zoom); }
    var pop = document.createElement('div');
    var b = document.createElement('b'); b.textContent = p.name; pop.appendChild(b);
    if (p.kind) { var k = document.createElement('div'); k.textContent = p.kind; pop.appendChild(k); }
    var c = document.createElement('div');
    c.textContent = p.lat.toFixed(5) + ', ' + p.lon.toFixed(5); pop.appendChild(c);
    marker = L.marker([p.lat, p.lon]).addTo(map).bindPopup(pop);
    marker.openPopup();
    input.value = p.name;
    clr.style.display = 'block';
  }

  function photon(q) {
    var c = map.getCenter();
    var url = 'https://photon.komoot.io/api/?limit=7&lang=en&lat=' + c.lat.toFixed(3) +
              '&lon=' + c.lng.toFixed(3) + '&q=' + encodeURIComponent(q);
    return fetch(url).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      return r.json();
    }).then(function (j) {
      return (j.features || []).map(function (f) {
        var pr = f.properties || {}, g = f.geometry.coordinates;
        var parts = [pr.name, pr.street, pr.district, pr.city, pr.county, pr.state, pr.country]
          .filter(function (x, i, a) { return x && a.indexOf(x) === i; });
        var p = { name: pr.name || parts[0] || q, kind: parts.slice(1).join(', '),
                  lat: g[1], lon: g[0] };
        if (pr.extent && pr.extent.length === 4) {      /* [minLon, maxLat, maxLon, minLat] */
          p.bounds = [[pr.extent[3], pr.extent[0]], [pr.extent[1], pr.extent[2]]];
        } else { p.zoom = 15; }
        return p;
      });
    });
  }

  function nominatim(q) {
    var url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&accept-language=en&q=' +
              encodeURIComponent(q);
    return fetch(url).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      return r.json();
    }).then(function (rows) {
      return rows.map(function (r) {
        var p = { name: r.name || String(r.display_name).split(',')[0],
                  kind: r.display_name, lat: parseFloat(r.lat), lon: parseFloat(r.lon) };
        var bb = r.boundingbox ? r.boundingbox.map(parseFloat) : null;   /* [S, N, W, E] */
        if (bb && bb.length === 4 && bb.every(isFinite)) { p.bounds = [[bb[0], bb[2]], [bb[1], bb[3]]]; }
        else { p.zoom = 14; }
        return p;
      });
    });
  }

  /* worldwide place-name search: Photon first, Nominatim as fallback */
  function onlineSearch(q) {
    return photon(q).then(function (r) { return r.length ? r : nominatim(q); })
                    .catch(function () { return nominatim(q); });
  }

  /* as-you-type suggestions (Photon only, debounced) */
  var tmr = null, seq = 0;
  function suggest(q) {
    var my = ++seq;
    photon(q).then(function (rows) {
      if (my !== seq || input.value.trim() !== q) { return; }
      var loc = localMatches(q);
      renderList(loc.concat(rows).slice(0, 9), (loc.length || rows.length) ? null : 'No matches - press Enter to search more.');
    }).catch(function () {});
  }

  function submit() {
    seq++; clearTimeout(tmr);
    var q = input.value.trim();
    if (!q) { return; }
    var c = parseCoords(q);
    if (c) {
      hideList();
      fly({ name: c[0].toFixed(5) + ', ' + c[1].toFixed(5), kind: 'Coordinates',
            lat: c[0], lon: c[1], zoom: 17 });
      return;
    }
    var loc = localMatches(q);
    var exact = loc.filter(function (p) { return p.name.toLowerCase() === q.toLowerCase(); })[0];
    if (exact) { hideList(); fly(exact); return; }
    if (!cfg.online) {
      if (loc.length) { hideList(); fly(loc[0]); }
      else { renderList([], 'No match. Try a district name or "lat, lon".'); }
      return;
    }
    if (busy) { return; }
    busy = true; btn.disabled = true;
    renderList([], 'Searching\u2026');
    onlineSearch(q).then(function (rows) {
      if (!rows.length && !loc.length) { renderList([], 'No results for "' + q + '".'); return; }
      renderList(loc.concat(rows), rows.length ? null : 'No online results - local matches shown.');
      fly(rows.length ? rows[0] : loc[0]);
    }).catch(function () {
      renderList(loc, 'Online search unavailable. Use a district name or "lat, lon".');
    }).then(function () { busy = false; btn.disabled = false; });
  }

  /* ---------- events ---------- */
  input.addEventListener('input', function () {
    clr.style.display = input.value ? 'block' : 'none';
    var m = localMatches(input.value);
    if (m.length) { renderList(m, null); } else { hideList(); }
    clearTimeout(tmr);
    var q = input.value.trim();
    if (cfg.online && q.length >= 3 && !parseCoords(q)) {
      tmr = setTimeout(function () { suggest(q); }, 450);
    }
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
    else if (e.key === 'Escape') { hideList(); input.blur(); }
  });
  btn.addEventListener('click', submit);
  clr.addEventListener('click', function () {
    input.value = ''; clr.style.display = 'none'; hideList();
    if (marker) { map.removeLayer(marker); marker = null; }
  });
  map.on('click', hideList);
})();
{% endmacro %}
""")

    def __init__(self, gazetteer: list[dict], online: bool = True,
                 country_codes: str = "bd", zoom: int = 16,
                 placeholder: str = "Search place or lat, lon  \u21b5"):
        super().__init__()
        self._name = "MapSearch"
        self.gazetteer = gazetteer
        self.options = {
            "online": bool(online),
            "country": country_codes or "",
            "zoom": int(zoom),
            "placeholder": placeholder,
        }


def add_map_search(m, extra_places: list[dict] | None = None,
                   online: bool | None = None, country_codes: str = "bd",
                   zoom: int = 16) -> MapSearch:
    """Attach the search bar to a Folium map and return it."""
    ctl = MapSearch(
        build_gazetteer(extra_places),
        online=ONLINE_DEFAULT if online is None else online,
        country_codes=country_codes,
        zoom=zoom,
    )
    ctl.add_to(m)
    return ctl