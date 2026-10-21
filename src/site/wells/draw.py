"""The three wells' drawings, as inline SVG, from the page's figures.

Each well is drawn twice from one description: tall, for the three
drawings side by side on a wide screen, and wide, for one drawing at a time
on a phone or a tablet, where its labels are at least params.MIN_LABEL_PX
on the narrowest screen params.PHONE_PX describes. A drawing is a list of
layers, a well (casing, screen, open hole), water, moving water and its
arrows, conceptual pathways and labels, each placed by depth: every depth,
level and label comes from the figures, so nothing is typed.

The classes are docs/assets/wells.css's; docs/assets/wells.js steps them
(w-water, w-recharge, w-levels and w-unsure appear with the steps) and
shows the source a layer's data-src names.
"""

import html

DASH = "–"
ARROW = ' marker-end="url(#w-arrow)"'


class Frame:
    """One shape of drawing: its size, its well's place and its fonts."""

    def __init__(self, name, width, height, ground, bottom, well_x, fonts):
        """A frame.

        Args:
            name: "tall" or "wide".
            width: The viewBox's width.
            height: Its height.
            ground: The ground's y.
            bottom: The y of the axis's deepest foot.
            well_x: The well's centre (for a tall granite well, 16 more).
            fonts: The label sizes: "lab", "small", "tiny" and "axis".
        """
        self.name = name
        self.width = width
        self.height = height
        self.ground = ground
        self.bottom = bottom
        self.well_x = well_x
        self.fonts = fonts
        self.x0 = 38.0
        self.half = 5.0  # the well's half width

    def u(self, u):
        """An x across the rock: -1 the left edge, 0 the well, 1 the right."""
        if u == "wl":
            return self.well_x - self.half - 1
        if u == "wr":
            return self.well_x + self.half + 1
        if u < 0:
            return self.well_x + u * (self.well_x - self.x0 - 4)
        return self.well_x + u * (self.width - self.well_x - 3)

    def columns(self):
        """The two label columns: left of the well and right of it."""
        return {
            "left": (self.x0 + 6, self.well_x - self.half - 7),
            "right": (self.well_x + self.half + 7, self.width - 4),
        }


TALL = {"width": 220, "height": 440, "ground": 50, "bottom": 400}
TALL_FONTS = {"lab": 14, "small": 12, "tiny": 10.5, "axis": 11}
WIDE = {"width": 340, "height": 320, "ground": 46, "bottom": 280}
WIDE_FONTS = {"lab": 14, "small": 13, "tiny": 13, "axis": 13}
CHAR_EM = (
    0.45  # an average character's width, in ems (Source Sans 3: about 0.42)
)
LINE = 1.18  # line height, in ems
GAP = 2.0  # space between two labels


def frames(granite=False):
    """The tall and wide frames of a drawing."""
    tall_x = 144 if granite else 128
    return (
        Frame("tall", **TALL, well_x=tall_x, fonts=TALL_FONTS),
        Frame("wide", **WIDE, well_x=180, fonts=WIDE_FONTS),
    )


class Depth:
    """Feet below the ground to a y, with an axis that may be broken."""

    def __init__(self, frame, parts, gap):
        """A depth scale.

        Args:
            frame: The Frame.
            parts: The feet drawn: ((0, 600), (1950, 2700)), or one part.
            gap: The y left between two parts.
        """
        self.frame = frame
        self.parts = parts
        self.gap = gap if len(parts) > 1 else 0
        feet = sum(b - a for a, b in parts)
        span = frame.bottom - frame.ground - self.gap * (len(parts) - 1)
        self.scale = span / feet

    def y(self, ft):
        """The y of a depth; a depth in a break is drawn at its edge."""
        y = self.frame.ground
        for i, (a, b) in enumerate(self.parts):
            if ft <= b or i == len(self.parts) - 1:
                return y + max(0, ft - a) * self.scale
            y += (b - a) * self.scale + self.gap
        return y

    def breaks(self):
        """The y ranges of the breaks."""
        out = []
        for (_, b), _ in zip(self.parts, self.parts[1:], strict=False):
            top = self.y(b)
            out.append((top, top + self.gap))
        return out


def esc(text):
    """Text for SVG."""
    return html.escape(text, quote=True)


