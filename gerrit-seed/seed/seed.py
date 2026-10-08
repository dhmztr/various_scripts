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
EXPORT_BRANCH = "review-export"
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


def req(method, path, data, headers, opener=plain, allow=()):
    r = urllib.request.Request(
        f"{G}/a{path}",
        data=json.dumps(data).encode(),
        method=method,
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        opener.open(r)
    except urllib.error.HTTPError as e:
        if e.code in allow:
            return
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode().strip()}")


def api(method, path, data, user="admin", allow=()):
    req(method, path, data, {"Authorization": auth(user)}, allow=allow)


def get(path):
    r = urllib.request.Request(f"{G}/a{path}", headers={"Authorization": auth("admin")})
    body = urllib.request.urlopen(r).read().decode()
    return json.loads(body.split("\n", 1)[1])  # Gerrit poprzedza JSON linią )]}'


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL)


def url(project=PROJECT, user="admin"):
    scheme, host = G.split("://", 1)
    return f"{scheme}://{user}:{PASS}@{host}/a/{project}"


def mirror(project, out):
    # pełny klon: refs/heads, refs/changes/*/{N,meta} (CL-ki i komentarze), refs/meta/config
    git("clone", "-q", "--mirror", url(project), out)
    git("config", "--remove-section", "remote.origin", cwd=out)  # URL zawiera hasło
    # clone --mirror trzyma refy w packed-refs; rozpakuj każdy do pliku pod refs/
    packed = f"{out}/packed-refs"
    if os.path.exists(packed):
        with open(packed) as f:
            refs = [l.split() for l in f if l[0] not in "#^"]
        os.remove(packed)
        for sha, ref in refs:
            os.makedirs(os.path.dirname(f"{out}/{ref}"), exist_ok=True)
            with open(f"{out}/{ref}", "w") as f:
                f.write(sha + "\n")
    git("fsck", "--connectivity-only", "--no-progress", cwd=out)


def export():
    if not EXPORT:
        return
    mirror(PROJECT, EXPORT)
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
        {"name": u, "email": f"{u}@example.com", "http_password": PASS},
        allow=(409,))  # konto zostało z wcześniejszego uruchomienia
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

# komentarze: alice i bob recenzują każdy CL; numery i pliki bierzemy z Gerrita,
# bo numeracja zmian jest globalna i nie musi zaczynać się od 1
changes = get(f"/changes/?q=project:{PROJECT}+status:open&o=CURRENT_REVISION&o=CURRENT_FILES")
for c in changes:
    n = c["_number"]
    path = next(f for f in c["revisions"][c["current_revision"]]["files"] if f != "/COMMIT_MSG")
    api("POST", f"/changes/{n}/revisions/current/review", {
        "message": f"alice: przejrzane CL {n}",
        "labels": {"Code-Review": 1},
        "comments": {path: [{"line": 1, "message": "Popraw tę linię"}]},
    }, "alice")
    api("POST", f"/changes/{n}/revisions/current/review", {
        "message": f"bob: uwagi do CL {n}",
        "comments": {path: [{"line": 2, "message": "A tu literówka?"}]},
    }, "bob")

# gałąź z kodem CL-ek i ich recenzjami jako pliki JSON (czytelne na GitHubie)
git("checkout", "-q", "--detach", "origin/master", cwd=work)
os.makedirs(f"{work}/reviews", exist_ok=True)
changes = get(f"/changes/?q=project:{PROJECT}&o=CURRENT_REVISION&o=MESSAGES"
              "&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS")
for c in sorted(changes, key=lambda c: c["_number"]):
    n = c["_number"]
    ref = c["revisions"][c["current_revision"]]["ref"]
    git("fetch", "-q", "origin", ref, cwd=work)
    git("cherry-pick", "--allow-empty", "FETCH_HEAD", cwd=work)
    review = {
        "change": n,
        "subject": c["subject"],
        "owner": c["owner"].get("username"),
        "url": f"{G}/c/{PROJECT}/+/{n}",
        "votes": {lbl: {v["username"]: v.get("value", 0) for v in d.get("all", [])}
                  for lbl, d in c["labels"].items()},
        "messages": [{"author": m.get("author", {}).get("username"),
                      "date": m["date"], "message": m["message"]}
                     for m in c["messages"]],
        "comments": [{"author": x["author"].get("username"), "file": f,
                      "line": x.get("line"), "date": x["updated"], "message": x["message"]}
                     for f, xs in get(f"/changes/{n}/comments").items() for x in xs],
    }
    with open(f"{work}/reviews/{n}.json", "w") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
    git("add", "reviews", cwd=work)
    git("commit", "-q", "-m", f"Review CL {n}: {c['subject']}", cwd=work)
git("push", "-q", "origin", f"HEAD:refs/heads/{EXPORT_BRANCH}", cwd=work)

export()
creds()
