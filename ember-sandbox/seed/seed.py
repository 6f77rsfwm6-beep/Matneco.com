#!/usr/bin/env python3
"""Seed a fresh Stash instance with a small, safe-for-work test library for Ember.

Runs once: on later starts it sees the marker file and exits. Uses only the
Python standard library plus the ffmpeg binary.
"""

import base64
import glob
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STASH_URL = os.environ.get("STASH_URL", "http://stash:9999").rstrip("/")
USERNAME = os.environ.get("STASH_USERNAME", "ember")
PASSWORD = os.environ.get("STASH_PASSWORD", "")
PUBLIC_URL = os.environ.get("STASH_PUBLIC_URL", "http://localhost:9999").rstrip("/")

# Where the seeder writes media, and where the same folder is mounted inside Stash.
MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")
STASH_LIBRARY_PATH = os.environ.get("STASH_LIBRARY_PATH", "/data")
OUT_DIR = os.environ.get("OUT_DIR", "/out")

# Paths as seen by the Stash container (used only for first-run setup).
STASH_CONFIG = os.environ.get("STASH_CONFIG_FILE", "/root/.stash/config.yml")
STASH_DATABASE = os.environ.get("STASH_DATABASE_FILE", "/root/.stash/stash-go.sqlite")
STASH_GENERATED = os.environ.get("STASH_GENERATED_PATH", "/generated")
STASH_CACHE = os.environ.get("STASH_CACHE_PATH", "/cache")
STASH_BLOBS = os.environ.get("STASH_BLOBS_PATH", "/blobs")

MARKER = os.path.join(OUT_DIR, ".seeded")

FONT_CANDIDATES = [
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
FONT = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)

# --------------------------------------------------------------------------
# Test catalogue. Everything here is fictional and safe for work.
# --------------------------------------------------------------------------

TAGS = [
    ("Outdoors", None), ("Indoors", None), ("Tutorial", None), ("Behind the Scenes", None),
    ("Timelapse", "Outdoors"), ("Interview", "Indoors"), ("4K", None), ("Vertical", None),
    ("Intro", None), ("Highlight", None), ("Credits", None),
]

STUDIOS = [
    # name, parent, url, colour
    ("Lantern Pictures", None, "https://example.com/lantern", "0x2b6cb0"),
    ("Lantern Shorts", "Lantern Pictures", "https://example.com/lantern/shorts", "0x3182ce"),
    ("Copperline Media", None, "https://example.com/copperline", "0xb7791f"),
    ("Northfield Studio", None, "https://example.com/northfield", "0x2f855a"),
]

PERFORMERS = [
    # name, gender, birthdate, country, colour, favourite
    ("Avery Quill", "FEMALE", "1990-04-12", "US", "0x805ad5", True),
    ("Jonah Bramble", "MALE", "1985-09-30", "CA", "0xdd6b20", False),
    ("Rowan Ashby", "NON_BINARY", "1994-01-05", "GB", "0x319795", False),
    ("Mira Castellan", "FEMALE", "1988-07-22", "ES", "0xd53f8c", True),
    ("Theo Lark", "MALE", "1992-11-14", "AU", "0x3182ce", False),
    ("Sasha Wren", "FEMALE", None, "NZ", "0x38a169", False),
]

GROUPS = [
    ("The Lantern Series", "Lantern Pictures", "2024-03-01", "A three-part test series."),
    ("Copperline Collection", "Copperline Media", "2025-06-15", "Assorted clips from Copperline."),
]