def fmt(x):
    """A coordinate, short."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def path(points):
    """An SVG path through (x, y) points."""
    return "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points)


def wrap(text, width, font):
    """Text broken into lines that fit a width."""
    per = max(4, int(width / (font * CHAR_EM)))
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if len(trial) <= per or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class Label:
    """A label: its text, column, depth (or y), size, classes, group."""

    def __init__(self, text, col, ft=None, size="tiny", cls="", **kw):
        """A label.

        Args:
            text: Its words.
            col: "left" or "right".
            ft: The depth it belongs to; or kw "y" in the frame's units
                ("sky" for above the ground, "foot" for below the axis).
            size: "lab", "small" or "tiny".
            cls: More classes ("w-rock", "w-q", "w-doclab").
            **kw: "group" (the step group it shows with), "src" (the
                source it names), "y".
        """
        self.text = text
        self.col = col
        self.ft = ft
        self.size = size
        self.cls = cls
        self.group = kw.get("group", "")
        self.src = kw.get("src")
        self.y = kw.get("y")


def place(labels, frame, depth, limit=None):
    """Each label's lines and their baselines, without overlaps.

    Returns:
        A list of (label, x, [(y, line)], (top, bottom)), in each column
        from the top down; labels pushed down from their depth, then up
        from the frame's foot if they would run off it.
    """
    cols = frame.columns()
    placed = []
    for col in ("left", "right"):
        mine = [lb for lb in labels if lb.col == col]
        a, b = cols[col]
        items = []
        for lb in mine:
            font = frame.fonts[lb.size]
            lines = wrap(lb.text, b - a, font)
            if lb.y == "sky":
                want = 4
            elif lb.y == "foot":
                want = frame.bottom + 6
            else:
                want = depth.y(lb.ft) - font * 0.4
            items.append([want, lb, lines, font])
        items.sort(key=lambda it: it[0])
        floor = 0.0
        for it in items:
            it[0] = max(it[0], floor)
            floor = it[0] + len(it[2]) * it[3] * LINE + GAP
        floor_ = frame.height - 2 if limit is None else limit
        for it in reversed(items):
            height = len(it[2]) * it[3] * LINE
            if it[0] + height > floor_:
                it[0] = floor_ - height
            floor_ = it[0] - GAP
        for top, lb, lines, font in items:
            rows = [
                (top + font * (0.9 + LINE * k), line)
                for k, line in enumerate(lines)
            ]
            placed.append((lb, a, rows, (top, top + len(lines) * font * LINE)))
    return placed


def label_svg(item, frame):
    """A placed label's <text> elements."""
    lb, x, rows, _ = item
    cls = " ".join(c for c in ("w-lab", f"w-{lb.size}", lb.cls) if c)
    size = frame.fonts[lb.size]
    src = f' data-src="{lb.src}"' if lb.src else ""
    return "".join(
        f'<text x="{fmt(x)}" y="{fmt(y)}" class="{cls}" '
        f'font-size="{fmt(size)}"{src}>{esc(line)}</text>'
        for y, line in rows
    )


