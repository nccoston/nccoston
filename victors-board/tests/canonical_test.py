"""The board's own address: with CANONICAL_HOST set, every other host is
sent there, path and query intact, except the MCP endpoint and files; the
links the board hands out use it. Unset, nothing redirects. Run from
anywhere:

    python3 victors-board/tests/canonical_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cn_")
os.environ["CANONICAL_HOST"] = "victorsboard.com"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
c = appmod.app.test_client()

def get(path, host, **kw):
    return c.get(path, base_url="https://" + host, **kw)

# the old address goes home, path and query intact
r = get("/message/91820?x=1", "the-victors-board.onrender.com")
if r.status_code != 301 or r.headers.get("Location") != "https://victorsboard.com/message/91820?x=1":
    fails.append("the old address did not redirect: %s %s" % (r.status_code, r.headers.get("Location")))
r = get("/", "www.victorsboard.com")
if r.status_code != 301 or r.headers.get("Location") != "https://victorsboard.com/":
    fails.append("www did not redirect: %s %s" % (r.status_code, r.headers.get("Location")))
# home answers
if get("/", "victorsboard.com").status_code != 200:
    fails.append("the canonical host does not answer")
# the MCP endpoint and files answer on the old address too
r = c.post("/mcp", base_url="https://the-victors-board.onrender.com",
           json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
if r.status_code != 200:
    fails.append("the MCP endpoint redirected on the old address: %s" % r.status_code)
if get("/static/style.css", "the-victors-board.onrender.com").status_code != 200:
    fails.append("a static file redirected on the old address")
# the links the board hands out carry the new address
r = c.post("/mcp", base_url="https://victorsboard.com",
           json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "board_stats", "arguments": {}}})
if "https://victorsboard.com/stats" not in r.get_data(as_text=True):
    fails.append("the MCP server's links do not use the new address")
if appmod.SITE_URL != "https://victorsboard.com/":
    fails.append("SITE_URL is %r" % appmod.SITE_URL)

# unset: nothing redirects
appmod.CANONICAL_HOST = ""
if get("/", "the-victors-board.onrender.com").status_code != 200:
    fails.append("with no canonical host, the old address redirected")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
