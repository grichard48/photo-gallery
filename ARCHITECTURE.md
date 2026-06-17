# How the Photo Gallery Works

A tour of the gallery's internals — how pages are produced, how the photo tree
is built and sorted, how the thumbnail grid is rendered, and how the lightbox
works. Companion to `README.md` (setup) and `HOW-TO.md` (day-to-day use).

## The big idea: one page, not many

The gallery is a **single-page application**. There are not separate HTML pages
for Seattle, 2015, or each album — there is exactly one file, `site/index.html`,
plus one data file, `manifest.json`. Every "page" you see is that same
`index.html` redrawing itself from a different branch of the data.

Two pieces make it work:

1. **The data tree** (`manifest.json`) — a nested outline of your albums and
   photos, generated at build time by `scripts/build.py`.
2. **The page logic** (a small script inside `index.html`) — it loads the tree
   once, watches the address bar, and redraws the screen for whatever node the
   URL points at.

The part of the URL after `#/` is the address of a node, e.g.
`#/Scrapbook/Seattle/2015`. Clicking only changes that hash — no new page loads
from the server — and the script walks the tree to the matching node and
redraws.

What it draws depends on what the node contains:

- Node has child albums → a grid of **album cards** (an "index page").
- Node has photos → the **masonry thumbnail grid** (a "gallery page").
- Click a thumbnail → the **lightbox** opens the full image from R2.

### Seattle, level by level

| URL | Node contains | What renders |
| --- | --- | --- |
| `#/Scrapbook/Seattle` | years | cards for 2015 … 2026 (Seattle index) |
| `#/Scrapbook/Seattle/2015` | months | cards for the months (2015 index) |
| `#/Scrapbook/Seattle/2015/August` | photos | thumbnail grid (gallery page) |
| (click a photo) | — | lightbox with the full image |

The breadcrumb trail (Home / Scrapbook / Seattle / 2015) is just that path split
into clickable links — and it's where the teal accent shows.

## Topic 1 — Building and sorting the tree (`build.py`)

The tree is built in two phases. During the upload phase, `build.py` processes
every photo and collects a dictionary of facts about each one — `meta` — keyed
by the photo's path, holding its display name, its thumbnail and web URLs (`t`
and `i`), its width/height, and its capture date `d`. Then a recursive walker
assembles the tree by mirroring your folders and looking up those facts:

```python
def build_album(dir_path, meta):
    rel = dir_path.relative_to(SRC)
    entries = sorted(dir_path.iterdir(), key=lambda p: natural_key(p.name))

    photos, albums = [], []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            sub = build_album(entry, meta)        # recurse into subfolder
            if sub["count"] > 0:                  # skip empty folders
                albums.append(sub)
        elif entry.suffix.lower() in IMAGE_EXTS:
            m = meta.get(entry.relative_to(SRC).as_posix())
            if m:
                photos.append(m)                  # look up the photo's facts

    photos.sort(key=lambda p: (p["d"] or "9999", natural_key(p["name"])))
    albums.sort(key=lambda a: album_key(a["name"]))

    count = len(photos) + sum(a["count"] for a in albums)
    cover = photos[0]["t"] if photos else (albums[0]["cover"] if albums else None)
    return {"name": ..., "path": ..., "cover": cover,
            "count": count, "albums": albums, "photos": photos}
```

Each subfolder becomes a child album (the function calls itself on it); each
image becomes a photo entry; empty folders are dropped. `count` and `cover` roll
up from the bottom — a folder's count is its own photos plus everything in its
children, and its cover is its first photo's thumbnail, or (for a pure container
like Seattle) the cover of its first child. That's why the Seattle card shows a
photo even though Seattle itself holds only year folders.

The two sort rules turn disk order into reading order:

```python
def natural_key(s):
    # numeric-aware: "img2" sorts before "img10"
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def album_key(name):
    if name.lower() in MONTHS:                # MONTHS = {"january":1, ... "december":12}
        return ["", MONTHS[name.lower()], ""]  # months sort by calendar number
    return natural_key(name)                   # everything else: natural alphabetical
```

So month folders sort chronologically (July, August, September …) regardless of
how the filesystem lists them, and other albums sort naturally. Photos sort by
their EXIF capture date `d` (a string like `2015:08:14 10:32:00`, which sorts
chronologically as plain text); anything without a date gets `"9999"` so it
drifts to the end, ordered by filename.

Finally the assembled tree is wrapped with the gallery title and written out:

```python
manifest = {"title": config["title"], "root": tree}
```

Everything the website knows about structure, order, counts, covers, and image
URLs is decided here at build time and frozen into that one JSON file. The page
never has to figure out ordering — it just renders what the tree says.

## Topic 2 — The masonry thumbnail grid

When a node has photos, the page turns its `photos` list into the grid:

```javascript
if (album.photos.length) {
  html += '<div class="grid">' + album.photos.map((p, i) =>
    '<a href="' + p.i + '" data-i="' + i + '">' +
      '<img loading="lazy" src="' + p.t + '" width="' + p.w + '" height="' + p.h + '" alt="' + esc(p.name) + '">' +
    '</a>').join('') + '</div>';
}
```

Each attribute earns its place:

- `data-i="i"` — the photo's index in the album, so the lightbox knows which one.
- `href = p.i` — the full image; the link still works with JavaScript off.
- `src = p.t` — the small thumbnail, so the grid loads fast.
- `width` / `height` — the real pixel size, so the browser reserves the right
  space before the image loads and nothing jumps as images stream in.
- `loading="lazy"` — the browser fetches a thumbnail only when you scroll near it.

The masonry layout is pure CSS — no JavaScript measuring anything:

```css
.grid { columns: 4 260px; column-gap: 12px; }
.grid a { display: block; margin-bottom: 12px; break-inside: avoid; }
.grid img { width: 100%; height: auto; }
```