class Well:
    """One drawing's description: everything placed by depth."""

    def __init__(self, key, title, granite=False):
        """An empty drawing.

        Args:
            key: Its id ("outcrop", "granite-rock").
            title: The SVG's title (what a screen reader says).
            granite: Whether its tall frame puts the well further right.
        """
        self.key = key
        self.title = title
        self.granite = granite
        self.parts = None
        self.ticks = ()
        self.gap = 22
        self.layers = []  # (top ft, bottom ft or None, fill, class, src)
        self.contact = None  # (ft, wobble ft) of a wavy contact
        self.water = []  # (top ft, bottom ft, group class, src)
        self.table = None  # (ft, label)
        self.segments = []  # (kind, top ft, bottom ft)
        self.static = []  # ft of static levels
        self.pumping = []  # ft of pumping levels
        self.cone = None  # (static ft, pumping ft)
        self.column = None  # (top ft, bottom ft) water inside the well
        self.flows = []  # polylines of (u, ft) into the well
        self.inflows = []  # short arrows of (u, ft)
        self.rise = None  # (bottom ft, top ft) inside the well
        self.joints = []  # water-bearing fractures, (u, ft) polylines
        self.fracs = []  # other fractures, decoration
        self.doc = None  # (top ft, bottom ft) the documented water
        self.illus = None  # (top ft, bottom ft) an illustrative bracket
        self.transition = None  # (top ft, bottom ft) a hatched band
        self.rain = True
        self.recharge = []  # concept arrows, (u, ft) polylines
        self.labels = []
        self.box = None  # (text) the step-6 box under the drawing
        self.src = {}  # group -> source number

    def svg(self, frame):
        """The drawing in one frame, as an SVG element."""
        parts = self.parts
        limit = None
        if self.box:
            limit = self._box_top(frame) - 3
            frame.bottom = min(frame.bottom, limit - frame.fonts["axis"] * 2)
        depth = Depth(frame, parts, self.gap * frame.height / 440)
        out = []
        tid = f"w-{self.key}-{frame.name}-t"
        out.append(
            f'<svg class="w-f-{frame.name}" viewBox="0 0 {frame.width} '
            f'{frame.height}" role="img" aria-labelledby="{tid}">'
            f'<title id="{tid}">{esc(self.title)}</title>'
        )
        x0, x1 = frame.x0, frame.width
        out.append(
            f'<rect class="w-sky" x="{fmt(x0)}" y="0" width="{fmt(x1 - x0)}"'
            f' height="{fmt(frame.ground)}"/>'
        )
        out.append(self._axis(frame, depth))
        out.append(self._layers(frame, depth))
        out.append(self._water(frame, depth))
        out.append(self._contact(frame, depth))
        out.append(
            f'<path class="w-ground" d="M{fmt(x0)} {fmt(frame.ground)}'
            f'H{fmt(x1)}"/>'
        )
        out.append(self._recharge(frame, depth))
        out.append(self._well(frame, depth))
        out.append(self._levels(frame, depth))
        out.append(self._flows(frame, depth))
        placed = place(self.labels, frame, depth, limit)
        groups = {}
        for item in placed:
            groups.setdefault(item[0].group, []).append(item)
        for group, items in groups.items():
            text = "".join(label_svg(it, frame) for it in items)
            if group:
                out.append(f'<g class="{group}">{text}</g>')
            else:
                out.append(text)
        if self.box:
            out.append(self._box(frame))
        out.append("</svg>")
        self.placed = getattr(self, "placed", {})
        self.placed[frame.name] = (placed, depth)
        return "".join(out)

    def _axis(self, frame, depth):
        x = frame.x0 - 2
        size = frame.fonts["axis"]
        segs, ticks = [], []
        for a, b in self.parts:
            segs.append(f"M{fmt(x)} {fmt(depth.y(a))}V{fmt(depth.y(b))}")
        text = []
        for ft in self.ticks:
            y = depth.y(ft)
            ticks.append(f"M{fmt(x - 4)} {fmt(y)}h4")
            text.append(
                f'<text x="{fmt(x - 5)}" y="{fmt(y + size * 0.35)}" '
                f'font-size="{fmt(size)}">{ft:,}</text>'
            )
        last = depth.y(self.parts[-1][1])
        text.append(
            f'<text x="{fmt(x - 5)}" y="{fmt(last + size * 1.5)}" '
            f'font-size="{fmt(size)}">ft</text>'
        )
        return (
            f'<g class="w-axis" aria-hidden="true"><path d="{"".join(segs)}"/>'
            f'<path d="{"".join(ticks)}"/>{"".join(text)}</g>'
        )

    def _layers(self, frame, depth):
        x0, x1 = frame.x0, frame.width
        out = []
        for top, bottom, fill, cls, src in self.layers:
            y0 = depth.y(top)
            y1 = frame.height if bottom is None else depth.y(bottom)
            attrs = f' class="{cls}"' if cls else ""
            attrs += f' data-src="{src}"' if src else ""
            fill_ = f' fill="url(#{fill})"' if fill else ""
            out.append(
                f'<rect x="{fmt(x0)}" y="{fmt(y0)}" width="{fmt(x1 - x0)}" '
                f'height="{fmt(y1 - y0)}"{fill_}{attrs}/>'
            )
        if self.transition:
            a, b = (depth.y(f) for f in self.transition)
            out.append(
                f'<rect x="{fmt(x0)}" y="{fmt(a)}" width="{fmt(x1 - x0)}" '
                f'height="{fmt(b - a)}" fill="url(#w-p-hatch)" '
                'class="w-transition"/>'
            )
        for line in self.fracs:
            pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
            out.append(f'<path class="w-fracs" d="{path(pts)}"/>')
        for line in self.joints:
            pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
            out.append(f'<path class="w-joint" d="{path(pts)}"/>')
        for a, b in depth.breaks():
            pts = []
            n = 10
            for k in range(n + 1):
                pts.append((x0 + (x1 - x0) * k / n, a + (8 if k % 2 else 0)))
            back = [(x, y + (b - a)) for x, y in reversed(pts)]
            out.append(f'<path class="w-break" d="{path(pts + back)}Z"/>')
        return "".join(out)

    def _contact(self, frame, depth):
        x0, x1 = frame.x0, frame.width
        out = []
        if self.contact:
            ft, wob = self.contact
            pts = []
            n = 6
            for k in range(n + 1):
                x = x0 + (x1 - x0) * k / n
                pts.append((x, depth.y(ft + (wob if k % 2 else -wob))))
            d = path(pts)
            out.append(
                f'<path d="{d} V{fmt(frame.height)} H{fmt(x0)}Z" '
                'fill="url(#w-p-core)"/>'
                f'<path class="w-contact" d="{d}"/>'
            )
        return "".join(out)

    def _water(self, frame, depth):
        x0, x1 = frame.x0, frame.width
        out = []
        for top, bottom, cls, src in self.water:
            y0, y1 = depth.y(top), depth.y(bottom)
            src_ = f' data-src="{src}"' if src else ""
            classes = " ".join(c for c in ("w-water", cls) if c)
            out.append(f'<g class="{classes}"{src_}>')
            if y1 > y0:
                out.append(
                    f'<rect x="{fmt(x0)}" y="{fmt(y0)}" width="{fmt(x1 - x0)}"'
                    f' height="{fmt(y1 - y0)}" fill="url(#w-p-water)"/>'
                )
            if self.table and top == self.table:
                out.append(
                    f'<path class="w-wt" d="M{fmt(x0)} {fmt(y0)}H{fmt(x1)}"/>'
                )
            for line in self.joints:
                pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
                out.append(f'<path class="w-fracw" d="{path(pts)}"/>')
            out.append("</g>")
        return "".join(out)

    def _recharge(self, frame, depth):
        src = self.src.get("w-recharge")
        src_ = f' data-src="{src}"' if src else ""
        out = [f'<g class="w-recharge"{src_}>']
        if self.rain:
            marks = "".join(
                f"M{fmt(frame.u(u))} 3l-4 11"
                for u in (-0.75, -0.45, 0.55, 0.85)
            )
            out.append(f'<path class="w-rain" d="{marks}"/>')
        for line in self.recharge:
            pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
            out.append(
                f'<path class="w-flow w-concept" d="{path(pts)}"{ARROW}/>'
            )
        out.append("</g>")
        return "".join(out)

    def _well(self, frame, depth):
        x, h = frame.well_x, frame.half
        src = self.src.get("w-well")
        src_ = f' data-src="{src}"' if src else ""
        out = [
            (
                f'<g class="w-well"{src_}><rect x="{fmt(x - h - 1)}" '
                f'y="{fmt(frame.ground - 12)}" width="{fmt(2 * h + 2)}" '
                'height="12" class="w-head"/>'
            )
        ]
        for kind, top, bottom in self.segments:
            y0, y1 = depth.y(top), depth.y(bottom)
            inset = 1 if kind == "open" else 0
            d = (
                f"M{fmt(x - h + inset)} {fmt(y0)}V{fmt(y1)}"
                f"M{fmt(x + h - inset)} {fmt(y0)}V{fmt(y1)}"
            )
            cls = {"casing": "w-casing", "screen": "w-screen"}.get(
                kind, "w-openhole"
            )
            out.append(
                f'<path class="{cls}" d="{d}" data-seg="{kind}" '
                f'data-well="{self.key}"/>'
            )
        for a, b in depth.breaks():
            out.append(
                f'<rect x="{fmt(x - h - 2)}" y="{fmt(a + 2)}" '
                f'width="{fmt(2 * h + 4)}" height="{fmt(b - a - 4)}" '
                'class="w-break"/>'
            )
        out.append("</g>")
        return "".join(out)

    def _levels(self, frame, depth):
        x, h = frame.well_x, frame.half
        src = self.src.get("w-levels")
        src_ = f' data-src="{src}"' if src else ""
        out = [f'<g class="w-levels"{src_}>']
        if self.column:
            top, bottom = self.column
            for a, b in self._unbroken(depth, top, bottom):
                out.append(
                    f'<rect x="{fmt(x - h + 1)}" y="{fmt(a)}" '
                    f'width="{fmt(2 * h - 2)}" height="{fmt(b - a)}" '
                    'class="w-column"/>'
                )
        if self.cone:
            s, p = (depth.y(f) for f in self.cone)
            left, right = frame.u(-0.94), frame.u(0.94)
            out.append(
                f'<path class="w-cone" d="M{fmt(left)} {fmt(s + 1)} '
                f"Q{fmt((left + x) / 2 + 10)} {fmt(s + 4)} {fmt(x - h)} "
                f"{fmt(p)} M{fmt(x + h)} {fmt(p)} Q{fmt((right + x) / 2 - 10)} "
                f'{fmt(s + 4)} {fmt(right)} {fmt(s + 1)}"/>'
            )
        for ft in self.static:
            y = depth.y(ft)
            out.append(
                f'<path class="w-static" d="M{fmt(x - h)} {fmt(y)}'
                f'h{fmt(2 * h)}"/>'
            )
        for ft in self.pumping:
            y = depth.y(ft)
            out.append(
                f'<path class="w-pump" d="M{fmt(x - h - 2)} {fmt(y)}'
                f'h{fmt(2 * h + 4)}"/>'
            )
        if self.rise:
            for a, b in self._unbroken(depth, self.rise[1], self.rise[0]):
                out.append(
                    f'<path class="w-move w-up" data-rise="{self.key}" '
                    f'd="M{fmt(x)} {fmt(b - 2)}V{fmt(a + 2)}"/>'
                )
        out.append("</g>")
        return "".join(out)

    def _unbroken(self, depth, top, bottom):
        """The y ranges of top..bottom ft, less the breaks."""
        a, b = depth.y(top), depth.y(bottom)
        cuts = [(a, b)]
        for c, d in depth.breaks():
            nxt = []
            for p, q in cuts:
                if q <= c or p >= d:
                    nxt.append((p, q))
                    continue
                if p < c:
                    nxt.append((p, c))
                if q > d:
                    nxt.append((d, q))
            cuts = nxt
        return cuts

    def _flows(self, frame, depth):
        src = self.src.get("w-flow")
        src_ = f' data-src="{src}"' if src else ""
        out = [f'<g class="w-water w-flowg"{src_}>']
        for line in self.flows:
            pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
            out.append(
                f'<path class="w-move" data-flow="{self.key}" d="{path(pts)}"/>'
            )
        for line in self.inflows:
            pts = [(frame.u(u), depth.y(ft)) for u, ft in line]
            out.append(
                f'<path class="w-inflow" data-inflow="{self.key}" '
                f'd="{path(pts)}"{ARROW}/>'
            )
        if self.doc:
            a, b = (depth.y(f) for f in self.doc)
            x = frame.well_x + frame.half + 4
            out.append(f'<path class="w-doc" d="M{fmt(x)} {fmt(a)}V{fmt(b)}"/>')
        if self.illus:
            a, b = (depth.y(f) for f in self.illus)
            x = frame.well_x + frame.half + 5
            out.append(
                f'<path class="w-illus" d="M{fmt(x)} {fmt(a)}V{fmt(b)}'
                f'M{fmt(x - 3)} {fmt(a)}h3M{fmt(x - 3)} {fmt(b)}h3"/>'
            )
        out.append("</g>")
        return "".join(out)

    def _box_top(self, frame):
        size = frame.fonts["tiny"]
        width = frame.width - frame.x0 - 8
        lines = wrap(self.box, width - 12, size)
        return frame.height - (len(lines) * size * LINE + 10) - 4

    def _box(self, frame):
        size = frame.fonts["tiny"]
        x0 = frame.x0 + 4
        width = frame.width - x0 - 4
        lines = wrap(self.box, width - 12, size)
        height = len(lines) * size * LINE + 10
        top = frame.height - height - 4
        src = self.src.get("w-unsure")
        src_ = f' data-src="{src}"' if src else ""
        text = "".join(
            f'<text x="{fmt(x0 + 6)}" '
            f'y="{fmt(top + 5 + size * (0.9 + LINE * k))}"'
            f' class="w-lab w-tiny w-q" font-size="{fmt(size)}">{esc(line)}'
            "</text>"
            for k, line in enumerate(lines)
        )
        self.box_top = getattr(self, "box_top", {})
        self.box_top[frame.name] = top
        return (
            f'<g class="w-unsure"{src_}><rect x="{fmt(x0)}" y="{fmt(top)}" '
            f'width="{fmt(width)}" height="{fmt(height)}" class="w-qbox"/>'
            f"{text}</g>"
        )


