"""API for the printer display (display/glass, Ender Pearl UI) and the web UI's Printer screen card.

    GET  /api/display/config            display settings (wallpaper, brightness, sleep, clock, message, show)
    POST /api/display/config            merge settings; {"message": "text"} pushes a message to the screen
    GET  /api/display/files             G-code files, newest first, with the print time from the file
    GET  /api/display/preview?name&n&w&h   walls of layer n as polylines in a w x h box (live preview)
    GET  /api/display/model?name&w&h       top view of the model (file details)
    GET  /api/display/objects?name&w&h     outline of every object (skip an object)
    GET  /api/display/wallpapers        wallpapers built into the display firmware (display/glass/manifest.json)
    GET  /api/display/frame             what the screen shows now: TJC drawing commands since the last full redraw
    GET  /api/display/asset?f=          a picture or font of the display (for the web UI's live preview)
    POST /api/display/input             {"op": "turn", "d": ±1..5} | {"op": "press"} | {"op": "long"}: the knob, remotely
                                        (desktop controller); forwarded to the display app on 127.0.0.1:INPUT_PORT
    POST /api/display/upload            {"name", "data": base64 image} -> queued for a firmware build on the laptop
    GET  /api/display/uploads           the build queue
Previews are simplified to at most a few hundred short lines (drawn over the serial link). Parsing a large G-code file
takes ~15 s on the Pi, so a low-priority background thread builds every job's previews ahead of time (whole plate, objects,
and every layer's outline for the live preview) and keeps them in out/preview_cache/, keyed by file time and size."""
import collections
import json
import os
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "out", "display_config.json")
FRAME = os.path.join(ROOT, "out", "display_frame.json")
ASSETS = os.path.join(ROOT, "display", "glass", "assets")
UPLOADS = os.path.join(ROOT, "out", "wallpaper_queue")
MANIFEST = os.path.join(ROOT, "display", "glass", "manifest.json")
PVDIR = os.path.join(ROOT, "out", "preview_cache")
PV_VER = 2                       # bump when the preview drawing changes, so old cache files are rebuilt
SIZES = {"model": (204, 88), "objects": (204, 150), "live": (98, 70)}   # what the display asks for (glass/app.py)
DEFAULTS = {"wallpaper": "neon-bedgrid", "brightness": 80, "sleep_s": 300, "clock24": True, "message": None, "show": None}
WALLS = ("External perimeter", "Perimeter", "Overhang perimeter")
EST = re.compile(r";\s*estimated printing time(?: \(normal mode\))?\s*=\s*(.+)")
_cache, _est = {}, {}
srv = None   # the server module (set by register)


def register(server_module, routes):
    global srv
    srv = server_module
    routes.update({("GET", "/api/display/config"): lambda q, b: get_config(), ("POST", "/api/display/config"): post_config,
                   ("GET", "/api/display/files"): lambda q, b: files(), ("GET", "/api/display/preview"): preview,
                   ("GET", "/api/display/model"): model, ("GET", "/api/display/objects"): objects,
                   ("GET", "/api/display/wallpapers"): lambda q, b: wallpapers(),
                   ("GET", "/api/display/frame"): lambda q, b: frame(), ("GET", "/api/display/asset"): asset,
                   ("POST", "/api/display/upload"): upload, ("POST", "/api/display/input"): post_input, ("GET", "/api/display/uploads"): lambda q, b: uploads()})
    threading.Thread(target=_warm, daemon=True, name="preview-cache").start()


def frame():
    try:
        with open(FRAME) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"v": None, "cmds": []}


def asset(q, body):
    """Only files that are part of the display: manifest pictures and the four font files."""
    f = q.get("f", [""])[0]
    allowed = set(_manifest().get("pictures", [])) | {"fonts/" + n for n in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "epicons.ttf")}
    if f not in allowed:
        raise ValueError("unknown display asset")
    with open(os.path.join(ASSETS, f), "rb") as fh:
        return fh.read()


