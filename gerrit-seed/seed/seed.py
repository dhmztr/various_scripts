import base64
import http.cookiejar
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

G = os.environ.get("GERRIT_URL", "http://gerrit:8080")
PASS = os.environ.get("SEED_PASSWORD", "secret")
EXPORT = os.environ.get("EXPORT_DIR", "")
PROJECT = "demo"
USERS = ["alice", "bob"]

jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
plain = urllib.request.build_opener()


def auth(user):
    return "Basic " + base64.b64encode(f"{user}:{PASS}".encode()).decode()


def ok(url):
    try:
        urllib.request.urlopen(url)
        return True
    except (urllib.error.URLError, ConnectionError):
        return False


def req(method, path, data, headers, opener=plain):
    r = urllib.request.Request(
        f"{G}/a{path}",
        data=json.dumps(data).encode(),
        method=method,
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        opener.open(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode().strip()}")


def api(method, path, data, user="admin"):
    req(method, path, data, {"Authorization": auth(user)})


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def url(user="admin"):
    scheme, host = G.split("://", 1)
    return f"{scheme}://{user}:{PASS}@{host}/a/{PROJECT}"


def export():
    if not EXPORT:
        return
    git("clone", "-q", "--mirror", url(), EXPORT)
    git("config", "--remove-section", "remote.origin", cwd=EXPORT)  # URL zawiera hasło
    print(f"repo -> {EXPORT}")


def creds():
    for u in ["admin", *USERS]:
        print(f"{u} / {PASS}")


while not ok(f"{G}/config/server/version"):
    time.sleep(2)

if ok(f"{G}/projects/{PROJECT}"):
    export()
    creds()
    raise SystemExit(0)

# hasło HTTP admina (jedyny moment, gdzie potrzebna sesja z przeglądarki)
browser.open(f"{G}/login/%23%2F?user_name=admin")
browser.open(f"{G}/")
xsrf = next(c.value for c in jar if c.name == "XSRF_TOKEN")
req("PUT", "/accounts/self/password.http", {"http_password": PASS},
    {"X-Gerrit-Auth": xsrf}, browser)

for u in USERS:
    api("PUT", f"/accounts/{u}",
        {"name": u, "email": f"{u}@example.com", "http_password": PASS})
api("PUT", f"/projects/{PROJECT}", {"create_empty_commit": True})

# repo + CL-ki: każdy commit wypchnięty na refs/for/master to osobna zmiana
work = tempfile.mkdtemp()
git("clone", "-q", url(), work)
git("config", "user.name", "Administrator", cwd=work)
git("config", "user.email", "admin@example.com", cwd=work)
hook = f"{work}/.git/hooks/commit-msg"
with open(hook, "wb") as f:
    f.write(urllib.request.urlopen(f"{G}/tools/hooks/commit-msg").read())
os.chmod(hook, 0o755)

for i in range(1, 4):
    git("checkout", "-q", "--detach", "origin/master", cwd=work)
    with open(f"{work}/file{i}.txt", "w") as f:
        f.write(f"linia 1 z CL {i}\nlinia 2 z CL {i}\n")
    git("add", ".", cwd=work)
    git("commit", "-q", "-m", f"Seed change {i}", cwd=work)
    git("push", "-q", "origin", "HEAD:refs/for/master", cwd=work)

# komentarze: alice i bob recenzują każdy CL
for i in range(1, 4):
    api("POST", f"/changes/{PROJECT}~{i}/revisions/current/review", {
        "message": f"alice: przejrzane CL {i}",
        "labels": {"Code-Review": 1},
        "comments": {f"file{i}.txt": [{"line": 1, "message": "Popraw tę linię"}]},
    }, "alice")
    api("POST", f"/changes/{PROJECT}~{i}/revisions/current/review", {
        "message": f"bob: uwagi do CL {i}",
        "comments": {f"file{i}.txt": [{"line": 2, "message": "A tu literówka?"}]},
    }, "bob")

export()
creds()