def ticks(top, step):
    """Axis ticks from 0 to top every step."""
    return tuple(range(0, int(top) + 1, step))


def outcrop(f, d, src):
    """The outcrop well: the Hickory Sandstone Member at the surface."""
    depth, static = f["outcrop_depth"], f["outcrop_level"]
    pumping = f["pumping_mid"]
    contact = depth + 50  # schematic: the granite below the well
    bottom = (int(contact / 50) + 2) * 50
    screen = static + (depth - static) * 0.55
    w = Well(
        "outcrop",
        (
            "Outcrop well: the Hickory Sandstone Member at the surface over "
            "granite. Below the water table, water moves through the "
            "connected pore spaces of the saturated sandstone into the "
            "well's producing interval, a screen or open hole (schematic), "
            "below blank casing. The rain arrows are conceptual."
        ),
    )
    w.parts = ((0, bottom),)
    w.ticks = ticks(bottom, 100)
    w.layers = [(0, contact, "w-p-sand", "", None)]
    w.contact = (contact, 8)
    w.water = [(static, contact + 8, "", src["mason"])]
    w.table = static
    w.segments = [("casing", 0, screen), ("screen", screen, depth)]
    w.static = [static]
    w.pumping = [pumping]
    w.cone = (static, pumping)
    mid = (screen + depth) / 2
    w.flows = [
        ((-0.94, contact - 30), (-0.5, mid + 12), ("wl", mid + 4)),
        ((-0.94, static + 25), (-0.5, screen - 4), ("wl", screen + 6)),
        ((0.94, contact - 20), (0.5, mid + 8), ("wr", mid)),
        ((0.94, screen - 4), (0.5, screen + 8), ("wr", screen + 12)),
    ]
    w.inflows = [
        ((-0.25, mid + 2), ("wl", mid)),
        ((0.25, mid - 4), ("wr", mid - 6)),
    ]
    w.recharge = [
        ((-0.7, 4), (-0.7, static - 6)),
        ((0.8, 4), (0.8, static - 6)),
    ]
    w.src = {
        "w-recharge": src["recharge_outcrop"],
        "w-levels": src["twdb"],
        "w-well": src["construction"],
        "w-unsure": src["twdb"],
    }
    w.labels = [
        Label(
            "rain soaks in (conceptual)",
            "left",
            y="sky",
            size="small",
            group="w-recharge",
        ),
        Label("water table", "left", static, size="small", group="w-water"),
        Label(
            "Hickory Sandstone Member",
            "left",
            (static + contact) / 2 + 10,
            size="lab",
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label(
            "Precambrian granite",
            "left",
            contact + 30,
            size="lab",
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label("casing", "right", 8, group=""),
        Label("static", "right", static, size="small", group="w-levels"),
        Label(
            "pumping, assumed", "right", pumping, size="small", group="w-levels"
        ),
        Label(f"{depth:,} ft", "right", depth, size="small"),
        Label("screen or open hole (schematic)", "right", depth + 6),
        Label(
            f"Drawdown: assumed {f['drawdown_low']}{DASH}"
            f"{f['drawdown_high']} ft",
            "left",
            y="foot",
            size="small",
            cls="w-q",
            group="w-unsure",
        ),
    ]
    return w


def granite_rock(f, d, src):
    """The granite example: one documented well, drawn to its own depth."""
    depth = f["example_depth"]
    top, bottom = f["example_water_top"], f["example_water_bottom"]
    water = (top + bottom) / 2
    casing = f["example_casing_ft"]
    static = f["example_level"]
    w = Well(
        "granite-rock",
        (
            f"Example: TWDB driller's report {f['example_report']} "
            f"({f['example_county']} County, {f['example_year']}), drawn to "
            f"its own depth scale, 0 to {depth} feet. "
            + "; ".join(
                f"{t} to {b:g} feet" if a else f"{t} to {b:g} foot"
                for a, b, t in d["example_layers"]
            )
            + f". {f['example_casing'].capitalize()} casing to {casing} feet "
            "keeps the gravel out of the well; open hole below. Water moves "
            "through connected fractures in the granite into the open hole, "
            f"where the driller reported water at {f['example_water']} feet "
            "(documented). The fractures are schematic: inferred flow "
            f"through fractures. Static level {static} feet. The recharge "
            "arrows are conceptual; the route is not documented."
        ),
        granite=True,
    )
    w.parts = ((0, depth),)
    w.ticks = (*ticks(depth - 25, 50), depth)
    layers = d["example_layers"]
    w.layers = [(0, None, "w-p-core", "", None)]
    for a, b, _ in layers[:-1]:
        fill = "w-p-grus" if a else None
        cls = "" if a else "w-soil"
        w.layers.append((a, b, fill, cls, None))
    w.joints = [
        (
            (-0.94, water * 0.53),
            (-0.6, water * 0.66),
            (-0.38, water * 0.87),
            ("wl", water),
        ),
        (
            (0.97, water * 0.71),
            (0.68, water * 0.85),
            (0.39, water * 0.96),
            ("wr", water),
        ),
    ]
    w.fracs = [
        ((-0.25, depth * 0.17), (-0.17, depth * 0.29)),
        ((0.5, depth * 0.45), (0.68, depth * 0.58)),
        ((-0.53, depth * 0.78), (-0.4, depth * 0.9)),
    ]
    w.water = [(top, top, "w-water-rock", src["usgs_rock"])]
    w.flows = list(w.joints)
    w.inflows = [
        ((-0.25, water - 4), ("wl", water)),
        ((0.25, water - 2), ("wr", water)),
    ]
    w.doc = (top, bottom)
    w.segments = [("casing", -3, casing), ("open", casing, depth)]
    w.static = [static]
    w.recharge = [
        ((-0.8, 3), (-0.8, casing - 2)),
        ((0.6, 3), (0.6, casing - 2)),
    ]
    w.src = {
        "w-recharge": src["example"],
        "w-levels": src["example"],
        "w-well": src["example"],
        "w-unsure": src["cm16"],
        "w-flow": src["usgs_rock"],
    }
    w.labels = [
        Label(
            "recharge: conceptual, route not documented",
            "left",
            y="sky",
            cls="w-conceptlab",
            group="w-recharge",
        ),
        Label(
            f"{f['example_gravel']}, behind blank casing",
            "left",
            (layers[1][0] + layers[1][1]) / 2,
            cls="w-rock",
            src=src["example"],
        ),
        Label(
            f"{f['example_rock']}, intact between fractures",
            "left",
            depth * 0.33,
            cls="w-rock",
            src=src["example"],
        ),
        Label(
            "schematic: inferred flow through fractures",
            "left",
            water * 0.72,
            group="w-water",
        ),
        Label(f"{f['example_casing']} casing to {casing} ft", "right", 4),
        Label(
            f"static {static} ft (no pumping level measured)",
            "right",
            static,
            group="w-levels",
        ),
        Label("open hole", "right", depth * 0.5),
        Label(
            f"documented: water at {f['example_water']} ft",
            "right",
            top,
            cls="w-doclab",
            group="w-water",
        ),
        Label(f"{depth} ft", "right", depth, size="small"),
    ]
    w.box = (
        "The sources reviewed do not establish Hickory Aquifer water "
        "supplying these granite wells."
    )
    return w


def granite_gravel(f, d, src):
    """The screened gravel-and-granite well, with illustrative values."""
    g = {k[7:]: v for k, v in f.items() if k.startswith("gravel_")}
    depth = g["depth"]
    w = Well(
        "granite-gravel",
        (
            "Screened gravel and granite, illustrative: topsoil, then "
            f"granite gravel and weathered granite to {g['gravel_bottom']} "
            "feet, a schematic transition into fractured granite to "
            f"{g['transition_bottom']} feet, and granite bedrock below. Blank "
            f"casing to {g['casing_bottom']} feet, then a screen to "
            f"{depth} feet. Water can enter through connected spaces in the "
            "gravel and weathered material, and through water-bearing "
            "fractures; the flow paths are schematic and their shares are "
            f"not known. Static level about {g['static']} feet."
        ),
        granite=True,
    )
    bottom = depth + 10
    w.parts = ((0, bottom),)
    w.ticks = ticks(bottom, 25)
    w.layers = [
        (0, None, "w-p-core", "", None),
        (g["topsoil"], g["transition_bottom"], "w-p-grus", "", None),
        (0, g["topsoil"], None, "w-soil", None),
    ]
    w.transition = (g["gravel_bottom"], g["transition_bottom"])
    entry = g["entry_bottom"]
    cas = g["casing_bottom"]
    w.joints = [
        (
            (-0.94, g["transition_bottom"]),
            (-0.6, entry - 4),
            (-0.32, entry - 5),
            ("wl", entry - 6),
        ),
        (
            (0.97, depth + 6),
            (0.68, depth + 1),
            (0.37, depth - 3),
            ("wr", depth - 4),
        ),
    ]
    w.fracs = [
        ((-0.7, depth + 1), (-0.62, depth + 8)),
        ((0.68, g["transition_bottom"] + 1), (0.76, depth)),
    ]
    w.water = [
        (g["static"], g["gravel_bottom"], "w-water-gravel", src["heath84"])
    ]
    w.table = g["static"]
    w.flows = [
        ((-0.94, cas - 12), (-0.5, cas - 4), ("wl", cas + 2)),
        ((-0.94, cas - 4), (-0.5, cas + 1), ("wl", cas + 4)),
        *w.joints,
    ]
    w.inflows = [
        ((-0.25, cas), ("wl", cas + 2)),
        ((0.25, cas + 1), ("wr", cas + 3)),
        ((-0.25, entry - 6), ("wl", entry - 6)),
        ((0.25, depth - 6), ("wr", depth - 4)),
    ]
    w.illus = (cas, entry)
    w.segments = [("casing", -3, cas), ("screen", cas, depth)]
    w.static = [g["static"]]
    w.recharge = [
        ((-0.8, 3), (-0.8, g["static"] - 2)),
        ((0.6, 3), (0.6, g["static"] - 2)),
    ]
    w.src = {
        "w-recharge": src["hunt"],
        "w-well": src["construction"],
        "w-unsure": src["cm16"],
        "w-flow": src["heath84"],
    }
    w.labels = [
        Label(
            "recharge: conceptual",
            "left",
            y="sky",
            cls="w-conceptlab",
            group="w-recharge",
        ),
        Label(
            "granite gravel, weathered granite",
            "left",
            g["topsoil"] + 4,
            cls="w-rock",
            src=src["ctgcd"],
        ),
        Label("saturated", "left", g["static"] + 6, group="w-water"),
        Label(
            "schematic transition to fractured granite",
            "left",
            g["gravel_bottom"],
        ),
        Label(
            "granite bedrock",
            "left",
            g["transition_bottom"] + 4,
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label(
            "possible entry paths; contributions vary",
            "left",
            depth + 2,
            group="w-water",
        ),
        Label(f"blank casing to {cas} ft", "right", 4),
        Label(
            f"static about {g['static']} ft (illustrative)",
            "right",
            g["static"],
            group="w-levels",
        ),
        Label(f"screen {cas}{DASH}{depth} ft", "right", cas),
        Label(
            f"illustrative water entry {cas}{DASH}{entry} ft",
            "right",
            cas + 6,
            group="w-water",
        ),
        Label(f"{depth} ft", "right", depth, size="small"),
    ]
    w.box = (
        "The sources reviewed do not establish Hickory Aquifer water "
        "supplying these granite wells."
    )
    return w


def deep(f, d, params, src):
    """The deep downdip well, its axis broken."""
    depth = f["deep_depth"]
    top = d["deep_top"]
    sand_bottom = max(d["deep_bottom"], depth + 30)
    levels = (f["deep_level_gwdb"], f["deep_level_sdr"])
    pump = [lv + f["deep_drawdown"] for lv in levels]
    a, b = params.DEEP_BREAK_FT
    if not (max(pump) < a < b < top):
        raise SystemExit(
            f"the deep drawing's break {a}-{b} ft does not lie between the "
            f"pumping level ({max(pump)} ft) and the aquifer ({top:.0f} ft)"
        )
    bottom = (int(sand_bottom / 100) + 2) * 100
    screen = top + (depth - top) * 0.4
    w = Well(
        "deep",
        (
            "Deep downdip well: younger rock at the surface; the Hickory "
            f"Sandstone Member about {f['deep_top']:,} feet down (the model "
            "median), confined, over Precambrian rock. The axis is broken: "
            f"{b - a:,} feet are left out. Water moves through the confined "
            "sandstone into the producing interval, perforated casing or a "
            "screen (schematic), and rises inside the well to a static level "
            f"of about {levels[0]} to {levels[1]} feet. The long-term pathway "
            "from the outcrop is conceptual."
        ),
    )
    w.parts = ((0, a), (b, bottom))
    w.ticks = (*ticks(a, 200), *range((b // 400 + 1) * 400, bottom + 1, 400))
    w.layers = [
        (0, top, "w-p-young", "", None),
        (top, sand_bottom, "w-p-sand", "", None),
        (sand_bottom, None, "w-p-core", "", None),
    ]
    w.water = [(top, sand_bottom, "", src["mason"])]
    w.segments = [("casing", 0, screen), ("screen", screen, depth)]
    w.static = list(levels)
    w.pumping = pump
    w.column = (levels[0], depth)
    w.rise = (screen, levels[0])
    mid = (screen + depth) / 2
    w.flows = [
        ((-0.94, sand_bottom - 40), (-0.5, mid + 20), ("wl", mid + 10)),
        ((0.94, top + 60), (0.5, mid - 10), ("wr", mid - 20)),
    ]
    w.inflows = [
        ((-0.25, mid + 4), ("wl", mid)),
        ((0.25, mid - 2), ("wr", mid - 6)),
    ]
    w.rain = False
    w.recharge = [((-0.94, top + 40), (-0.4, top + 40))]
    w.src = {
        "w-recharge": src["cm16"],
        "w-levels": src["twdb"],
        "w-well": src["twdb"],
        "w-unsure": src["costs"],
        "w-flow": src["mason"],
    }
    w.labels = [
        Label(
            "younger rock",
            "left",
            150,
            size="lab",
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label(f"{b - a:,} ft left out", "right", a + 40, cls="w-breaklab"),
        Label(
            f"aquifer top about {f['deep_top']:,} ft (model median)",
            "left",
            top - 60,
        ),
        Label(
            "Hickory Sandstone Member",
            "left",
            top + 4,
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label(
            "long-term pathway (conceptual)",
            "left",
            top + 50,
            cls="w-conceptlab",
            group="w-recharge",
        ),
        Label(
            "Precambrian",
            "left",
            sand_bottom + 20,
            size="lab",
            cls="w-rock",
            src=src["sgmc"],
        ),
        Label("casing", "right", 20),
        Label(
            f"static about {levels[0]}{DASH}{levels[1]} ft",
            "right",
            levels[0],
            group="w-levels",
        ),
        Label(
            f"pumping about {f['deep_drawdown']} ft lower",
            "right",
            pump[1],
            group="w-levels",
        ),
        Label("confined", "right", top + 10, size="small", group="w-water"),
        Label(f"{depth:,} ft", "right", depth, size="small"),
        Label("perforated casing or screen (schematic)", "right", depth + 20),
        Label(
            "Cost: a planning estimate",
            "right",
            y="foot",
            size="small",
            cls="w-q",
            group="w-unsure",
        ),
    ]
    return w


def scale_svg(f):
    """Step 05's median depths, to one scale."""
    deep_ = f["deep_depth"]
    top = (deep_ // 1000 + 1) * 1000
    y0, y1 = 14, 140
    k = (y1 - y0) / top
    size = 13
    bars = (
        ("Outcrop", f["outcrop_depth"], "w-bar-out", 80),
        ("Granite", f["granite_depth"], "w-bar-gra", 160),
        ("Downdip", deep_, "w-bar-deep", 240),
    )
    out = [
        '<svg viewBox="0 0 330 180" role="img" aria-labelledby="w-scale-t">'
        '<title id="w-scale-t">Median well depths drawn to one scale: '
        + ", ".join(f"{n.lower()} {d:,} feet" for n, d, _, _ in bars)
        + ".</title>",
        '<g class="w-axis"><path d="M66 14V140"/>',
    ]
    for ft in range(0, top + 1, 1000):
        y = y0 + ft * k
        out.append(
            f'<path d="M62 {fmt(y)}h4"/><text x="60" y="{fmt(y + 4)}" '
            f'font-size="{size}">{ft:,}</text>'
        )
    out.append("</g>")
    for name, ft, cls, x in bars:
        h = max(2.0, ft * k)
        out.append(
            f'<rect x="{x}" y="{y0}" width="50" height="{fmt(h)}" '
            f'class="{cls}"/>'
            f'<text x="{x + 25}" y="{fmt(y0 + h + 15)}" text-anchor="middle" '
            f'class="w-lab w-small" font-size="{size}">{ft:,} ft</text>'
            f'<text x="{x + 25}" y="174" text-anchor="middle" '
            f'class="w-lab w-small" font-size="{size}">{name}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def make(f, d, params, src):
    """Every drawing: {slot: SVG markup}, and the wells drawn.

    Args:
        f: The figures.
        d: The drawing's extra values (figures.make()'s third result).
        params: src/site/wells/params.py.
        src: The source numbers, by name.

    Returns:
        ({"outcrop", "granite-rock", "granite-gravel", "deep", "scale"}:
        markup, [Well]).
    """
    wells = [
        outcrop(f, d, src),
        granite_rock(f, d, src),
        granite_gravel(f, d, src),
        deep(f, d, params, src),
    ]
    out = {}
    for w in wells:
        out[w.key] = "".join(
            w.svg(frame) for frame in frames(granite=w.granite)
        )
    out["scale"] = scale_svg(f)
    return out, wells
