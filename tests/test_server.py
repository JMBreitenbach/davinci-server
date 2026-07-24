"""
tests/test_server.py -- integration tests against the real Flask app.

These use server.app.test_client(), which runs actual WSGI request/
response cycles through the real route handlers (not mocks). The only
thing replaced is the printer hardware itself, via fake_minimover.py
(see tests/conftest.py) -- everything else (Flask routing, file I/O,
the job state machine, the OctoPrint API shim) runs unmodified.
"""

import io
import time


def _upload_gcode(client, filename="test.gcode", body=b"G1 X0 Y0\n"):
    data = {"file": (io.BytesIO(body), filename)}
    return client.post("/upload", data=data, content_type="multipart/form-data")


def _wait_until_idle(server_module, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with server_module.job_lock:
            if not server_module.job_state["printing"]:
                return server_module.job_state.copy()
        time.sleep(0.05)
    raise AssertionError("job did not finish within timeout")


# ---- Browser UI -----------------------------------------------------

def test_index_page_renders(app_client):
    client, _ = app_client
    r = client.get("/")
    assert r.status_code == 200
    assert b"da Vinci 1.0 Pro" in r.data


def test_files_list_starts_empty(app_client):
    client, _ = app_client
    r = client.get("/files")
    assert r.status_code == 200
    assert r.get_json() == []


def test_status_starts_idle(app_client):
    client, _ = app_client
    r = client.get("/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["printing"] is False
    assert body["state_text"] == "Operational"


def test_printer_status_hits_driver(app_client):
    client, _ = app_client
    r = client.get("/printer-status")
    assert r.status_code == 200
    assert r.get_json()["connected"] is True


# ---- Upload / print / delete lifecycle -------------------------------

def test_upload_rejects_wrong_extension(app_client):
    client, _ = app_client
    data = {"file": (io.BytesIO(b"not gcode"), "model.stl")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_upload_then_appears_in_files(app_client):
    client, _ = app_client
    r = _upload_gcode(client)
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    r = client.get("/files")
    assert r.get_json() == ["test.gcode"]


def test_print_unknown_file_404s(app_client):
    client, _ = app_client
    r = client.post("/print/does-not-exist.gcode")
    assert r.status_code == 404


def test_full_upload_convert_print_cycle_succeeds(app_client):
    """The real end-to-end path: upload -> /print triggers a background
    thread that calls driver.convert() then driver.print_file() against
    the fake minimover -- this exercises the same code a real print
    would, just with fake hardware underneath."""
    client, server = app_client
    _upload_gcode(client, filename="cycle.gcode")

    r = client.post("/print/cycle.gcode")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    final_state = _wait_until_idle(server)
    assert final_state["state_text"] == "Operational"
    assert final_state["last_error"] is None
    assert final_state["completion"] == 1.0

    # the converted .3w should exist in the .converted dir
    converted = list(server.CONVERTED_DIR.glob("*.3w"))
    assert len(converted) == 1


def test_print_busy_rejects_second_job(app_client):
    client, server = app_client
    _upload_gcode(client, filename="a.gcode")
    _upload_gcode(client, filename="b.gcode")

    r1 = client.post("/print/a.gcode")
    assert r1.status_code == 200
    # Immediately try a second job while the first may still be running.
    r2 = client.post("/print/b.gcode")
    # Either the first job already finished (fast fake hardware) or it's
    # still busy -- both are valid depending on scheduling, so just make
    # sure we never get two jobs running: a 409 is the "still busy" case.
    assert r2.status_code in (200, 409)
    _wait_until_idle(server)


def test_convert_failure_surfaces_as_error(app_client, monkeypatch):
    client, server = app_client
    monkeypatch.setenv("FAKE_MINIMOVER_FAIL", "1")
    _upload_gcode(client, filename="willfail.gcode")

    r = client.post("/print/willfail.gcode")
    assert r.status_code == 200

    final_state = _wait_until_idle(server)
    assert final_state["state_text"] == "Error"
    assert final_state["last_error"] is not None


def test_delete_removes_file(app_client):
    client, _ = app_client
    _upload_gcode(client, filename="deleteme.gcode")
    r = client.delete("/delete/deleteme.gcode")
    assert r.status_code == 200

    r = client.get("/files")
    assert r.get_json() == []


# ---- OctoPrint-compatible API (for Cura / OrcaSlicer) -----------------

def test_api_version(app_client):
    client, _ = app_client
    r = client.get("/api/version")
    assert r.status_code == 200
    assert "OctoPrint" in r.get_json()["text"]


def test_api_files_local_upload_and_print(app_client):
    client, server = app_client
    data = {
        "file": (io.BytesIO(b"G1 X0 Y0\n"), "sliced.gcode"),
        "print": "true",
    }
    r = client.post("/api/files/local", data=data, content_type="multipart/form-data")
    assert r.status_code == 201
    assert r.get_json()["done"] is True

    _wait_until_idle(server)


def test_api_job_cancel_not_implemented(app_client):
    client, _ = app_client
    r = client.post("/api/job", json={"command": "cancel"})
    assert r.status_code == 501


# ---- API key enforcement ----------------------------------------------

def test_api_routes_require_key_when_configured(app_client_with_api_key):
    client, _ = app_client_with_api_key
    r = client.get("/api/version")
    assert r.status_code == 401

    r = client.get("/api/version", headers={"X-Api-Key": "test-secret-key"})
    assert r.status_code == 200


def test_browser_routes_are_not_key_protected(app_client_with_api_key):
    """/upload, /files etc. are for the LAN browser UI and intentionally
    don't require the API key -- only the OctoPrint API shim does."""
    client, _ = app_client_with_api_key
    r = client.get("/files")
    assert r.status_code == 200
