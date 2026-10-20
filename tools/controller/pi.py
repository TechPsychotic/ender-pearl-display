"""The connection to the Pi: SSH (one shared control connection) and the Ender Pearl web API.

The API token is read over SSH from the Pi (<root>/ui/token.txt) on every connect and only kept in memory.
Settings (host, user, project folder, the Pi's MAC address for finding it again) live in
~/.config/ender-pearl-controller/config.json."""
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request

CONF_DIR = os.path.join(os.path.expanduser("~"), ".config", "ender-pearl-controller")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "ender-pearl-controller")
CONF = os.path.join(CONF_DIR, "config.json")
SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "epc-%r@%h")   # short: Unix socket paths are limited
DEFAULTS = {"host": "raspberrypi.local", "user": "rpi4", "root": "closedloop", "port": 8080,
            "host_key_alias": "raspberrypi.local", "mac": ""}
PI_OUIS = ("b8:27:eb", "dc:a6:32", "e4:5f:01", "d8:3a:dd", "2c:cf:67", "28:cd:c1")   # Raspberry Pi network chips


def load_config():
    try:
        with open(CONF) as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(cfg):
    os.makedirs(CONF_DIR, exist_ok=True)
    keep = {k: cfg[k] for k in DEFAULTS if k in cfg}
    with open(CONF, "w") as f:
        json.dump(keep, f, indent=1)


class ApiError(RuntimeError):
    pass


class Pi:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = None
        os.makedirs(CACHE_DIR, exist_ok=True)

    # ---------------------------------------------------------------- ssh
    def _ssh_base(self):
        c = self.cfg
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-o", "ServerAliveInterval=10",
                "-o", "ControlMaster=auto", "-o", f"ControlPath={SOCK}", "-o", "ControlPersist=180"]
        if c.get("host_key_alias"):
            argv += ["-o", f"HostKeyAlias={c['host_key_alias']}"]
        return argv + [f"{c['user']}@{c['host']}"]

    def remote(self, cmd):
        """A shell command run in the project folder on the Pi."""
        return f"cd ~/{shlex.quote(self.cfg['root'])} && {cmd}"

    def run(self, cmd, timeout=30):
        r = subprocess.run(self._ssh_base() + [self.remote(cmd)], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def popen(self, cmd, stdin=False):
        """A long-running command (log tail, flashing, the bench): line-buffered text pipes."""
        return subprocess.Popen(self._ssh_base() + [self.remote(cmd)], stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def scp(self, local, remote_rel):
        c = self.cfg
        argv = ["scp", "-q", "-o", "BatchMode=yes", "-o", f"ControlPath={SOCK}"]
        if c.get("host_key_alias"):
            argv += ["-o", f"HostKeyAlias={c['host_key_alias']}"]
        r = subprocess.run(argv + [local, f"{c['user']}@{c['host']}:{c['root']}/{remote_rel}"], capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or "scp failed")

    def close(self):
        subprocess.run(self._ssh_base()[:-1] + ["-O", "exit", self._ssh_base()[-1]], capture_output=True)

    # ---------------------------------------------------------------- connect
    def connect(self):
        rc, out, err = self.run("cat ui/token.txt", timeout=15)
        if rc:
            raise RuntimeError((err or out).strip() or f"ssh failed ({rc})")
        self.token = out.strip()
        state = self.api("GET", "/api/state")
        mac = self.mac_of(self.cfg["host"])
        if mac:
            self.cfg["mac"] = mac
        return state

    # ---------------------------------------------------------------- web API
    def _url(self, path):
        return f"http://{self.cfg['host']}:{self.cfg['port']}{path}"

    def api(self, method, path, body=None, timeout=10, raw=False):
        if not self.token:
            raise ApiError("not connected")
        req = urllib.request.Request(self._url(path), method=method, headers={"X-Token": self.token, "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error")
            except ValueError:
                msg = None
            raise ApiError(msg or f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"web server not reachable: {getattr(e, 'reason', e)}") from None
        return data if raw else json.loads(data or b"{}")

    def asset(self, name):
        """A picture or font of the display, cached on disk (they only change with a firmware rebuild)."""
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        path = os.path.join(CACHE_DIR, "assets", safe)
        if not os.path.exists(path):
            data = self.api("GET", "/api/display/asset?f=" + urllib.parse.quote(name), raw=True, timeout=30)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
        return path

    def knob(self, op, d=None):
        self.api("POST", "/api/display/input", {"op": op, **({"d": d} if d is not None else {})}, timeout=4)

    def printing(self):
        st = self.api("GET", "/api/state", timeout=5)
        return bool(st.get("printing") or st.get("sd"))

    # ---------------------------------------------------------------- finding the Pi on the network
    @staticmethod
    def mac_of(host):
        try:
            ip = socket.gethostbyname(host)
        except OSError:
            return None
        out = subprocess.run(["ip", "neigh", "show", ip], capture_output=True, text=True).stdout
        m = re.search(r"lladdr ([0-9a-f:]{17})", out)
        return m.group(1) if m else None

    @staticmethod
    def find(mac=""):
        """The Pi's IP address: by its MAC address (or any Raspberry Pi MAC) after pinging the local subnet."""
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True).stdout
        nets = []
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", out):
            n = ipaddress.ip_interface(m.group(1)).network
            if n.prefixlen >= 20 and not str(n).startswith("172.17."):   # not docker, not huge
                nets.append(n)
        procs = [subprocess.Popen(["ping", "-c1", "-W1", str(h)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for n in nets for h in n.hosts()]
        for p in procs:
            p.wait()
        neigh = subprocess.run(["ip", "neigh"], capture_output=True, text=True).stdout.lower()
        rows = re.findall(r"^(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-f:]{17})", neigh, re.M)
        for ip, m in rows:
            if mac and m == mac.lower():
                return ip
        for ip, m in rows:
            if m.startswith(PI_OUIS):
                return ip
        return None