# file, source, size, seconds, title, studio, performers, tags, date, rating, group(index)
SCENES = [
    ("lantern_ep1.mp4", "testsrc2", "1280x720", 40, "Lantern Episode 1: First Light", "Lantern Pictures",
     ["Avery Quill", "Jonah Bramble"], ["Outdoors", "Intro"], "2024-03-01", 80, ("The Lantern Series", 1)),
    ("lantern_ep2.mp4", "testsrc2", "1280x720", 45, "Lantern Episode 2: The Long Road", "Lantern Pictures",
     ["Avery Quill", "Rowan Ashby"], ["Outdoors", "Timelapse"], "2024-03-08", 70, ("The Lantern Series", 2)),
    ("lantern_ep3.mp4", "testsrc2", "1280x720", 50, "Lantern Episode 3: Homecoming", "Lantern Pictures",
     ["Avery Quill", "Jonah Bramble", "Rowan Ashby"], ["Indoors"], "2024-03-15", 90, ("The Lantern Series", 3)),
    ("lantern_short_bts.mp4", "smptehdbars", "1920x1080", 30, "Behind the Lantern", "Lantern Shorts",
     ["Jonah Bramble"], ["Behind the Scenes", "Interview"], "2024-04-02", 60, None),
    ("copperline_fractal.mp4", "mandelbrot", "1280x720", 35, "Copperline Fractal Study", "Copperline Media",
     ["Mira Castellan"], ["Tutorial", "Highlight"], "2025-06-15", 100, ("Copperline Collection", 1)),
    ("copperline_life.mp4", "life", "854x480", 30, "Copperline: Game of Life", "Copperline Media",
     ["Mira Castellan", "Theo Lark"], ["Tutorial"], "2025-06-20", 40, ("Copperline Collection", 2)),
    ("copperline_vertical.mp4", "testsrc2", "720x1280", 25, "Copperline Vertical Teaser", "Copperline Media",
     ["Theo Lark"], ["Vertical", "Highlight"], "2025-07-01", 50, None),
    ("northfield_4k_bars.mp4", "smptehdbars", "3840x2160", 20, "Northfield 4K Calibration", "Northfield Studio",
     [], ["4K", "Tutorial"], "2023-11-11", None, None),
    ("northfield_interview.mp4", "cellauto", "1280x720", 40, "Northfield Interview with Sasha Wren", "Northfield Studio",
     ["Sasha Wren"], ["Interview", "Indoors"], "2023-12-01", 70, None),
    ("northfield_credits.mp4", "testsrc2", "1280x720", 20, "Northfield Credits Reel", "Northfield Studio",
     ["Sasha Wren", "Avery Quill", "Theo Lark", "Mira Castellan"], ["Credits"], "2024-01-10", 30, None),
    # Edge cases for the client: long unicode title, and a bare file with no metadata.
    ("unicode_title.mp4", "testsrc2", "640x360", 15,
     "Ünïcødé & Emoji Test 🎬 — a deliberately long title to check wrapping and truncation in list views",
     None, ["Rowan Ashby"], [], "2022-02-22", 20, None),
    ("unorganized_clip.mp4", "smptehdbars", "640x360", 15, None, None, [], [], None, None, None),
]

# (scene file, seconds, end seconds, title, primary tag)
MARKERS = [
    ("lantern_ep1.mp4", 0, 8, "Opening", "Intro"),
    ("lantern_ep1.mp4", 20, None, "Sunrise", "Highlight"),
    ("lantern_ep3.mp4", 35, 50, "Ending", "Credits"),
    ("copperline_fractal.mp4", 10, 25, "Zoom in", "Highlight"),
    ("northfield_interview.mp4", 5, None, "First question", "Interview"),
]


# --------------------------------------------------------------------------
# Stash API helpers
# --------------------------------------------------------------------------

cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def log(msg):
    print(f"[seed] {msg}", flush=True)


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(f"{STASH_URL}/graphql", data=body,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=120) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def login():
    form = urllib.parse.urlencode({"username": USERNAME, "password": PASSWORD}).encode()
    req = urllib.request.Request(f"{STASH_URL}/login", data=form)
    try:
        opener.open(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303):
            raise


def wait_for_stash():
    log(f"waiting for Stash at {STASH_URL} ...")
    for _ in range(120):
        try:
            return gql("{ systemStatus { status } }")["systemStatus"]["status"]
        except Exception:
            time.sleep(2)
    sys.exit("Stash never came up")


def wait_for_jobs(label):
    log(f"waiting for {label} ...")
    time.sleep(2)
    while True:
        jobs = gql("{ jobQueue { id status description progress } }")["jobQueue"] or []
        if not jobs:
            return
        time.sleep(3)


# --------------------------------------------------------------------------
# Media generation
# --------------------------------------------------------------------------

