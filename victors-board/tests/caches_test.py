"""The external caches refresh in the background: a page gets the value it
has now, and the fetch happens off to the side. Only the first fill waits.

Run from anywhere:  python3 victors-board/tests/caches_test.py
"""
import os, sys, tempfile, threading, time
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cc_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod

fails = []
refresh = appmod.refresh_cache


def fresh_cache():
    return {"at": -1e9, "v": None}, threading.Lock()


# --- the first fill waits, so a fresh start has a value ------------------
cache, lock = fresh_cache()
calls = []
def slow_fetch():
    calls.append(1)
    time.sleep(0.25)
    return "v%d" % len(calls)
t = time.monotonic()
v = refresh(cache, lock, "v", 0.2, slow_fetch)
if v != "v1" or time.monotonic() - t < 0.2:
    fails.append("the first fill did not wait for a value: %r" % v)

# --- a fresh value is served without fetching ----------------------------
if refresh(cache, lock, "v", 0.2, slow_fetch) != "v1" or len(calls) != 1:
    fails.append("a fresh value was refetched")

# --- a stale value comes back NOW, and the refresh happens behind it -----
time.sleep(0.25)
t = time.monotonic()
v = refresh(cache, lock, "v", 0.2, slow_fetch)
waited = time.monotonic() - t
if v != "v1":
    fails.append("a stale read did not return the old value: %r" % v)
if waited > 0.05:
    fails.append("a stale read waited %.0fms on the fetch" % (waited * 1000))
# meanwhile, more stale reads don't start more fetches
for _ in range(5):
    refresh(cache, lock, "v", 0.2, slow_fetch)
time.sleep(0.35)
if cache["v"] != "v2" or len(calls) != 2:
    fails.append("background refresh wrong: value=%r fetches=%d" % (cache["v"], len(calls)))
if cache.get("_busy"):
    fails.append("the cache is still marked busy after the refresh")

# --- keep_empty: an empty answer keeps the last good one ----------------
cache, lock = fresh_cache()
answers = iter([["a game"], [], ["another"]])
def feed():
    return next(answers)
if refresh(cache, lock, "v", 0.1, feed, keep_empty=True) != ["a game"]:
    fails.append("keep_empty first fill wrong")
time.sleep(0.15); refresh(cache, lock, "v", 0.1, feed, keep_empty=True); time.sleep(0.1)
if cache["v"] != ["a game"]:
    fails.append("an empty fetch replaced the last good slate: %r" % cache["v"])
time.sleep(0.15); refresh(cache, lock, "v", 0.1, feed, keep_empty=True); time.sleep(0.1)
if cache["v"] != ["another"]:
    fails.append("a non-empty fetch did not replace the slate: %r" % cache["v"])

# --- a fetch that blows up doesn't take the page with it -----------------
cache, lock = fresh_cache()
def boom():
    raise RuntimeError("ESPN is on fire")
try:
    v = refresh(cache, lock, "v", 0.1, boom)
except Exception as e:
    fails.append("a failing first fill raised: %r" % e)
    v = "raised"
if v is not None:
    fails.append("a failing first fill should yield None, got %r" % v)
cache, lock = fresh_cache()
cache.update(at=time.monotonic() - 10, v=["kept"])
refresh(cache, lock, "v", 0.1, boom, keep_empty=True); time.sleep(0.1)
if cache["v"] != ["kept"]:
    fails.append("a failing refresh lost the last good slate")

# --- the real call sites use it, and don't block each other --------------
for name in ("live_games", "michigan_game_this_week", "slippery_rock_line",
             "pod_box", "michigan_schedule"):
    import inspect
    src = inspect.getsource(getattr(appmod, name))
    if "refresh_cache(" not in src:
        fails.append("%s does not use refresh_cache" % name)
    if "requests.get" in src:
        fails.append("%s fetches inline" % name)

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