def _manifest():
    try:
        with open(MANIFEST) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def upload(q, body):
    """A new wallpaper: stored in out/wallpaper_queue/ for the laptop build service (the display checks its firmware's
    checksums, so pictures can only be added by rebuilding the firmware with the TJC editor)."""
    import base64
    req = json.loads(body or b"{}")
    name = re.sub(r"[^a-z0-9]+", "-", str(req.get("name", "")).lower()).strip("-")[:24]
    if not name:
        raise ValueError("give the wallpaper a name")
    if name in wallpapers()["names"]:
        raise ValueError(f"{name!r} is already built in")
    data = base64.b64decode(req.get("data", ""), validate=True)
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"):
        raise ValueError("send a PNG or JPEG image")
    if len(data) > 8_000_000:
        raise ValueError("image too large (max 8 MB)")
    os.makedirs(UPLOADS, exist_ok=True)
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    path = os.path.join(UPLOADS, name + ext)
    with open(path, "wb") as f:
        f.write(data)
    q_ = uploads()
    q_["items"] = [x for x in q_["items"] if x["name"] != name] + [{"name": name, "file": name + ext, "added": time.time(), "status": "waiting for the laptop build"}]
    with open(os.path.join(UPLOADS, "queue.json"), "w") as f:
        json.dump(q_, f)
    return q_


def uploads():
    try:
        with open(os.path.join(UPLOADS, "queue.json")) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"items": []}


def get_config():
    try:
        with open(CONFIG) as f:
            return {**DEFAULTS, **json.load(f)}
    except (FileNotFoundError, ValueError):
        return dict(DEFAULTS)


INPUT_PORT = 47321   # display/glass_main.py listens here (localhost only) for knob input from the API


def post_input(q, body):
    """The knob, from elsewhere (tools/controller): one turn / press / long press, sent to the display app as a datagram."""
    import socket
    req = json.loads(body or b"{}")
    op = req.get("op")
    if op not in ("turn", "press", "long"):
        raise ValueError("op must be turn, press or long")
    msg = {"op": op}
    if op == "turn":
        msg["d"] = max(-5, min(5, int(req.get("d", 1)))) or 1
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(json.dumps(msg).encode(), ("127.0.0.1", INPUT_PORT))
    finally:
        s.close()
    return {"ok": True}


def post_config(q, body):
    req = json.loads(body or b"{}")
    cfg = get_config()
    walls = wallpapers()["names"]
    if "wallpaper" in req:
        if req["wallpaper"] not in walls:
            raise ValueError(f"unknown wallpaper {req['wallpaper']!r} (built in: {', '.join(walls)})")
        cfg["wallpaper"] = req["wallpaper"]
    if "brightness" in req:
        cfg["brightness"] = max(10, min(100, int(req["brightness"])))
    if "sleep_s" in req:
        cfg["sleep_s"] = max(30, min(3600, int(req["sleep_s"])))
    if "clock24" in req:
        cfg["clock24"] = bool(req["clock24"])
    if req.get("message"):
        cfg["message"] = {"id": int(time.time() * 1000), "text": str(req["message"])[:200]}
    if req.get("show") in ("home", "print", "prepare", "control", "level"):
        cfg["show"] = {"id": int(time.time() * 1000), "screen": req["show"]}
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f)
    os.replace(tmp, CONFIG)
    return cfg


def wallpapers():
    try:
        with open(MANIFEST) as f:
            m = json.load(f)
        names = list(m["wallpapers"])
    except (FileNotFoundError, ValueError, KeyError):
        names = [DEFAULTS["wallpaper"]]
    return {"names": names, "titles": {n: n.replace("-", " ").title() for n in names}}


def estimate(path):
    """'1h 19m' from the slicer's comment near the end of the file (cached by size and time)."""
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key not in _est:
        val = None
        with open(path, "rb") as f:
            f.seek(max(0, st.st_size - 40000))
            for line in f.read().decode(errors="replace").splitlines():
                m = EST.match(line)
                if m:
                    val = m.group(1).strip()
        if val:   # "1h 19m 1s" -> "1h 19m"; "18m 20s" -> "18 min"
            parts = dict((u, int(n)) for n, u in re.findall(r"(\d+)([dhms])", val))
            h = parts.get("d", 0) * 24 + parts.get("h", 0)
            val = f"{h}h {parts.get('m', 0):02d}m" if h else f"{max(1, parts.get('m', 0))} min"
        _est[key] = val
    return _est[key]