`columns: 4 260px` means "as many columns as fit at ~260px each, up to 4." The
browser flows tiles into those columns; because each image keeps its aspect ratio
(`height: auto`) and `break-inside: avoid` prevents splitting, they stack into a
staggered wall on their own. One quirk: CSS columns fill top-to-bottom, so
reading order runs down each column rather than strictly left-to-right. A media
query drops to two columns on phones.

Clicks use **event delegation** — one listener on the whole grid instead of one
per tile:

```javascript
const grid = document.querySelector('.grid');
if (grid) grid.addEventListener('click', e => {
  const a = e.target.closest('a[data-i]');
  if (!a) return;
  e.preventDefault();
  openLB(+a.dataset.i);
});
```

It finds the nearest enclosing tile, cancels the normal navigation, and opens the
lightbox at that index. Just before this, `render` stored `current.photos =
album.photos`, giving the lightbox the full ordered list plus a starting index.

## Topic 3 — The lightbox

One overlay covers the screen, hidden until needed:

```html
<div class="lb" id="lb" role="dialog" aria-modal="true">
  <button class="x" onclick="closeLB()">✕</button>
  <button class="p" onclick="step(-1)">‹</button>
  <button class="n" onclick="step(1)">›</button>
  <img id="lbimg"><div class="ct" id="lbct"></div>
</div>
```

```css
.lb { position: fixed; inset: 0; background: rgba(12,12,12,.96); display: none;
      align-items: center; justify-content: center; z-index: 50; }
.lb.open { display: flex; }
.lb img { max-width: 95vw; max-height: 92vh; object-fit: contain; }
```

Its whole memory is one object, `current = { photos, idx }` — the album's photo
list and which one is showing (`-1` when closed). Open and close are small, and
note the scroll lock:

```javascript
function openLB(i) { current.idx = i; show(); $('lb').classList.add('open');
                     document.body.style.overflow = 'hidden'; }
function closeLB() { $('lb').classList.remove('open'); document.body.style.overflow = '';
                     current.idx = -1; }
```

Paging holds two nice details — wrap-around and neighbour preloading:

```javascript
function step(d) { const n = current.photos.length;
                   current.idx = (current.idx + d + n) % n; show(); }

function show() {
  const p = current.photos[current.idx];
  $('lbimg').src = p.i;                                   // full image from R2
  $('lbct').textContent = (current.idx + 1) + ' / ' + current.photos.length;
  [1, -1].forEach(d => {                                  // preload neighbours
    const q = current.photos[(current.idx + d + current.photos.length) % current.photos.length];
    if (q) new Image().src = q.i;
  });
}
```

`(idx + d + n) % n` wraps the index — back from the first photo lands on the
last, forward from the last lands on the first. And each time a photo shows, the
code creates throwaway `new Image()` objects for the next and previous photos,
which makes the browser fetch and cache them in the background — so pressing next
feels instant.

Three inputs drive it:

```javascript
document.addEventListener('keydown', e => {
  if (current.idx < 0) return;                 // ignore keys when closed
  if (e.key === 'Escape') closeLB();
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'ArrowLeft') step(-1);
});

$('lb').addEventListener('click', e => { if (e.target === $('lb')) closeLB(); });

let tx = null;
$('lb').addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
$('lb').addEventListener('touchend', e => {
  const dx = e.changedTouches[0].clientX - tx;
  if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1);   // swipe left = next
  tx = null;
}, { passive: true });
```

The keyboard handler lives on the document but bails when the lightbox is closed,
so arrows and Escape only act while viewing. Click-to-close fires only when you
click the dark backdrop itself (`e.target === lb`) — clicking the image or
buttons has a different target, so those don't dismiss it. The swipe records the
touch-down X and pages if the finger moves more than 40px. Buttons carry
`aria-label`s and the overlay is `role="dialog"` / `aria-modal` for screen
readers.

### The info panel

The lightbox also has an optional info panel, toggled with the `i` key or the
ⓘ button (for touch). A module-level flag `infoOn` remembers whether it's open,
and `renderInfo` fills it from the current photo's manifest entry:

```javascript
function renderInfo() {
  const box = $('lbinfo');
  const p = current.photos[current.idx];
  if (!infoOn || !p) { box.hidden = true; return; }
  const file = decodeURIComponent(p.i.split('/').pop());   // filename from the URL
  const date = fmtDate(p.d);                                // capture date, if any
  let h = '<div class="fn">' + esc(file) + '</div>';
  if (date) h += '<div class="sub">' + esc(date) + '</div>';
  h += '<div class="sub">' + p.w + ' × ' + p.h + '</div>';
  box.innerHTML = h;
  box.hidden = false;
}
```

All of this data is already in the manifest — there's no extra lookup. The
filename comes from the tail of the photo's `i` URL (so the extension reads as the
published `.jpg`), the dimensions from `w`/`h`, and the date from `d`. The date
line is only added when `d` is non-empty, so photos with an embedded EXIF capture
date show one and the older imports (whose date field is blank) simply show
filename and size. `show()` calls `renderInfo()` on every photo change, so the
panel stays in sync as you page, and the flag persists so it stays open until you
toggle it off.

Note that `d` is the EXIF `DateTimeOriginal` captured at build time, not the
file's write date — so it reflects when a photo was actually taken, where that
metadata survives.

## The pipeline in one line

`build.py` walks your folders and freezes an ordered tree into `manifest.json`;
the page reads that tree and paints either album cards or the CSS-columns photo
grid; clicking a thumbnail hands its index to the lightbox, which pages through
the album with wrap-around, preloading, and keyboard/swipe controls — all from
one small HTML file, with the images streamed from R2.
