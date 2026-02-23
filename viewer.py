#!/usr/bin/env python3
"""
Simple image gallery viewer for captured images.
Run on Raspberry Pi and access via http://<pi-ip>:8080
"""
import os
import glob
from flask import Flask, send_file, render_template_string, abort

SAVE_DIR = "/home/pi/captures"
PORT = 8080

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pi Cam Viewer</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #111; color: #eee; font-family: sans-serif; }

    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 20px; background: #1a1a1a; border-bottom: 1px solid #333;
      position: sticky; top: 0; z-index: 10;
    }
    header h1 { font-size: 1rem; font-weight: 600; letter-spacing: 0.05em; }
    header span { font-size: 0.8rem; color: #888; }

    .auto-refresh { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #aaa; }
    .auto-refresh input { accent-color: #4af; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 4px;
      padding: 8px;
    }

    .card {
      position: relative; overflow: hidden; aspect-ratio: 4/3;
      background: #222; cursor: pointer;
    }
    .card img {
      width: 100%; height: 100%; object-fit: cover;
      transition: transform 0.2s;
      loading: lazy;
    }
    .card:hover img { transform: scale(1.04); }
    .card .label {
      position: absolute; bottom: 0; left: 0; right: 0;
      padding: 4px 6px; font-size: 0.65rem; color: #ccc;
      background: linear-gradient(transparent, rgba(0,0,0,0.7));
    }

    .empty { text-align: center; padding: 80px 20px; color: #555; }

    /* Lightbox */
    #lb {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.92); z-index: 100;
      align-items: center; justify-content: center; flex-direction: column;
    }
    #lb.open { display: flex; }
    #lb img { max-width: 95vw; max-height: 90vh; object-fit: contain; }
    #lb .lb-name {
      margin-top: 10px; font-size: 0.8rem; color: #888;
    }
    #lb-close {
      position: absolute; top: 14px; right: 18px;
      font-size: 1.6rem; cursor: pointer; color: #aaa; background: none; border: none;
    }
  </style>
</head>
<body>

<header>
  <h1>Pi Cam &mdash; {{ hostname }}</h1>
  <div style="display:flex; gap:20px; align-items:center;">
    <span>{{ count }} image{{ 's' if count != 1 else '' }}</span>
    <label class="auto-refresh">
      <input type="checkbox" id="ar"> Auto-refresh
    </label>
  </div>
</header>

{% if images %}
<div class="grid">
  {% for img in images %}
  <div class="card" onclick="openLb('{{ img }}')">
    <img src="/img/{{ img }}" alt="{{ img }}" loading="lazy">
    <div class="label">{{ img }}</div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="empty">No images yet in {{ save_dir }}</div>
{% endif %}

<!-- Lightbox -->
<div id="lb">
  <button id="lb-close" onclick="closeLb()">&#x2715;</button>
  <img id="lb-img" src="" alt="">
  <div class="lb-name" id="lb-name"></div>
</div>

<script>
  function openLb(name) {
    document.getElementById('lb-img').src = '/img/' + name;
    document.getElementById('lb-name').textContent = name;
    document.getElementById('lb').classList.add('open');
  }
  function closeLb() {
    document.getElementById('lb').classList.remove('open');
    document.getElementById('lb-img').src = '';
  }
  document.getElementById('lb').addEventListener('click', function(e) {
    if (e.target === this) closeLb();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeLb();
  });

  // Auto-refresh
  let arTimer = null;
  document.getElementById('ar').addEventListener('change', function() {
    if (this.checked) {
      arTimer = setInterval(() => location.reload(), 3000);
    } else {
      clearInterval(arTimer);
    }
  });
</script>
</body>
</html>"""


@app.route("/")
def index():
    files = sorted(
        glob.glob(os.path.join(SAVE_DIR, "*.jpg")),
        key=os.path.getmtime,
        reverse=True,
    )
    images = [os.path.basename(f) for f in files]
    return render_template_string(
        HTML,
        images=images,
        count=len(images),
        save_dir=SAVE_DIR,
        hostname=os.uname().nodename,
    )


@app.route("/img/<filename>")
def serve_image(filename):
    # Prevent directory traversal
    if "/" in filename or ".." in filename:
        abort(400)
    path = os.path.join(SAVE_DIR, filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")


if __name__ == "__main__":
    print(f"Starting viewer on http://0.0.0.0:{PORT}")
    print(f"Images served from: {SAVE_DIR}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
