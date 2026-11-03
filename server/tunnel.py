"""Optional Cloudflare Quick Tunnel (cloudflared child process) so friends can join over the internet.
Only the person at the host PC may start / stop it (is_local_request); everything else is injectable for tests."""
import glob
import ipaddress
import os
import re
import shutil
import subprocess
import threading
from urllib.parse import urlsplit

URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")   # not api.trycloudflare.com, which cloudflared names in its error lines
START_TIMEOUT = 30.0
# Headers that only appear on requests which came through the tunnel (or some other proxy).
FORWARD_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for")


def find_cloudflared():
    """Path of cloudflared.exe or None. PATH of a running server is not refreshed after a fresh winget install, so look in the usual places too."""
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    local, pf86, pf = (os.environ.get(k) for k in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"))
    candidates = []
    if local:
        candidates.append(os.path.join(local, "Microsoft", "WinGet", "Links", "cloudflared.exe"))
    if pf86:
        candidates.append(os.path.join(pf86, "cloudflared", "cloudflared.exe"))
    if pf:
        candidates.append(os.path.join(pf, "cloudflared", "cloudflared.exe"))
    if local:
        candidates += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "Cloudflare.cloudflared*", "cloudflared.exe")))
    return next((c for c in candidates if os.path.isfile(c)), None)


def launch_cloudflared(exe, port):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([exe, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace", creationflags=flags)
    proc.job = _kill_with_parent(proc)
    return proc


def _kill_with_parent(proc):
    """Windows: put the child into a job object that ends it when this server process ends in any way
    (window closed, crash), so no tunnel stays open without a server. Best effort; returns the job handle to keep."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("user_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                        ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("procs", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6), ("proc_mem", ctypes.c_size_t),
                        ("job_mem", ctypes.c_size_t), ("peak_proc_mem", ctypes.c_size_t), ("peak_job_mem", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        job = k32.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) \
                and k32.AssignProcessToJobObject(job, int(proc._handle)):   # 9 = JobObjectExtendedLimitInformation
            return job
    except (OSError, AttributeError):
        pass
    return None


def parse_url(line):
    m = URL_RE.search(line)
    return m.group(0) if m else None


def _hostname(host):
    host = (host or "").strip().lower()
    if host.startswith("["):
        return host[1:].split("]")[0]
    return host.split(":")[0] if host.count(":") == 1 else host


def is_loopback(addr):
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def is_local_request(host_header, client_host, headers=None):
    """True only for a browser on the host PC itself. A loopback client IP is not enough: cloudflared connects from 127.0.0.1 too,
    so the Host header must be a local name and no proxy headers may be present."""
    h = {k.lower(): v for k, v in (headers or {}).items()}
    if _hostname(host_header) not in ("localhost", "127.0.0.1", "::1"):
        return False
    if not is_loopback(client_host or ""):
        return False
    if any(k in h for k in FORWARD_HEADERS):
        return False
    origin = h.get("origin")   # a web page on another site must not be able to start the tunnel from the host's browser
    return not origin or (urlsplit(origin).hostname or "") in ("localhost", "127.0.0.1", "::1")


class Tunnel:
    def __init__(self, finder=find_cloudflared, launcher=launch_cloudflared, timeout=START_TIMEOUT):
        self.finder, self.launcher, self.timeout = finder, launcher, timeout
        self._proc = None
        self._url = None
        self._found = threading.Event()
        self._start_lock = threading.Lock()

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _read(self, proc):
        for line in proc.stderr:   # keep draining after the URL so the pipe never fills up
            if proc is self._proc and not self._url:
                url = parse_url(line)
                if url:
                    self._url = url
                    self._found.set()
        self._found.set()   # process ended: wake up start()

    def status(self):
        running = self._alive() and self._url is not None
        return {"available": self.finder() is not None, "running": running, "url": self._url if running else None}

    def start(self, port):
        """Returns the public URL; raises RuntimeError with a German message."""
        with self._start_lock:
            if self._alive() and self._url:
                return self._url
            self.stop()
            exe = self.finder()
            if not exe:
                raise RuntimeError("cloudflared ist nicht installiert.")
            self._url = None
            self._found = threading.Event()
            try:
                proc = self._proc = self.launcher(exe, port)
            except OSError as e:
                self._proc = None
                raise RuntimeError(f"cloudflared konnte nicht gestartet werden: {e}")
            threading.Thread(target=self._read, args=(proc,), daemon=True).start()
            if self._found.wait(self.timeout) and not self._url:   # stderr closed without a URL: the process is ending
                try:
                    proc.wait(2)
                except subprocess.TimeoutExpired:
                    pass
            if self._url and proc.poll() is None:
                return self._url
            died = proc.poll() is not None
            self.stop()
            raise RuntimeError("cloudflared wurde unerwartet beendet." if died else "Der Online-Link konnte nicht rechtzeitig erstellt werden. Internetverbindung prüfen und noch einmal versuchen.")

    def stop(self):
        proc, self._proc, self._url = self._proc, None, None
        self._found.set()
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(3)
            except subprocess.TimeoutExpired:
                pass
