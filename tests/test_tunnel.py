"""Cloudflare Quick Tunnel manager and endpoints, with a fake cloudflared (a tiny Python script) instead of the real one."""
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.tunnel import Tunnel, is_local_request, parse_url

URL = "https://quiet-fox-1234.trycloudflare.com"
FAKE = "import sys, time\nprint('2026 INF Requesting new quick Tunnel', file=sys.stderr, flush=True)\n" \
       f"print('INF |  {URL}  |', file=sys.stderr, flush=True)\ntime.sleep(60)\n"
SILENT = "import time\ntime.sleep(60)\n"
CRASH = "import sys\nprint('ERR no network', file=sys.stderr)\nsys.exit(1)\n"


def launcher(script, ports=None):
    def launch(exe, port):
        if ports is not None:
            ports.append(port)
        return subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return launch


def test_parse_url():
    assert parse_url(f"2026-11-03T10:00:00Z INF |  {URL}  |") == URL
    assert parse_url("INF Requesting new quick Tunnel on trycloudflare.com...") is None
    assert parse_url('ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": EOF') is None
    assert parse_url("") is None


@pytest.mark.parametrize("host, client, headers, ok", [
    ("localhost:8000", "127.0.0.1", {}, True),
    ("127.0.0.1:8000", "127.0.0.1", {}, True),
    ("[::1]:8000", "::1", {}, True),
    ("localhost", "127.0.0.1", {"Origin": "http://localhost:8000"}, True),
    ("quiet-fox-1234.trycloudflare.com", "127.0.0.1", {}, False),             # through the tunnel: cloudflared connects locally
    ("localhost:8000", "127.0.0.1", {"cf-connecting-ip": "1.2.3.4"}, False),
    ("localhost:8000", "127.0.0.1", {"CF-Ray": "abc"}, False),
    ("localhost:8000", "127.0.0.1", {"Origin": "https://evil.example"}, False),
    ("192.168.0.5:8000", "192.168.0.7", {}, False),                           # another PC in the LAN
    ("localhost:8000", "192.168.0.7", {}, False),
    ("localhost:8000", "testclient", {}, False),
    (None, "127.0.0.1", {}, False),
])
def test_is_local_request(host, client, headers, ok):
    assert is_local_request(host, client, headers) is ok


def test_start_stop_status():
    ports = []
    t = Tunnel(finder=lambda: "fake", launcher=launcher(FAKE, ports), timeout=10)
    assert t.status() == {"available": True, "running": False, "url": None}
    assert t.start(8123) == URL and ports == [8123]
    assert t.status() == {"available": True, "running": True, "url": URL}
    assert t.start(8123) == URL and ports == [8123]   # already running: no second process
    proc = t._proc
    t.stop()
    assert proc.poll() is not None
    assert t.status()["running"] is False and t.status()["url"] is None
    t.stop()   # harmless twice


def test_start_errors():
    assert Tunnel(finder=lambda: None).status()["available"] is False
    with pytest.raises(RuntimeError, match="nicht installiert"):
        Tunnel(finder=lambda: None).start(8000)
    with pytest.raises(RuntimeError, match="beendet"):
        Tunnel(finder=lambda: "fake", launcher=launcher(CRASH), timeout=10).start(8000)
    t = Tunnel(finder=lambda: "fake", launcher=launcher(SILENT), timeout=0.5)
    with pytest.raises(RuntimeError, match="rechtzeitig"):
        t.start(8000)
    assert t._proc is None and not t.status()["running"]   # the silent process was stopped
    def broken(exe, port):
        raise FileNotFoundError("weg")
    with pytest.raises(RuntimeError, match="gestartet"):
        Tunnel(finder=lambda: "fake", launcher=broken).start(8000)


def make(tmp_path, tunnel, host="localhost:8000", client=("127.0.0.1", 50000)):
    return TestClient(create_app(tmp_path, tunnel=tunnel), base_url=f"http://{host}", client=client)


def test_endpoints_local(tmp_path):
    ports = []
    tun = Tunnel(finder=lambda: "fake", launcher=launcher(FAKE, ports), timeout=10)
    with make(tmp_path, tun) as c:
        assert c.get("/api/tunnel").json() == {"local": True, "available": True, "running": False, "url": None}
        r = c.post("/api/tunnel/start").json()
        assert r["url"] == URL and r["running"] and ports == [8000]
        assert c.get("/api/tunnel").json()["url"] == URL
        assert c.post("/api/tunnel/stop").json()["running"] is False
        tun.finder = lambda: None
        r = c.post("/api/tunnel/start")
        assert r.status_code == 400 and "cloudflared" in r.json()["detail"]
    assert tun._proc is None


def test_endpoints_forbidden_for_tunnel_requests(tmp_path):
    tun = Tunnel(finder=lambda: "fake", launcher=launcher(FAKE), timeout=10)
    cases = [
        make(tmp_path, tun, host="quiet-fox-1234.trycloudflare.com"),                 # Host of the tunnel, client is cloudflared on loopback
        make(tmp_path, tun, client=("testclient", 1)),                                 # not a loopback client
    ]
    forwarded = make(tmp_path, tun)
    forwarded.headers["cf-connecting-ip"] = "1.2.3.4"
    for c in cases + [forwarded]:
        assert c.post("/api/tunnel/start").status_code == 403
        assert "Spielleiter" in c.post("/api/tunnel/stop").json()["detail"]
        assert c.get("/api/tunnel").json() == {"local": False, "url": None}
    assert tun._proc is None
    # a visitor sees the url (it is public anyway) but may not control it
    tun.start(8000)
    try:
        assert forwarded.get("/api/tunnel").json() == {"local": False, "url": URL}
        assert forwarded.post("/api/tunnel/stop").status_code == 403 and tun.status()["running"]
    finally:
        tun.stop()