def files():
    out = []
    for n in os.listdir(srv.JOBS):
        p = os.path.join(srv.JOBS, n)
        if n.endswith(".gcode") and srv.NAME_OK.match(n):
            try:
                out.append({"name": n, "mtime": os.path.getmtime(p), "estimate": estimate(p)})
            except OSError:
                pass
    out.sort(key=lambda f: -f["mtime"])   # newest first (modification time)
    return {"files": out}


def _box(info, w, h, pad=2):
    x0, y0, x1, y1 = info["bbox"]
    s = min((w - 2 * pad) / max(1e-6, x1 - x0), (h - 2 * pad) / max(1e-6, y1 - y0))
    ox = pad + ((w - 2 * pad) - (x1 - x0) * s) / 2
    oy = pad + ((h - 2 * pad) - (y1 - y0) * s) / 2
    return lambda x, y: (int(round(ox + (x - x0) * s)), int(round(h - 1 - (oy + (y - y0) * s))))   # bed y up -> screen down


def _polys(moves, kinds, tf, want=WALLS, obj=None, min_px=2, cap=500):
    """Walls as screen polylines. A move that continues the current polyline (starts within min_px of its end) is
    added to it, and every point is kept only if it is at least min_px from the last kept one, so a larger min_px
    really thins dense layers instead of leaving one point per tiny move."""
    names = set(want)
    out, n = [], 0
    tol = 1.5   # only true continuations are joined (a larger tolerance would draw chords between separate features)
    near = lambda a, b, t: abs(a[0] - b[0]) + abs(a[1] - b[1]) <= t
    for mv in moves:
        ext, o, pts, kind = mv[0], mv[1], mv[2], mv[3]
        if not ext or kinds[kind] not in names or (obj is not None and o != obj) or not pts:
            continue
        P = [tf(x, y) for x, y in pts]
        if out and near(out[-1][-1], P[0], tol):
            cur = out[-1]
        else:
            cur = [P[0]]; out.append(cur); n += 1
        for q in P[1:]:
            if not near(q, cur[-1], min_px - 1e-9):
                cur.append(q); n += 1
        if n > cap:
            break
    return [q if len(q) > 1 else [q[0], (q[0][0] + 1, q[0][1])] for q in out]   # a lone point = a tiny stroke


def _plan(name):
    return srv.load_plan(srv.safe_path(name))


