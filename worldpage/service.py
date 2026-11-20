"""World page helper: serves /world/ for the stack.

Reads the world, the nightly backups and the old worlds (all mounted
read-only). Uploads and requests only go into the inbox folder; the host
job `world-inbox` (run by root from cron) carries them out.
"""
import json, os, re, shutil, sqlite3, tarfile, tempfile, time, zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote

WORLDS = os.environ.get("WORLDS", "/worlds")
WORLD = WORLDS + "/world"
BACKUPS = os.environ.get("BACKUPS", "/backups")
INBOX = os.environ.get("INBOX", "/inbox")
HERE = os.path.dirname(os.path.abspath(__file__))
MAX_UPLOAD = 4 << 30

BACKUP_RE = re.compile(r"^world-\d{4}-\d{2}-\d{2}\.tar\.gz$")
OLD_RE = re.compile(r"^world\.bak-\d{8}-\d{6}$")


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def read_conf(path):
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def db_ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)


def query(path, sql):
    try:
        con = db_ro(path)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None


def list_backups():
    out = []
    try:
        names = os.listdir(BACKUPS)
    except OSError:
        return out
    for n in sorted(names, reverse=True):
        p = os.path.join(BACKUPS, n)
        if BACKUP_RE.match(n) and os.path.isfile(p):
            st = os.stat(p)
            out.append({"name": n, "size": st.st_size, "time": int(st.st_mtime)})
    return out


def list_old():
    out = []
    for n in sorted(os.listdir(WORLDS), reverse=True):
        p = os.path.join(WORLDS, n)
        if OLD_RE.match(n) and os.path.isdir(p):
            d = n[10:]  # YYYYMMDD-HHMMSS, the server's local time
            out.append({"name": n, "size": dir_size(p),
                        "when": "%s-%s-%s %s:%s" % (d[:4], d[4:6], d[6:8], d[9:11], d[11:13])})
    return out


