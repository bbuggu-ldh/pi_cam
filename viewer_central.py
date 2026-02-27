#!/usr/bin/env python3
"""
Central viewer for all Pi cameras.
Run on the main PC: python3 viewer_central.py
Access at http://localhost:8081

Requires: pip install flask
"""
import json
import urllib.request
import urllib.error
from flask import Flask, Response, render_template_string, abort

PI_IPS = ["192.168.0.3", "192.168.0.2", "192.168.0.4"]
PI_PORT = 8080
PORT = 8081
TIMEOUT = 3  # seconds per Pi request

app = Flask(__name__)


def fetch_pi_images(ip):
    """Fetch image list from a Pi's /images.json. Returns dict or None on failure."""
    try:
        url = f"http://{ip}:{PI_PORT}/images.json"
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except Exception:
        return None


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pi Cam Central</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #111; color: #eee; font-family: sans-serif; }

    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 20px; background: #1a1a1a; border-bottom: 1px solid #333;
      position: sticky; top: 0; z-index: 10;
    }
    header h1 { font-size: 1rem; font-weight: 600; letter-spacing: 0.05em; }

    .auto-refresh { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #aaa; }
    .auto-refresh input { accent-color: #4af; }

    .tabs {
      display: flex; gap: 4px; padding: 8px 8px 0; background: #161616;
      border-bottom: 1px solid #2a2a2a; flex-wrap: wrap;
    }
    .tab {
      padding: 6px 14px; border-radius: 6px 6px 0 0; font-size: 0.8rem;
      cursor: pointer; background: #222; color: #888; border: none;
      border-bottom: 2px solid transparent; transition: color 0.15s;
    }
    .tab.active { background: #2a2a2a; color: #eee; border-bottom-color: #4af; }
    .tab.offline { color: #f66; }

    .section { display: none; }
    .section.active { display: block; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 4px; padding: 8px;
    }
    .card {
      position: relative; overflow: hidden; aspect-ratio: 4/3;
      background: #222; cursor: pointer;
    }
    .card img {
      width: 100%; height: 100%; object-fit: cover;
      transition: transform 0.2s;
    }
    .card:hover img { transform: scale(1.04); }
    .card .label {
      position: absolute; bottom: 0; left: 0; right: 0;
      padding: 4px 6px; font-size: 0.65rem; color: #ccc;
      background: linear-gradient(transparent, rgba(0,0,0,0.7));
    }
    .card .pi-badge {
      position: absolute; top: 4px; right: 4px;
      background: rgba(0,0,0,0.65); color: #4af;
      font-size: 0.6rem; padding: 2px 5px; border-radius: 3px;
    }

    .empty { text-align: center; padding: 80px 20px; color: #555; font-size: 0.9rem; }
    .offline-msg { text-align: center; padding: 80px 20px; color: #f66; font-size: 0.9rem; }

    /* Lightbox */
    #lb {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.93); z-index: 100;
      align-items: center; justify-content: center; flex-direction: column;
    }
    #lb.open { display: flex; }
    #lb img { max-width: 92vw; max-height: 86vh; object-fit: contain; }
    #lb .lb-name { margin-top: 10px; font-size: 0.8rem; color: #888; }
    #lb .lb-pi  { margin-top: 4px; font-size: 0.75rem; color: #4af; }
    #lb-close {
      position: absolute; top: 14px; right: 18px;
      font-size: 1.6rem; cursor: pointer; color: #aaa; background: none; border: none;
    }
    #lb-prev, #lb-next {
      position: absolute; top: 50%; transform: translateY(-50%);
      background: rgba(255,255,255,0.07); border: none; color: #ccc;
      font-size: 2rem; padding: 10px 16px; cursor: pointer; border-radius: 4px;
    }
    #lb-prev { left: 10px; }
    #lb-next { right: 10px; }
  </style>
</head>
<body>

<header>
  <h1>Pi Cam &mdash; Central Viewer</h1>
  <div style="display:flex; gap:20px; align-items:center;">
    <span id="count-label" style="font-size:0.8rem;color:#888;"></span>
    <label class="auto-refresh">
      <input type="checkbox" id="ar"> Auto-refresh (5s)
    </label>
  </div>
</header>

<div class="tabs" id="tabs"></div>
<div id="sections"></div>

<div id="lb">
  <button id="lb-close" onclick="closeLb()">&#x2715;</button>
  <button id="lb-prev" onclick="lbStep(-1)">&#8249;</button>
  <img id="lb-img" src="" alt="">
  <button id="lb-next" onclick="lbStep(1)">&#8250;</button>
  <div class="lb-name" id="lb-name"></div>
  <div class="lb-pi"   id="lb-pi"></div>
</div>

<script>
const pis = {{ pis_json }};

let lbItems = [], lbIdx = 0;

// ── Build UI ──────────────────────────────────────────────────────────────────

function buildUI() {
  const tabsEl    = document.getElementById('tabs');
  const sectionsEl = document.getElementById('sections');

  // Collect all images across all online Pis for the "All" tab
  const allItems = [];
  pis.forEach((pi, piIdx) => {
    if (pi.online && pi.images) {
      pi.images.forEach(img => allItems.push({ img, piIdx, badge: true }));
    }
  });

  addTab(tabsEl, 'All (' + allItems.length + ')', 0, false);
  addSection(sectionsEl, allItems, 0);

  pis.forEach((pi, piIdx) => {
    const label = (pi.hostname || pi.ip) + (pi.online ? '' : ' (offline)');
    addTab(tabsEl, label, piIdx + 1, !pi.online);

    if (!pi.online) {
      addOfflineSection(sectionsEl, piIdx + 1, pi.ip);
    } else {
      const items = (pi.images || []).map(img => ({ img, piIdx, badge: false }));
      addSection(sectionsEl, items, piIdx + 1);
    }
  });

  activateTab(0);
}

function addTab(container, label, idx, isOffline) {
  const btn = document.createElement('button');
  btn.className = 'tab' + (isOffline ? ' offline' : '');
  btn.textContent = label;
  btn.dataset.idx = idx;
  btn.onclick = () => activateTab(idx);
  container.appendChild(btn);
}

function addSection(container, items, idx) {
  const div = document.createElement('div');
  div.className = 'section';
  div.dataset.idx = idx;

  if (!items || items.length === 0) {
    div.innerHTML = '<div class="empty">No images yet</div>';
    div._items = [];
    container.appendChild(div);
    return;
  }

  const sectionItems = [];
  const grid = document.createElement('div');
  grid.className = 'grid';

  items.forEach(({ img, piIdx, badge }) => {
    const cardIdx = sectionItems.length;
    sectionItems.push({ img, piIdx });

    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML =
      `<img src="/img/${piIdx}/${img}" alt="${img}" loading="lazy">` +
      `<div class="label">${img}</div>` +
      (badge ? `<div class="pi-badge">${pis[piIdx].hostname || pis[piIdx].ip}</div>` : '');
    card.onclick = () => openLb(sectionItems, cardIdx);
    grid.appendChild(card);
  });

  div._items = sectionItems;
  div.appendChild(grid);
  container.appendChild(div);
}

function addOfflineSection(container, idx, ip) {
  const div = document.createElement('div');
  div.className = 'section';
  div.dataset.idx = idx;
  div._items = [];
  div.innerHTML = `<div class="offline-msg">${ip} — offline or unreachable</div>`;
  container.appendChild(div);
}

function activateTab(idx) {
  document.querySelectorAll('.tab').forEach(t =>
    t.classList.toggle('active', +t.dataset.idx === idx));
  document.querySelectorAll('.section').forEach(s =>
    s.classList.toggle('active', +s.dataset.idx === idx));

  const sec = document.querySelector('.section.active');
  const cnt = sec?._items?.length ?? 0;
  document.getElementById('count-label').textContent =
    idx === 0
      ? pis.reduce((s, p) => s + (p.images ? p.images.length : 0), 0) + ' total'
      : (pis[idx - 1].online ? cnt + ' image' + (cnt !== 1 ? 's' : '') : 'offline');
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

function openLb(items, idx) {
  lbItems = items;
  lbIdx   = idx;
  renderLb();
  document.getElementById('lb').classList.add('open');
}
function renderLb() {
  const { img, piIdx } = lbItems[lbIdx];
  document.getElementById('lb-img').src = `/img/${piIdx}/${img}`;
  document.getElementById('lb-name').textContent = img;
  document.getElementById('lb-pi').textContent   = pis[piIdx].hostname || pis[piIdx].ip;
}
function closeLb() {
  document.getElementById('lb').classList.remove('open');
  document.getElementById('lb-img').src = '';
}
function lbStep(dir) {
  lbIdx = (lbIdx + dir + lbItems.length) % lbItems.length;
  renderLb();
}

document.getElementById('lb').addEventListener('click', e => { if (e.target === e.currentTarget) closeLb(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape')      closeLb();
  if (e.key === 'ArrowRight')  lbStep(1);
  if (e.key === 'ArrowLeft')   lbStep(-1);
});

// ── Auto-refresh ──────────────────────────────────────────────────────────────

let arTimer = null;
document.getElementById('ar').addEventListener('change', function () {
  if (this.checked) arTimer = setInterval(() => location.reload(), 5000);
  else              clearInterval(arTimer);
});

buildUI();
</script>
</body>
</html>"""


@app.route("/")
def index():
    pis_data = []
    for ip in PI_IPS:
        result = fetch_pi_images(ip)
        if result is None:
            pis_data.append({"ip": ip, "online": False})
        else:
            pis_data.append({
                "ip": ip,
                "online": True,
                "hostname": result.get("hostname", ip),
                "images": result.get("images", []),
            })
    return render_template_string(HTML, pis_json=json.dumps(pis_data))


@app.route("/img/<int:pi_idx>/<filename>")
def proxy_image(pi_idx, filename):
    if pi_idx < 0 or pi_idx >= len(PI_IPS):
        abort(400)
    if "/" in filename or ".." in filename:
        abort(400)
    ip = PI_IPS[pi_idx]
    url = f"http://{ip}:{PI_PORT}/img/{filename}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = r.read()
            return Response(data, mimetype="image/jpeg")
    except Exception:
        abort(502)


if __name__ == "__main__":
    print(f"Starting central viewer at http://localhost:{PORT}")
    print(f"Fetching from Pis: {', '.join(PI_IPS)}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