def _iso_frame(info, w, h, pad=2):
    """Isometric projection from the front left, height up, scaled to fit the whole model in w x h.
    Returns tf_at(z) -> (x, y) -> screen point, and the model height."""
    import math
    zs = info["z"]; zmax = max(zs) or 1
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    proj = lambda x, y, z: ((x - y) * c30, -((x + y) * s30 + z))
    x0, y0, x1, y1 = info["bbox"]
    corners = [proj(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (0, zmax)]
    u0, u1 = min(p[0] for p in corners), max(p[0] for p in corners)
    v0, v1 = min(p[1] for p in corners), max(p[1] for p in corners)
    sc = min((w - 2 * pad) / max(1e-6, u1 - u0), (h - 2 * pad) / max(1e-6, v1 - v0))
    ou, ov = pad + ((w - 2 * pad) - (u1 - u0) * sc) / 2, pad + ((h - 2 * pad) - (v1 - v0) * sc) / 2
    tf_at = lambda z: (lambda x, y: (int(round(ou + (proj(x, y, z)[0] - u0) * sc)), int(round(ov + (proj(x, y, z)[1] - v0) * sc))))
    return tf_at, zmax


def _iso_layer(info, moves, tf, per):
    """One layer's outer walls, simplified to about per points."""
    px = 1.5   # simplify the whole layer (never cut it off): coarser until it fits its share of the budget
    while True:
        polys = _polys(moves, info["kinds"], tf, want=("External perimeter", "Overhang perimeter"), min_px=px, cap=10 ** 9)
        if sum(len(q) for q in polys) <= per * 1.5 or px > 6:   # small shapes stay round; budget enforced below
            break
        px *= 1.6
    ext = lambda q: max(max(a[0] for a in q) - min(a[0] for a in q), max(a[1] for a in q) - min(a[1] for a in q))
    keep, used = [], 0
    for q in sorted(polys, key=ext, reverse=True):   # still over budget: the largest outlines first, specks go
        if keep and (used + len(q) > per * 1.5 or ext(q) < 2):
            continue
        keep.append(q); used += len(q)
    return keep


def _iso_idx(L, nlayers=22):
    return sorted({round(i * (L - 1) / max(1, nlayers - 1)) for i in range(nlayers)})


def _iso(info, layers, w, h, upto=None, nlayers=22, cap=1400, pad=2):
    """The whole model in 3D: outer walls of nlayers evenly spaced layers (plus the current one), isometric from the
    front left, height up. Each path: [points, level 0..1 (height), done (layer <= upto, or True)]."""
    L = len(layers)
    idx = sorted(set(_iso_idx(L, nlayers)) | ({upto} if upto is not None and 0 <= upto < L else set()))
    tf_at, zmax = _iso_frame(info, w, h, pad)
    out, per = [], max(20, cap // len(idx))   # every sampled layer gets an equal share of the point budget
    for i in idx:
        z = info["z"][i]
        for poly in _iso_layer(info, layers[i], tf_at(z), per):
            out.append([poly, round(z / zmax, 3), upto is None or i <= upto])
    return out


def _live_layers(info, layers, w, h, nlayers=22, cap=1400):
    """For the live preview: every layer's outline (any layer can be the current one) and the evenly spaced layers."""
    idx = _iso_idx(len(layers), nlayers)
    tf_at, zmax = _iso_frame(info, w, h)
    per = max(20, cap // (len(idx) + 1))      # the current layer is not one of idx: one more layer shares the budget
    per_in = max(20, cap // len(idx))         # it is: idx alone
    lay = lambda i, p: _iso_layer(info, layers[i], tf_at(info["z"][i]), p)
    return {"idx": idx, "level": [round(z / zmax, 3) for z in info["z"]],
            "layers": [lay(i, per) for i in range(len(layers))], "idx_layers": {str(i): lay(i, per_in) for i in idx}}


def _live_from(pv, n):
    n = min(len(pv["layers"]) - 1, max(0, n))
    if n in pv["idx"]:
        return {"n": n, "paths": [[poly, pv["level"][i], i <= n] for i in pv["idx"] for poly in pv["idx_layers"][str(i)]]}
    return {"n": n, "paths": [[poly, pv["level"][i], i <= n] for i in sorted(set(pv["idx"]) | {n}) for poly in pv["layers"][i]]}


def _objects(info, layers, w, h):
    i = min(len(layers) - 1, 1)
    tf = _box(info, w, h)
    return [{"name": oname, "paths": _polys(layers[i], info["kinds"], tf, want=("External perimeter",), obj=k, cap=200)}
            for k, oname in enumerate(info.get("objects") or [])]


# ---- preview cache on disk: built ahead of time for every job by a background thread ----
_building = {}           # name -> Event while some thread builds it
_mem = collections.OrderedDict()   # cache file -> previews, the last few used
_build_lock = threading.Lock()


def _cache_file(name):
    """out/preview_cache/<job>.<mtime>.<size>.v<PV_VER>.json: the name says which file version it was built from."""
    st = os.stat(srv.safe_path(name))
    return os.path.join(PVDIR, f"{name}.{int(st.st_mtime)}.{st.st_size}.v{PV_VER}.json")


def _cached(name, load=True):
    """The prebuilt previews of a job (the last few stay in memory), or None if missing or out of date."""
    try:
        path = _cache_file(name)
        if path in _mem:
            _mem.move_to_end(path)
            return _mem[path]
        if not os.path.exists(path):
            return None
        if not load:
            return True
        with open(path) as f:
            hit = json.load(f)
        _remember(path, hit)
        return hit
    except (OSError, ValueError):
        return None


def _remember(path, hit):
    _mem[path] = hit
    while len(_mem) > 4:
        _mem.popitem(last=False)


def _build(name, keep_plan=True):
    """Parse the job once and store all its previews. One build per file at a time; others wait for it."""
    with _build_lock:
        ev = _building.get(name)
        mine = ev is None
        if mine:
            ev = _building[name] = threading.Event()
    if not mine:
        ev.wait(120)
        hit = _cached(name)
        if not hit:
            raise RuntimeError("no preview for this file")
        return hit
    try:
        hit = _cached(name)
        if hit:
            return hit
        path = srv.safe_path(name)
        had = path in srv.plan_cache
        out = _cache_file(name)
        info, layers = srv.load_plan(path)
        if not info.get("bbox") or not layers:
            hit = {"model": {"paths": []}, "objects": {"objects": []}, "live": {"idx": [0], "level": [0], "layers": [[]], "idx_layers": {"0": []}}}
        else:
            hit = {"model": {"paths": _iso(info, layers, *SIZES["model"])},
                   "objects": {"objects": _objects(info, layers, *SIZES["objects"])},
                   "live": _live_layers(info, layers, *SIZES["live"])}
        if not keep_plan and not had:
            srv.plan_cache.pop(path, None)   # the warmer must not keep 48 parsed files in memory
        os.makedirs(PVDIR, exist_ok=True)
        with open(out + ".tmp", "w") as f:
            json.dump(hit, f, separators=(",", ":"))
        os.replace(out + ".tmp", out)
        if keep_plan:
            _remember(out, hit)
        return hit
    finally:
        with _build_lock:
            _building.pop(name, None)
        ev.set()


def _warm():
    """Background: keep every job's previews built (newest files first), and drop cache files of deleted jobs."""
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 15)   # Linux: nice applies per thread
    except (AttributeError, OSError):
        pass
    time.sleep(5)
    while True:
        try:
            names = [f["name"] for f in files()["files"]]
            for n in names:
                if _cached(n, load=False) is None:
                    t = time.time()
                    try:
                        _build(n, keep_plan=False)
                        print(f"preview cache: {n} ({time.time() - t:.1f} s)", flush=True)
                    except Exception as e:   # a broken file must not stop the others
                        print(f"preview cache: {n}: {e}", flush=True)
            if os.path.isdir(PVDIR):
                keep = set()
                for n in names:
                    try:
                        keep.add(os.path.basename(_cache_file(n)))
                    except OSError:
                        pass
                for f in os.listdir(PVDIR):
                    if f not in keep and not f.endswith(".tmp"):
                        os.remove(os.path.join(PVDIR, f))
        except Exception as e:
            print("preview cache:", e, flush=True)
        time.sleep(20)


def preview(q, body):
    """Live preview while printing: the whole model in 3D, layers up to n printed (teal), the rest grey."""
    name, n, w, h = q["name"][0], int(q["n"][0]), int(q.get("w", ["98"])[0]), int(q.get("h", ["70"])[0])
    if (w, h) == SIZES["live"]:
        return _live_from((_cached(name) or _build(name))["live"], n)
    key = ("pv", name, n, w, h)
    if key not in _cache:
        info, layers = _plan(name)
        n = min(len(layers) - 1, max(0, n))
        _cache[key] = {"n": n, "paths": _iso(info, layers, w, h, upto=n)}
    return _cache[key]


def _sample_layer(info, layers):
    """A layer that shows the model's shape: the one among a few samples with the most wall length."""
    cand = sorted({len(layers) // 2, len(layers) // 3, 2 * len(layers) // 3, min(len(layers) - 1, 2)})
    best, bestn = 0, -1
    for i in cand:
        n = sum(len(mv[2]) for mv in layers[i] if mv[0] and info["kinds"][mv[3]] in WALLS)
        if n > bestn:
            best, bestn = i, n
    return best


def model(q, body):
    """File details: the whole plate in 3D (all objects), shaded by height."""
    name, w, h = q["name"][0], int(q.get("w", ["204"])[0]), int(q.get("h", ["88"])[0])
    if (w, h) == SIZES["model"]:
        return (_cached(name) or _build(name))["model"]
    key = ("model", name, w, h)
    if key not in _cache:
        info, layers = _plan(name)
        _cache[key] = {"paths": _iso(info, layers, w, h)}
    return _cache[key]


def objects(q, body):
    name, w, h = q["name"][0], int(q.get("w", ["204"])[0]), int(q.get("h", ["150"])[0])
    if (w, h) == SIZES["objects"]:
        return (_cached(name) or _build(name))["objects"]
    key = ("objs", name, w, h)
    if key not in _cache:
        info, layers = _plan(name)
        _cache[key] = {"objects": _objects(info, layers, w, h)}
    return _cache[key]
