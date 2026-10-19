"""The page's drawings as SVG files: the four maps, the locator, the slice.

Each file stands alone (the page shows it as an <img>), so each carries its
own patterns, colours and fonts. The maps are drawn from maps.make()'s
outlines and dots; section.svg from section.json's data, every layer shown,
for readers without JavaScript and for print (docs/assets/land.js draws the
same layers at the figure's own width and reveals them step by step).
Standard library only.
"""

import html

from . import params

NS = 'xmlns="http://www.w3.org/2000/svg"'
FONT = "font-family=\"'Source Sans 3', Arial, sans-serif\""
INK = "#282b24"
MUTED = "#6c6259"
WINE = "#5a1e2e"
PAPER = "#f4efe5"
SAND = "#c7976f"
SAND_MARK = "#8f6646"
CORE = "#e7e1d4"
CORE_MARK = "#a59a88"
YOUNGER = "#d3ccbd"
YOUNGER_MARK = "#ada491"
WATER = "#6d8c86"
WATER_MARK = "#93aca6"
WATER_EDGE = "#47625c"
HIGH = "#d6ccb7"
TOGETHER = "#b98457"
TOGETHER_EDGE = "#7d5636"
GRID = "#b1a797"
STROKE = 'vector-effect="non-scaling-stroke"'

# The maps' patterns: the formation (dotted sand) and the core (crosses).
MAP_DEFS = (
    "<defs>"
    '<pattern id="sand" width="9" height="8" patternUnits="userSpaceOnUse">'
    f'<rect width="9" height="8" fill="{SAND}"/>'
    f'<circle cx="2" cy="2" r="1.1" fill="{SAND_MARK}"/>'
    f'<circle cx="6.5" cy="6" r=".9" fill="{SAND_MARK}"/></pattern>'
    '<pattern id="core" width="18" height="18" patternUnits="userSpaceOnUse">'
    f'<rect width="18" height="18" fill="{CORE}"/>'
    '<path d="M3 6h6M6 3v6M12 14h5M14.5 11.5v5" '
    f'stroke="{CORE_MARK}" stroke-width="1.1"/></pattern>'
    "</defs>"
)


def svg_open(width, height, label):
    """An SVG file's opening tag, its title and its background."""
    title = html.escape(label, quote=False)
    return (
        f'<svg {NS} viewBox="0 0 {width:g} {height:g}" width="{width:g}" '
        f'height="{height:g}" role="img"><title>{title}</title>'
        f'<rect width="{width:g}" height="{height:g}" fill="{PAPER}"/>'
    )


def area(d, fill, extra=""):
    """A filled outline (even-odd), or nothing when it is empty."""
    if not d:
        return ""
    return f'<path d="{d}" fill="{fill}" fill-rule="evenodd"{extra}/>'


