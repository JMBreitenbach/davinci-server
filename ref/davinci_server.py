#!/usr/bin/env python3
"""
davinci_server.py

A small LAN web server for the XYZ da Vinci 1.0 Pro, backed by
miniMoverConsole ("minimover").

Provides two things:
  1. A plain browser UI at http://<pi-ip>:5000/  -- upload a .gcode
     file, see the file list, hit Print / Delete.
  2. A minimal subset of OctoPrint's REST API, so Cura and OrcaSlicer's
     built-in "OctoPrint" network-printing option can talk to this
     server directly (Settings -> Printers -> connect via OctoPrint,
     point it at this Pi's IP and port 5000, any API key you like).

Requires: pip3 install flask --break-system-packages

Run:
    python3 davinci_server.py
Then browse to http://<pi-ip>:5000/

--------------------------------------------------------------------
IMPORTANT CAVEATS (read before relying on this):

- Only ONE print job is supported at a time; a second request while
  printing is rejected.
- Progress reporting is a best-effort ESTIMATE based on elapsed time
  vs. a file-size heuristic, NOT real telemetry -- minimover's status
  output format for this printer isn't fully confirmed. If you find
  out the real format (run `minimover -d /dev/ttyACM0 -s` while idle
  and while printing, compare output), update parse_status() below.
- API key checking is OFF by default (LAN convenience). Set API_KEY
  below to require one -- do this if the Pi is reachable beyond your
  trusted LAN.
--------------------------------------------------------------------
"""

import os
import subprocess
import threading
import time
import re
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string, send_from_directory

# ---- Configuration ---------------------------------------------------
# All of these can be overridden with environment variables, so a
# packaged install doesn't require editing this file. See install.sh /
# the systemd unit for where these get set.

