"""The pod box: up on Wednesday for this week's episode or stream, and not
taken down by one refresh that can't reach YouTube, nor by the moment a
scheduled stream goes live. Run from anywhere:

    python3 victors-board/tests/pod_test.py
"""
import os, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pod_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod

fails = []
with appmod.app.app_context():
    appmod.init_db()

# --- reading the watch page
W = appmod._stream_window_from
recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
cases = {
    '... "isUpcoming":true ...': "upcoming",
    '... "isLiveNow":true ... "startTimestamp":"%s"' % old: "today",      # live beats an odd start time
    '... "isLive":true ...': "today",
    '... "startTimestamp":"%s" ...' % recent: "today",
    '... "startTimestamp":"%s" ...' % old: None,
    '... "startTimestamp":"garbage" ...': None,
    "plain upload page": None,
}
for html, want in cases.items():
    if W(html) != want:
        fails.append("window for %r: %r, wanted %r" % (html[:40], W(html), want))


# --- the box on a Wednesday, with YouTube played by a stub
class FakeNow:
    @staticmethod
    def wednesday():
        d = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)   # a Wednesday, 1 PM Detroit
        assert d.astimezone(appmod.BOARD_TZ).weekday() == 2
        return d

real_datetime = appmod.datetime
class WedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        d = FakeNow.wednesday()
        return d.astimezone(tz) if tz else d.replace(tzinfo=None)
appmod.datetime = WedDatetime

feed_video = {"video_id": "FGTCqVfuPpA", "title": "The Victors Pod 11/11", "published": FakeNow.wednesday() - timedelta(days=3)}
state = {"feed": feed_video, "window": "upcoming"}
appmod.fetch_latest_pod = lambda: state["feed"]
appmod.pod_stream_window = lambda vid: state["window"]


def box():
    with appmod.app.app_context():
        return appmod.pod_box()


def refresh_and_box():
    with appmod.POD_LOCK:
        appmod.POD_CACHE["at"] = -1e9
    b = box()
    for _ in range(50):   # the refresh runs in a thread; wait for it
        time.sleep(0.02)
        with appmod.POD_LOCK:
            if not appmod.POD_CACHE.get("_busy"):
                break
    return box()


# morning: the stream is scheduled -> box up
with appmod.POD_LOCK:
    appmod.POD_CACHE.update({"at": -1e9, "video": None, "_busy": False})
if not (box() and box()["video_id"] == "FGTCqVfuPpA"):
    fails.append("the box is not up for a scheduled stream")
# showtime: YouTube says live now -> still up
state["window"] = "today"
if not refresh_and_box():
    fails.append("the box went down when the stream went live")
# a refresh that can't reach the feed at all -> the box stays
state["feed"] = None
if not refresh_and_box():
    fails.append("one failed refresh took the box down")
state["feed"] = feed_video
# the watch page unreadable, entry from this week -> still up
state["window"] = "unknown"
if not refresh_and_box():
    fails.append("an unreadable watch page took the box down for this week's entry")
# a plainly old entry with nothing to say for itself -> no box (a skipped week)
old_video = dict(feed_video, published=FakeNow.wednesday() - timedelta(days=12))
with appmod.POD_LOCK:
    appmod.POD_CACHE.update({"at": -1e9, "video": None, "_busy": False})
state["feed"], state["window"] = old_video, None
if box():
    fails.append("a skipped week shows last week's box")
state["window"] = "unknown"
with appmod.POD_LOCK:
    appmod.POD_CACHE.update({"at": -1e9, "video": None, "_busy": False})
if box():
    fails.append("an old entry with an unreadable page shows")

appmod.datetime = real_datetime
print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