def map_svg(m, kind, label):
    """One of the four maps, or the locator.

    Args:
        m: maps.make()'s outlines and dots.
        kind: "high", "sand", "water", "together" or "locator".
        label: The drawing's title.

    Returns:
        The SVG file's text.
    """
    w, h = m["w"], m["h"]
    out = [svg_open(w, h, label), MAP_DEFS]
    if kind == "high":
        out.append(area(m["high"], HIGH))
    elif kind == "sand":
        out.append(area(m["precambrian"], "url(#core)"))
        out.append(area(m["hickory"], "url(#sand)"))
    elif kind == "water":
        out.append(area(m["precambrian"], CORE))
        out.append(area(m["hickory"], SAND, ' fill-opacity=".28"'))
        for name in params.MAP_DRAW_ORDER:
            cls = params.CLASSES.index(name)
            dots = "".join(
                f'<circle cx="{x:g}" cy="{y:g}" r="{params.MAP_DOT_R:g}"/>'
                for x, y, c in m["wells"]
                if c == cls
            )
            if dots:
                out.append(
                    f'<g fill="{params.CLASS_COLOURS[cls]}" '
                    f'fill-opacity=".85">{dots}</g>'
                )
    elif kind == "together":
        out.append(area(m["high"], HIGH, ' fill-opacity=".45"'))
        out.append(area(m["hickory"], SAND, ' fill-opacity=".3"'))
        out.append(
            area(
                m["together"],
                TOGETHER,
                f' stroke="{TOGETHER_EDGE}" stroke-width=".6" {STROKE}',
            )
        )
    elif kind == "locator":
        out.append(area(m["hickory"], "url(#sand)"))
        out.append(area(m["precambrian"], "url(#core)"))
    else:
        raise ValueError(kind)
    out.append(
        f'<path d="{m["district"]}" fill="none" stroke="{WINE}" '
        f'stroke-width="1.5" stroke-linejoin="round" fill-rule="evenodd" '
        f"{STROKE}/>"
    )
    if kind == "locator":
        (ax, ay), (bx, by) = m["line"]
        font = f'{FONT} fill="{INK}" font-weight="600" font-size="32"'
        out.append(
            f'<line x1="{ax:g}" y1="{ay:g}" x2="{bx:g}" y2="{by:g}" '
            f'stroke="{INK}" stroke-width="1.6" {STROKE}/>'
            f'<circle cx="{ax:g}" cy="{ay:g}" r="7" fill="{INK}"/>'
            f'<circle cx="{bx:g}" cy="{by:g}" r="7" fill="{INK}"/>'
            f'<text x="{ax + 16:g}" y="{ay + 10:g}" {font}>NW</text>'
            f'<text x="{bx + 12:g}" y="{by + 32:g}" {font}>SE</text>'
        )
    bar = m["scale"]
    out.append(
        f'<line x1="14" x2="{14 + bar:g}" y1="{h - 16:g}" y2="{h - 16:g}" '
        f'stroke="{MUTED}" stroke-width="1.5" {STROKE}/>'
        f'<text x="14" y="{h - 24:g}" font-size="22" {FONT} fill="{MUTED}">'
        f"{params.SCALE_KM:g} km</text>"
    )
    out.append("</svg>")
    return "".join(out)


def fmt(n):
    """A number as the page writes it: thousands separated, a true minus."""
    text = f"{round(n):,}"
    return text.replace("-", "\N{MINUS SIGN}")


