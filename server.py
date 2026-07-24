#!/usr/bin/env python3
"""
server.py

A small LAN print server for 3D printers that don't speak standard
gcode-over-serial, backed by a pluggable printer driver (see
printers/base.py). Ships with a driver for the XYZprinting da Vinci
1.0 Pro, using the minimover CLI to convert uploads to .3w and stream
them over USB.

Provides two things:
  1. A plain browser UI at http://<pi-ip>:5000/  -- upload a file, see
     the file list, hit Print / Delete.
  2. A minimal subset of OctoPrint's REST API, so Cura and
     OrcaSlicer's built-in "OctoPrint" network-printing option can
     talk to this server directly (Settings -> Printers -> connect via
     OctoPrint, point it at this Pi's IP and port 5000, any API key
     you like unless DAVINCI_API_KEY is set).

Requires: pip3 install flask --break-system-packages

Run:
    python3 server.py
Then browse to http://<pi-ip>:5000/

--------------------------------------------------------------------
IMPORTANT CAVEATS (read before relying on this):

- Only ONE print job is supported at a time; a second request while a
  job is converting or printing is rejected.
- Progress reporting is a best-effort ESTIMATE based on elapsed time
  vs. a file-size heuristic, NOT real telemetry -- see each driver's
  status()/estimate_seconds() docstrings for what would need to change
  to make this exact.
- API key checking is OFF by default (LAN convenience). Set
  DAVINCI_API_KEY in /etc/davinci/config.env to require one -- do this
  if the Pi is reachable beyond your trusted LAN.
- Which printer this talks to is controlled by DAVINCI_PRINTER (see
  printers/__init__.py for the list of registered drivers). Adding a
  new printer is a matter of writing one new driver module -- nothing
  here needs to change.
--------------------------------------------------------------------
"""

import os
import threading
import time
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string

from printers import get_driver_class

# ---- Configuration ---------------------------------------------------
# All of these can be overridden with environment variables, so a
# packaged install doesn't require editing this file. See install.sh /
# the systemd unit for where these get set (/etc/davinci/config.env).

PRINTER_ID = os.environ.get("DAVINCI_PRINTER", "davinci_1_0_pro")
UPLOAD_DIR = Path(os.environ.get("DAVINCI_UPLOAD_DIR", str(Path.home() / "davinci" / "uploads")))
CONVERTED_DIR = UPLOAD_DIR / ".converted"
API_KEY = os.environ.get("DAVINCI_API_KEY") or None  # unset/empty = no auth required
PORT = int(os.environ.get("DAVINCI_PORT", "5000"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

driver = get_driver_class(PRINTER_ID).from_env()

app = Flask(__name__)

# ---- Shared print-job state -------------------------------------------

job_lock = threading.Lock()
job_state = {
    "printing": False,       # true during both the convert and print phases
    "phase": None,            # "converting" | "printing" | None
    "filename": None,
    "started_at": None,
    "completion": 0.0,        # 0.0 - 1.0, estimated
    "state_text": "Operational",
    "last_error": None,
}


def run_print_job(path: Path):
    start = time.time()

    with job_lock:
        job_state.update(
            printing=True, phase="converting", filename=path.name, started_at=start,
            completion=0.0, state_text="Converting", last_error=None,
        )

    try:
        native_path = driver.convert(path, CONVERTED_DIR)
    except Exception as exc:
        with job_lock:
            job_state.update(
                printing=False, phase=None, completion=0.0,
                state_text="Error", last_error=str(exc)[-500:],
            )
        return

    total_est = driver.estimate_seconds(native_path)
    with job_lock:
        job_state.update(phase="printing", state_text="Printing", completion=0.0)

    proc = driver.print_file(native_path)
    print_start = time.time()

    while proc.poll() is None:
        elapsed = time.time() - print_start
        with job_lock:
            job_state["completion"] = min(0.98, elapsed / total_est)
        time.sleep(2)

    output = proc.stdout.read() if proc.stdout else ""
    ok = proc.returncode == 0

    with job_lock:
        job_state.update(
            printing=False, phase=None,
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
<title>{{ printer_name }}</title>
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
<h1>{{ printer_name }}</h1>

<div id="status">Loading status...</div>

<form id="uploadForm" enctype="multipart/form-data">
  <input type="file" name="file" accept="{{ accepts_extension }}" required>
  <button type="submit">Upload</button>
</form>

<h2>Files</h2>
<div id="files">Loading...</div>

<script>
async function refresh() {
  const s = await (await fetch('/status')).json();
  const statusDiv = document.getElementById('status');
  if (s.printing) {
    const label = s.phase === 'converting' ? 'Converting' : 'Printing';
    statusDiv.innerHTML = `${label} <b>${s.filename}</b>` +
      (s.phase === 'printing' ? ` &mdash; ${Math.round(s.completion * 100)}% (estimated)` : '') +
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
    return render_template_string(
        PAGE, printer_name=driver.display_name, accepts_extension=driver.accepts_extension,
    )


@app.route("/files")
def list_files():
    return jsonify(sorted(p.name for p in UPLOAD_DIR.glob(f"*{driver.accepts_extension}")))


@app.route("/status")
def status():
    with job_lock:
        return jsonify(dict(job_state))


@app.route("/printer-status")
def printer_status():
    """Raw connectivity/diagnostic check, independent of any job --
    hits the driver directly rather than reporting job_state."""
    return jsonify(driver.status())


@app.route("/upload", methods=["POST"])
def web_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(driver.accepts_extension):
        return jsonify(error=f"Expected a {driver.accepts_extension} file"), 400
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
# POST /api/files/local with the file and form fields
# select=true/print=true to upload-and-print in one step.

@app.route("/api/version")
def api_version():
    err = check_api_key()
    if err: return err
    return jsonify(api="0.1", server="1.9.0", text=f"OctoPrint 1.9.0 ({driver.display_name} shim)")


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
        printing = job_state["printing"]
    return jsonify(
        state={"text": state_text, "flags": {
            "operational": True,
            "printing": printing,
            "error": state_text == "Error",
            "ready": not printing,
        }},
        temperature={},  # unknown -- driver-dependent, not implemented
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
        # Cancel-mid-stream isn't implemented by any driver yet;
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
                 for p in UPLOAD_DIR.glob(f"*{driver.accepts_extension}")]
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
# vars picked up above. See davinci-reset (installed to
# /usr/local/bin) for clearing uploads/config/WiFi without re-running
# the whole installer.
# ---------------------------------------------------------------------
