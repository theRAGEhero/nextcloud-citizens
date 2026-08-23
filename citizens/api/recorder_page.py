"""Public recorder page (no Nextcloud chrome; loads the lean recorder bundle).

The page computes its own base URL from location.pathname, so it works with
and without a trailing slash, through /apps/app_api/proxy/... or a /exapps/
rewrite.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

RECORDER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#1b1b1b">
<title>Citizens — Table Recorder</title>
<style>
  html, body { margin: 0; background: #1b1b1b; color: #eee;
    font-family: system-ui, -apple-system, sans-serif; }
  #boot { padding: 40px 20px; text-align: center; color: #888; }
</style>
</head>
<body>
<div id="recorder-app"><div id="boot">Loading recorder…</div></div>
<script>
(function () {
  var path = window.location.pathname;
  var idx = path.lastIndexOf('/recorder');
  var base = idx >= 0 ? path.slice(0, idx + '/recorder'.length) : path.replace(/\\/$/, '');
  window.__CITIZENS_RECORDER_BASE__ = base;
  var s = document.createElement('script');
  s.src = base + '/static/citizens-recorder.js';
  s.onerror = function () {
    document.getElementById('boot').textContent =
      'Failed to load the recorder application. Check the connection and reload.';
  };
  document.body.appendChild(s);
  var l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = base + '/static/citizens-recorder.css';
  document.head.appendChild(l);
})();
</script>
</body>
</html>"""


@router.get("/recorder", response_class=HTMLResponse)
@router.get("/recorder/", response_class=HTMLResponse)
def recorder_page() -> str:
    return RECORDER_HTML