MINIMOVER_BIN = os.environ.get("DAVINCI_MINIMOVER_BIN", "/usr/local/bin/minimover")
SERIAL_DEVICE = os.environ.get("DAVINCI_SERIAL_DEVICE", "/dev/ttyACM0")
UPLOAD_DIR = Path(os.environ.get("DAVINCI_UPLOAD_DIR", str(Path.home() / "davinci" / "uploads")))
API_KEY = os.environ.get("DAVINCI_API_KEY") or None  # unset/empty = no auth required
PORT = int(os.environ.get("DAVINCI_PORT", "5000"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# ---- Shared print-job state -------------------------------------------

job_lock = threading.Lock()
job_state = {
    "printing": False,
    "filename": None,
    "started_at": None,
    "completion": 0.0,   # 0.0 - 1.0, estimated
    "state_text": "Operational",
    "last_error": None,
}


def estimate_total_seconds(path: Path) -> int:
    """Very rough heuristic: ~2 seconds of print time per KB of gcode.
    Replace with something better once you have real prints to calibrate
    against (e.g. log actual durations per file size)."""
    kb = path.stat().st_size / 1024
    return max(60, int(kb * 2))


def run_print_job(path: Path):
    total_est = estimate_total_seconds(path)
    start = time.time()

    with job_lock:
        job_state.update(
            printing=True, filename=path.name, started_at=start,
            completion=0.0, state_text="Printing", last_error=None,
        )

    proc = subprocess.Popen(
        [MINIMOVER_BIN, "-d", SERIAL_DEVICE, "-p", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    # Poll while the process runs, faking progress off elapsed time
    while proc.poll() is None:
        elapsed = time.time() - start
        with job_lock:
            job_state["completion"] = min(0.98, elapsed / total_est)
        time.sleep(2)

    output = proc.stdout.read() if proc.stdout else ""
    ok = proc.returncode == 0

    with job_lock:
        job_state.update(
            printing=False,
            completion=1.0 if ok else job_state["completion"],
            state_text="Operational" if ok else "Error",
            last_error=None if ok else output[-500:],
        )


def start_print(path: Path) -> bool:
    with job_lock:
        if job_state["printing"]:
            return False
    t = threading.Thread(target=run_print_job, args=(path,), daemon=True)
    t.start()
    return True


def check_api_key():
    if API_KEY and request.headers.get("X-Api-Key") != API_KEY:
        return jsonify(error="Invalid API key"), 401
    return None


# ---- Browser UI ---------------------------------------------------------

PAGE = """
<!doctype html>
<html>
<head>
<title>da Vinci 1.0 Pro</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: sans-serif; max-width: 640px; margin: 2em auto; padding: 0 1em; }
  h1 { font-size: 1.3em; }
  .file { display: flex; justify-content: space-between; align-items: center;
          padding: 0.5em 0; border-bottom: 1px solid #ddd; }
  button { padding: 0.4em 0.8em; margin-left: 0.4em; }
  #status { padding: 0.8em; background: #f2f2f2; border-radius: 6px; margin-bottom: 1em; }
  progress { width: 100%; }
</style>
</head>
<body>
<h1>da Vinci 1.0 Pro</h1>

<div id="status">Loading status...</div>

<form id="uploadForm" enctype="multipart/form-data">
  <input type="file" name="file" accept=".gcode" required>
  <button type="submit">Upload</button>
</form>

<h2>Files</h2>
<div id="files">Loading...</div>

<script>
async function refresh() {
  const s = await (await fetch('/status')).json();
  const statusDiv = document.getElementById('status');
  if (s.printing) {
    statusDiv.innerHTML = `Printing <b>${s.filename}</b> &mdash; ` +
      `${Math.round(s.completion * 100)}% (estimated)` +
      `<br><progress value="${s.completion}" max="1"></progress>`;
  } else {
    statusDiv.innerHTML = s.last_error
      ? `Idle. Last job failed: <pre>${s.last_error}</pre>`
      : 'Idle. Printer ready.';
  }

  const files = await (await fetch('/files')).json();
  const filesDiv = document.getElementById('files');
  filesDiv.innerHTML = files.length ? '' : '<i>No files uploaded yet.</i>';
  for (const f of files) {
    const row = document.createElement('div');
    row.className = 'file';
    row.innerHTML = `<span>${f}</span>` +
      `<span>
         <button onclick="printFile('${f}')" ${s.printing ? 'disabled' : ''}>Print</button>
         <button onclick="deleteFile('${f}')" ${s.printing ? 'disabled' : ''}>Delete</button>
       </span>`;
    filesDiv.appendChild(row);
  }
}

async function printFile(name) {
  await fetch('/print/' + encodeURIComponent(name), { method: 'POST' });
  refresh();
}
async function deleteFile(name) {
  if (!confirm('Delete ' + name + '?')) return;
  await fetch('/delete/' + encodeURIComponent(name), { method: 'DELETE' });
  refresh();
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const data = new FormData(e.target);
  await fetch('/upload', { method: 'POST', body: data });
  e.target.reset();
  refresh();
});

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/files")
def list_files():
    return jsonify(sorted(p.name for p in UPLOAD_DIR.glob("*.gcode")))


@app.route("/status")
def status():
    with job_lock:
        return jsonify(dict(job_state))


@app.route("/upload", methods=["POST"])
def web_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".gcode"):
        return jsonify(error="Expected a .gcode file"), 400
    dest = UPLOAD_DIR / f.filename
    f.save(dest)
    return jsonify(ok=True, filename=f.filename)


@app.route("/print/<path:filename>", methods=["POST"])
def web_print(filename):
    path = UPLOAD_DIR / filename
    if not path.exists():
        return jsonify(error="No such file"), 404
    if not start_print(path):
        return jsonify(error="Printer busy"), 409
    return jsonify(ok=True)


@app.route("/delete/<path:filename>", methods=["DELETE"])
def web_delete(filename):
    path = UPLOAD_DIR / filename
    if path.exists():
        path.unlink()
    return jsonify(ok=True)


# ---- Minimal OctoPrint-compatible API (for Cura / OrcaSlicer) -----------
#
# Cura's "Connect via OctoPrint" and OrcaSlicer's "OctoPrint" print host
# both do roughly: GET /api/version (to confirm it's alive), then
# POST /api/files/local with the gcode file and form fields
# select=true/print=true to upload-and-print in one step.

@app.route("/api/version")
def api_version():
    err = check_api_key()
    if err: return err
    return jsonify(api="0.1", server="1.9.0", text="OctoPrint 1.9.0 (daVinci shim)")


@app.route("/api/server")
def api_server():
    err = check_api_key()
    if err: return err
    return jsonify(version="1.9.0", safemode=False)


@app.route("/api/settings")
def api_settings():
    err = check_api_key()
    if err: return err
    # Minimal shape; webcam disabled so slicers don't try to embed a stream
    return jsonify(webcam={"webcamEnabled": False}, feature={"sdSupport": False})


@app.route("/api/printer")
def api_printer():
    err = check_api_key()
    if err: return err
    with job_lock:
        state_text = job_state["state_text"]
    return jsonify(
        state={"text": state_text, "flags": {
            "operational": True,
            "printing": job_state["printing"],
            "error": state_text == "Error",
            "ready": not job_state["printing"],
        }},
        temperature={},  # unknown until minimover's status format is confirmed
    )


@app.route("/api/job", methods=["GET", "POST"])
def api_job():
    err = check_api_key()
    if err: return err

    if request.method == "GET":
        with job_lock:
            js = dict(job_state)
        return jsonify(
            job={"file": {"name": js["filename"]}},
            progress={"completion": js["completion"] * 100 if js["filename"] else None},
            state=js["state_text"],
        )

    cmd = (request.json or {}).get("command")
    if cmd == "cancel":
        # minimover doesn't currently support cancel-mid-stream here;
        # documenting the gap rather than pretending to support it.
        return jsonify(error="Cancel not implemented"), 501
    return jsonify(error="Unsupported command"), 400


@app.route("/api/files", methods=["GET"])
@app.route("/api/files/local", methods=["GET", "POST"])
def api_files_local():
    err = check_api_key()
    if err: return err

    if request.method == "GET":
        files = [{"name": p.name, "origin": "local", "size": p.stat().st_size}
                 for p in UPLOAD_DIR.glob("*.gcode")]
        return jsonify(files=files)

    f = request.files.get("file")
    if not f:
        return jsonify(error="No file in request"), 400
    dest = UPLOAD_DIR / f.filename
    f.save(dest)

    want_print = request.form.get("print", "false").lower() == "true"
    if want_print:
        if not start_print(dest):
            return jsonify(error="Printer busy"), 409

    return jsonify(
        done=True,
        files={"local": {"name": f.filename, "origin": "local"}},
    ), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

# ---------------------------------------------------------------------
# See install.sh for the full automated setup, including the systemd
# unit and an /etc/davinci/config.env file that sets DAVINCI_* env
# vars picked up above.
# ---------------------------------------------------------------------