class Slice:
    """The slice drawn at one width, every layer shown (as land.js draws).

    Attributes:
        s: section.json's data.
        width: The drawing's width in CSS pixels.
    """

    def __init__(self, section, width=params.SECTION_SVG_W):
        """Sets the scales; the drawing is as tall as the exaggeration asks."""
        self.s = section
        self.width = width
        self.ml, self.mr, self.mt, self.mb = 54, 14, 46, 38
        self.pw = width - self.ml - self.mr
        self.kx = self.pw / section["length_ft"]
        self.ky = self.kx * section["ve"]
        ph = (section["z_top"] - section["z_base"]) * self.ky
        self.height = round(self.mt + ph + self.mb)
        self.gs = [g[0] for g in section["ground"]]
        self.gz = [g[1] for g in section["ground"]]

    def x(self, s):
        """The drawing's x of a distance along the slice."""
        return self.ml + s * self.kx

    def y(self, z):
        """The drawing's y of an elevation."""
        return self.mt + (self.s["z_top"] - z) * self.ky

    def pt(self, s, z):
        """A point "x,y" to one decimal."""
        return f"{self.x(s):.1f},{self.y(z):.1f}"

    def ground(self, s):
        """The ground at s, between the drawn samples."""
        gs, gz = self.gs, self.gz
        if s <= gs[0]:
            return gz[0]
        if s >= gs[-1]:
            return gz[-1]
        lo, hi = 0, len(gs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if gs[mid] <= s:
                lo = mid
            else:
                hi = mid
        return gz[lo] + (gz[hi] - gz[lo]) * (s - gs[lo]) / (gs[hi] - gs[lo])

    def samples(self, a, b):
        """a, the ground's samples between a and b, and b."""
        return [a, *(s for s in self.gs if a < s < b), b]

    def band(self, has, top, bot, fill, stroke="none"):
        """A unit's band: each run of columns that has it, top to bottom."""
        runs, cur = [], None
        for c in self.s["cols"]:
            if not has(c):
                cur = None
                continue
            if cur is None:
                cur = ([], [])
                runs.append(cur)
            for s in self.samples(c[0], c[1]):
                cur[0].append(self.pt(s, top(c, s)))
                cur[1].append(self.pt(s, bot(c, s)))
        d = "".join("M" + "L".join(t + b[::-1]) + "Z" for t, b in runs if t)
        return (
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            'stroke-width=".6" stroke-linejoin="round"/>'
        )

    def svg(self, label):
        """The whole drawing.

        Args:
            label: The drawing's title.

        Returns:
            The SVG file's text.
        """
        s = self.s
        w, h, ml, mt, pw = self.width, self.height, self.ml, self.mt, self.pw
        g = self.ground
        out = [svg_open(w, h, label), self.defs()]
        out.append(f'<g {FONT} font-size="11" fill="{MUTED}">')
        step = 500
        z = -(-s["z_base"] // step) * step
        while z <= s["z_top"]:
            out.append(
                f'<line x1="{ml}" x2="{ml + pw:.1f}" y1="{self.y(z):.1f}" '
                f'y2="{self.y(z):.1f}" stroke="{GRID}" stroke-width=".5" '
                'stroke-dasharray="1 3"/>'
                f'<text x="{ml - 5}" y="{self.y(z) + 3.5:.1f}" '
                f'text-anchor="end">{fmt(z)}</text>'
            )
            z += step
        out.append(f'<text x="2" y="{mt - 14}">feet above sea level</text>')
        mile = params.FT_PER_MI
        for mi in range(0, int(s["length_ft"] // mile) + 1, 5):
            x = self.x(mi * mile)
            yb = self.y(s["z_base"])
            anchor = "start" if mi == 0 else "middle"
            out.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{yb:.1f}" '
                f'y2="{yb + 4:.1f}" stroke="{MUTED}"/>'
                f'<text x="{x:.1f}" y="{yb + 15:.1f}" text-anchor="{anchor}">'
                f"{'0 mi' if mi == 0 else mi}</text>"
            )
        out.append("</g>")
        ground_d = "L".join(self.pt(a, b) for a, b in s["ground"])
        out.append('<g clip-path="url(#clip)">')
        out.append(
            f'<path d="M{ground_d}L{self.pt(s["length_ft"], s["z_base"])}'
            f'L{self.pt(0, s["z_base"])}Z" fill="#ddd6c8"/>'
        )

        def hk_top(c, x):
            return g(x) if c[5] == params.HICKORY_LAYER else min(c[2], g(x))

        def core_top(c, x):
            if c[5] == params.PRECAMBRIAN_LAYER:
                return g(x)
            return min(c[4], g(x))

        out.append(
            self.band(
                lambda c: c[5] < params.HICKORY_LAYER,
                lambda c, x: g(x),
                lambda c, x: min(c[2] if c[2] is not None else c[4], g(x)),
                "url(#younger)",
            )
        )
        out.append(
            self.band(
                lambda c: True, core_top, lambda c, x: s["z_base"], "url(#core)"
            )
        )
        out.append(
            self.band(
                lambda c: c[2] is not None,
                hk_top,
                lambda c, x: min(c[3], g(x)),
                "url(#water)",
                WATER_EDGE,
            )
        )
        for a, b in s["surface_hickory"]:
            top = [(self.x(x), self.y(g(x))) for x in self.samples(a, b)]
            d = "L".join(f"{px:.1f},{py - 1:.1f}" for px, py in top)
            d += "L" + "L".join(
                f"{px:.1f},{py + 4:.1f}" for px, py in reversed(top)
            )
            out.append(
                f'<path d="M{d}Z" fill="{SAND}" stroke="{SAND_MARK}" '
                'stroke-width=".5"/>'
            )
        for f in s["faults"]:
            out.append(
                f'<line x1="{self.x(f):.1f}" x2="{self.x(f):.1f}" '
                f'y1="{self.y(g(f)):.1f}" y2="{self.y(s["z_base"]):.1f}" '
                f'stroke="{INK}" stroke-width=".9" stroke-dasharray="4 3" '
                'opacity=".7"/>'
            )
        out.append("</g>")
        for a, b in s["district"]:
            x0, x1 = self.x(a), self.x(b)
            out.append(
                f'<rect x="{x0:.1f}" y="{mt - 18}" width="{x1 - x0:.1f}" '
                f'height="{self.y(s["z_base"]) - mt + 18:.1f}" fill="{WINE}" '
                'fill-opacity=".07"/>'
                f'<rect x="{x0:.1f}" y="{mt - 18}" width="{x1 - x0:.1f}" '
                f'height="4" fill="{WINE}"/>'
            )
        first, last = s["district"][0], s["district"][-1]
        mid = (self.x(first[0]) + self.x(last[1])) / 2
        out.append(
            f'<text x="{mid:.1f}" y="{mt - 24}" text-anchor="middle" {FONT} '
            f'font-size="11" font-weight="500" fill="{WINE}">'
            "Hickory Sands District (proposed)</text>"
        )
        out.append(
            f'<path d="M{ground_d}" fill="none" stroke="{INK}" '
            'stroke-width="1.4" stroke-linejoin="round"/>'
            f'<line x1="{ml}" x2="{ml + pw:.1f}" '
            f'y1="{self.y(s["rule_ft"]):.1f}" y2="{self.y(s["rule_ft"]):.1f}" '
            f'stroke="{WINE}" stroke-width=".9" stroke-dasharray="5 4"/>'
            f'<text x="{ml + pw - 2:.1f}" y="{self.y(s["rule_ft"]) - 5:.1f}" '
            f'text-anchor="end" {FONT} font-size="11" fill="{WINE}" '
            f'stroke="{PAPER}" stroke-width="3" paint-order="stroke" '
            f'stroke-linejoin="round">{fmt(s["rule_ft"])} ft</text>'
            f'<g {FONT} font-size="11" font-weight="600" fill="{INK}" '
            'letter-spacing=".06em">'
            f'<text x="{ml}" y="11">North-west end</text>'
            f'<text x="{ml + pw:.1f}" y="11" text-anchor="end">'
            "South-east end</text></g>"
        )
        for wl in s["wells"]:
            x, z0 = self.x(wl["s"]), wl["ground"]
            out.append("<g>")
            for top, bot, cls, _ in wl["log"]:
                out.append(
                    f'<line x1="{x:.1f}" x2="{x:.1f}" '
                    f'y1="{self.y(z0 - top):.1f}" '
                    f'y2="{self.y(z0 - min(bot, wl["depth"])):.1f}" '
                    f'stroke="{params.CLASS_COLOURS[cls]}" stroke-width="3"/>'
                )
            out.append(
                f'<circle cx="{x:.1f}" cy="{self.y(z0):.1f}" r="2" '
                f'fill="{INK}"/></g>'
            )
        out.append("</svg>")
        return "".join(out)

    def defs(self):
        """The drawing's patterns and its clip."""
        return (
            "<defs>"
            '<pattern id="sand" width="7" height="6" '
            'patternUnits="userSpaceOnUse">'
            f'<rect width="7" height="6" fill="{SAND}"/>'
            f'<circle cx="1.5" cy="1.5" r=".7" fill="{SAND_MARK}"/>'
            f'<circle cx="5" cy="4.5" r=".55" fill="{SAND_MARK}"/></pattern>'
            '<pattern id="water" width="7" height="6" '
            'patternUnits="userSpaceOnUse">'
            f'<rect width="7" height="6" fill="{WATER}"/>'
            f'<circle cx="1.5" cy="1.5" r=".7" fill="{WATER_MARK}"/>'
            f'<circle cx="5" cy="4.5" r=".55" fill="{WATER_MARK}"/></pattern>'
            '<pattern id="core" width="14" height="14" '
            'patternUnits="userSpaceOnUse">'
            f'<rect width="14" height="14" fill="{CORE}"/>'
            '<path d="M2 4.5h5M4.5 2v5M9 11h4M11 9v4" '
            f'stroke="{CORE_MARK}" stroke-width=".8"/></pattern>'
            '<pattern id="younger" width="18" height="9" '
            'patternUnits="userSpaceOnUse">'
            f'<rect width="18" height="9" fill="{YOUNGER}"/>'
            '<path d="M0 .5H18M0 5H18M6 .5V5M15 5V9" '
            f'stroke="{YOUNGER_MARK}" stroke-width=".5" fill="none"/>'
            "</pattern>"
            f'<clipPath id="clip"><rect x="{self.ml}" y="0" '
            f'width="{self.pw:.1f}" height="{self.y(self.s["z_base"]):.1f}"/>'
            "</clipPath></defs>"
        )