def ffmpeg(args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def text_filter(text, size="h/12"):
    if not FONT:
        return None
    safe = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
    return (f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:fontsize={size}:"
            "box=1:boxcolor=black@0.55:boxborderw=12:x=(w-text_w)/2:y=(h-text_h)/2")


def make_video(path, source, size, seconds, label):
    if os.path.exists(path):
        return
    w, h = size.split("x")
    if source == "mandelbrot":
        src = f"mandelbrot=size={size}:rate=30"
    elif source == "life":
        src = f"life=size={size}:rate=30:mold=10:ratio=0.1:death_color=#202040:life_color=#40c0ff"
    elif source == "cellauto":
        src = f"cellauto=size={size}:rate=30:rule=110"
    else:
        src = f"{source}=size={size}:rate=30"
    vf = ["format=yuv420p"]
    caption = text_filter(label)
    if caption:
        vf.append(caption)
        # running clock so seeking and resume are easy to check by eye
        vf.append(f"drawtext=fontfile={FONT}:text='%{{pts\\:hms}}':fontcolor=yellow:fontsize=h/18:"
                  "box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-text_h-h/12")
    ffmpeg(["-f", "lavfi", "-i", f"{src},trim=duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency={220 + len(label) * 7 % 600}:duration={seconds}",
            "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", path])


def make_image(path, colour, label, size="1200x800"):
    if os.path.exists(path):
        return
    vf = text_filter(label, "h/8")
    args = ["-f", "lavfi", "-i", f"color=c={colour}:size={size}:duration=1", "-frames:v", "1"]
    if vf:
        args += ["-vf", vf]
    ffmpeg(args + [path])


def data_uri(colour, label, size="600x800"):
    tmp = os.path.join(OUT_DIR, ".tmp_portrait.jpg")
    if os.path.exists(tmp):
        os.remove(tmp)
    make_image(tmp, colour, label, size)
    with open(tmp, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    os.remove(tmp)
    return f"data:image/jpeg;base64,{encoded}"


def generate_media():
    scenes_dir = os.path.join(MEDIA_DIR, "scenes")
    os.makedirs(scenes_dir, exist_ok=True)
    for i, s in enumerate(SCENES, 1):
        fname, source, size, seconds, title = s[:5]
        log(f"video {i}/{len(SCENES)}: {fname} ({size}, {seconds}s)")
        make_video(os.path.join(scenes_dir, fname), source, size, seconds, (title or fname)[:40])



# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------

def setup_stash():
    log("running first-time setup")
    gql("""mutation($input: SetupInput!) { setup(input: $input) }""", {"input": {
        "configLocation": STASH_CONFIG,
        "stashes": [{"path": STASH_LIBRARY_PATH, "excludeVideo": False, "excludeImage": True}],
        "sfwContentMode": True,
        "databaseFile": STASH_DATABASE,
        "generatedLocation": STASH_GENERATED,
        "cacheLocation": STASH_CACHE,
        "storeBlobsInDatabase": False,
        "blobsLocation": STASH_BLOBS,
    }})
    for _ in range(30):
        if gql("{ systemStatus { status } }")["systemStatus"]["status"] == "OK":
            return
        time.sleep(1)
    sys.exit("Stash did not finish setup")


def seed_metadata():
    ids = {"tag": {}, "studio": {}, "performer": {}, "group": {}, "scene": {}}

    for name, parent in TAGS:
        inp = {"name": name}
        if parent:
            inp["parent_ids"] = [ids["tag"][parent]]
        ids["tag"][name] = gql("mutation($i: TagCreateInput!) { tagCreate(input: $i) { id } }",
                               {"i": inp})["tagCreate"]["id"]

    for name, parent, url, colour in STUDIOS:
        inp = {"name": name, "urls": [url], "image": data_uri(colour, name, "800x400"),
               "details": f"{name} is a fictional studio created for Ember testing."}
        if parent:
            inp["parent_id"] = ids["studio"][parent]
        ids["studio"][name] = gql("mutation($i: StudioCreateInput!) { studioCreate(input: $i) { id } }",
                                  {"i": inp})["studioCreate"]["id"]

    for name, gender, birthdate, country, colour, fav in PERFORMERS:
        inp = {"name": name, "gender": gender, "country": country, "favorite": fav,
               "image": data_uri(colour, name), "details": f"{name} is a fictional performer for Ember testing.",
               "alias_list": [name.split()[0]]}
        if birthdate:
            inp["birthdate"] = birthdate
        ids["performer"][name] = gql("mutation($i: PerformerCreateInput!) { performerCreate(input: $i) { id } }",
                                     {"i": inp})["performerCreate"]["id"]

    for name, studio, date, synopsis in GROUPS:
        ids["group"][name] = gql("mutation($i: GroupCreateInput!) { groupCreate(input: $i) { id } }", {"i": {
            "name": name, "studio_id": ids["studio"][studio], "date": date, "synopsis": synopsis,
            "front_image": data_uri("0x1a202c", name),
        }})["groupCreate"]["id"]

    found = gql("""{ findScenes(filter: {per_page: -1}) { scenes { id files { basename } } } }""")
    by_file = {s["files"][0]["basename"]: s["id"] for s in found["findScenes"]["scenes"] if s["files"]}
    for fname, _src, _size, _secs, title, studio, performers, tags, date, rating, group in SCENES:
        sid = by_file.get(fname)
        if not sid:
            log(f"WARNING: scan did not pick up {fname}")
            continue
        ids["scene"][fname] = sid
        if title is None:
            continue  # leave this one bare on purpose
        inp = {"id": sid, "title": title, "date": date, "organized": True,
               "details": f"Test scene “{title}” generated for Ember.",
               "performer_ids": [ids["performer"][p] for p in performers],
               "tag_ids": [ids["tag"][t] for t in tags],
               "urls": [f"https://example.com/scenes/{fname.removesuffix('.mp4')}"]}
        if studio:
            inp["studio_id"] = ids["studio"][studio]
        if rating is not None:
            inp["rating100"] = rating
        if group:
            inp["groups"] = [{"group_id": ids["group"][group[0]], "scene_index": group[1]}]
        gql("mutation($i: SceneUpdateInput!) { sceneUpdate(input: $i) { id } }", {"i": inp})

    for fname, secs, end, title, tag in MARKERS:
        inp = {"scene_id": ids["scene"][fname], "seconds": secs, "title": title,
               "primary_tag_id": ids["tag"][tag]}
        if end is not None:
            inp["end_seconds"] = end
        gql("mutation($i: SceneMarkerCreateInput!) { sceneMarkerCreate(input: $i) { id } }", {"i": inp})

    # A little play history so "continue watching" style features have data.
    ep2 = ids["scene"].get("lantern_ep2.mp4")
    if ep2:
        gql("mutation { sceneSaveActivity(id: %s, resume_time: 18.5, playDuration: 90) }" % ep2)
        gql("mutation { sceneAddPlay(id: %s, times: [\"2025-01-04T20:00:00Z\", \"2025-01-05T21:30:00Z\"]) { count } }" % ep2)
    return ids


def lock_down():
    """Set the login, then mint an API key for Ember."""
    if not PASSWORD:
        log("STASH_PASSWORD is empty: leaving Stash open with no login and no API key")
        return None
    gql("mutation($i: ConfigGeneralInput!) { configureGeneral(input: $i) { username } }",
        {"i": {"username": USERNAME, "password": PASSWORD}})
    login()
    return gql("mutation { generateAPIKey(input: {}) }")["generateAPIKey"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(MARKER):
        log("library already seeded; nothing to do (run ./reset.sh to start over)")
        return

    status = wait_for_stash()
    if status == "SETUP":
        setup_stash()
    elif PASSWORD:
        login()  # a half-finished earlier run may already have set the password

    gql("mutation($i: ConfigGeneralInput!) { configureGeneral(input: $i) { previewSegments } }",
        {"i": {"previewSegments": 6, "previewSegmentDuration": 0.75}})

    generate_media()

    gql("""mutation { metadataScan(input: {scanGenerateCovers: true, scanGeneratePreviews: true,
          scanGenerateSprites: true, scanGeneratePhashes: true}) }""")
    wait_for_jobs("library scan and generation")

    ids = seed_metadata()
    gql("mutation { metadataGenerate(input: {markers: true, markerScreenshots: true, markerImagePreviews: false}) }")
    wait_for_jobs("marker previews")

    api_key = lock_down()

    lines = [
        "Ember sandbox: Stash connection details",
        "=======================================",
        f"Stash URL : {PUBLIC_URL}",
        f"GraphQL   : {PUBLIC_URL}/graphql",
        f"Username  : {USERNAME if PASSWORD else '(none - open access)'}",
        f"Password  : {'(see STASH_PASSWORD in .env)' if PASSWORD else '(none)'}",
        f"API key   : {api_key or '(none - open access)'}",
        "",
        "Send the API key in the 'ApiKey' HTTP header on every request.",
        "",
        f"Seeded: {len(ids['scene'])} scenes, {len(ids['performer'])} performers, {len(ids['studio'])} studios, "
        f"{len(ids['tag'])} tags, {len(ids['group'])} groups, {len(MARKERS)} markers.",
    ]
    with open(os.path.join(OUT_DIR, "ember-connection.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(MARKER, "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