def job_state():
    st = {"busy": os.path.exists(INBOX + "/request")
          or os.path.exists(INBOX + "/running")}
    try:  # a request nobody picked up: the cron job isn't running
        st["waiting"] = int(time.time() - os.stat(INBOX + "/request").st_mtime)
    except OSError:
        st["waiting"] = 0
    try:
        with open(INBOX + "/status", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        st.update(state=lines[0], message=lines[1] if len(lines) > 1 else "",
                  log="\n".join(lines[2:])[-4000:],
                  time=int(os.stat(INBOX + "/status").st_mtime))
    except (OSError, IndexError):
        pass
    return st


def info():
    meta = read_conf(WORLD + "/map_meta.txt")
    wmt = read_conf(WORLD + "/world.mt")
    auth = WORLD + "/auth.sqlite"
    accounts = query(auth, "SELECT count(*) FROM auth")
    recent = query(auth, "SELECT name, last_login FROM auth "
                         "ORDER BY last_login DESC LIMIT 5")
    backups = list_backups()
    return {
        "size": dir_size(WORLD),
        "seed": meta.get("seed", ""),
        "mapgen": meta.get("mg_name", ""),
        "gameid": wmt.get("gameid", ""),
        "accounts": accounts[0][0] if accounts else None,
        "recent": [{"name": r[0], "time": r[1]} for r in recent or []],
        "last_backup": backups[0]["time"] if backups else None,
        "backups": backups,
        "old": list_old(),
        "job": job_state(),
        "inbox_ok": os.access(INBOX, os.W_OK),
        "backups_ok": os.path.isdir(BACKUPS),
    }


def zip_folder(src, label, tmp):
    """Zip a world folder; .sqlite files are copied with the backup API so a
    running server can keep writing."""
    top = "server-world-" + label
    out = os.path.join(tmp, top + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            dirs.sort()
            rel = os.path.relpath(root, src)
            for f in sorted(files):
                p = os.path.join(root, f)
                arc = os.path.normpath(os.path.join(top, rel, f))
                if f.endswith(("-journal", "-wal", "-shm")) or os.path.islink(p):
                    continue
                if f == "world.mt" and rel == ".":
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        lines = [l for l in fh.read().splitlines()
                                 if not re.match(r"^world_name\s*=", l)]
                    lines.append("world_name = Server world " + label)
                    z.writestr(arc, "\n".join(lines) + "\n")
                elif f.endswith(".sqlite"):
                    copy = os.path.join(tmp, "copy.sqlite")
                    s = db_ro(p)
                    d = sqlite3.connect(copy)
                    s.backup(d)
                    d.close()
                    s.close()
                    z.write(copy, arc)
                    os.remove(copy)
                else:
                    z.write(p, arc)
    return out


def zip_backup(path, label, tmp):
    """Turn a nightly .tar.gz into a .zip that opens anywhere."""
    x = os.path.join(tmp, "x")
    os.mkdir(x)
    with tarfile.open(path) as t:
        t.extractall(x, filter="data")
    found = [r for r, _, fs in os.walk(x) if "world.mt" in fs]
    if len(found) != 1:
        raise ValueError("backup does not hold exactly one world")
    return zip_folder(found[0], label, tmp)


class Handler(BaseHTTPRequestHandler):
    server_version = "worldpage"

    def log_message(self, fmt, *args):
        print("%s %s" % (self.headers.get("X-Real-IP", "-"), fmt % args),
              flush=True)

    def send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, name):
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(path, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self.send(200, fh.read(), "text/html; charset=utf-8")
        if path == "/api/info":
            return self.send(200, info())
        m = re.match(r"^/download/(current|backup/([^/]+)|old/([^/]+))$", path)
        if not m:
            return self.send(404, {"error": "not found"})
        with tempfile.TemporaryDirectory() as tmp:
            try:
                if m.group(1) == "current":
                    label = time.strftime("%Y-%m-%d")
                    out = zip_folder(WORLD, label, tmp)
                elif m.group(2):
                    n = m.group(2)
                    if not BACKUP_RE.match(n) or not os.path.isfile(os.path.join(BACKUPS, n)):
                        return self.send(404, {"error": "no such backup"})
                    label = "backup-" + n[6:16]
                    out = zip_backup(os.path.join(BACKUPS, n), label, tmp)
                else:
                    n = m.group(3)
                    if not OLD_RE.match(n) or not os.path.isdir(os.path.join(WORLDS, n)):
                        return self.send(404, {"error": "no such world"})
                    label = "old-" + n[10:]
                    out = zip_folder(os.path.join(WORLDS, n), label, tmp)
            except (OSError, ValueError, sqlite3.Error, tarfile.TarError) as e:
                return self.send(500, {"error": str(e)})
            self.send_file(out, os.path.basename(out))

    def do_POST(self):
        # A custom header can't be sent cross-site without a CORS preflight,
        # which this server never grants, so other websites can't post here.
        if self.headers.get("X-World") != "1" or \
                self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
            return self.send(403, {"error": "forbidden"})
        path = self.path.split("?", 1)[0]
        if path == "/api/cancel":
            # Only a request still waiting; one that has started can't be stopped.
            if not os.path.exists(INBOX + "/request"):
                return self.send(409, {"error": "Nothing is waiting, or it has already started."})
            for f in ("request", "upload.zip"):
                try:
                    os.remove(os.path.join(INBOX, f))
                except OSError:
                    pass
            return self.send(200, {"cancelled": True})
        if not os.access(INBOX, os.W_OK):
            return self.send(503, {"error": "The inbox folder is not set up. See the note at the top of the page."})
        if job_state()["busy"]:
            return self.send(409, {"error": "Another change is still running."})
        if path == "/api/upload":
            return self.upload()
        if path in ("/api/restore", "/api/delete"):
            try:
                n = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))["name"]
            except (ValueError, KeyError, TypeError):
                return self.send(400, {"error": "bad request"})
            if path == "/api/restore":
                if not BACKUP_RE.match(n) or not os.path.isfile(os.path.join(BACKUPS, n)):
                    return self.send(404, {"error": "no such backup"})
                return self.queue("restore " + n)
            if not OLD_RE.match(n) or not os.path.isdir(os.path.join(WORLDS, n)):
                return self.send(404, {"error": "no such world"})
            return self.queue("delete " + n)
        return self.send(404, {"error": "not found"})

    def upload(self):
        try:
            left = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.send(411, {"error": "length required"})
        if left > MAX_UPLOAD:
            return self.send(413, {"error": "file too large"})
        part = INBOX + "/upload.part"
        with open(part, "wb") as fh:
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        if left or not zipfile.is_zipfile(part):
            os.remove(part)
            return self.send(400, {"error": "That is not a .zip file."})
        os.replace(part, INBOX + "/upload.zip")
        return self.queue("import upload.zip")

    def queue(self, line):
        tmp = INBOX + "/request.part"
        with open(tmp, "w") as fh:
            fh.write(line + "\n")
        os.replace(tmp, INBOX + "/request")
        return self.send(202, {"queued": line})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
