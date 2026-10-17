"""Ink classes for scanned USGS topographic quadrangles (1:24,000 historical scans, five-colour printing: black,
blue, brown, red, green woodland tint). Calibrated Oct. 2026 on 13 Texas sheets (1955-1970); see
references/ink-colors.md for the samples and how to recalibrate on a new set.

The hard cases are ink printed OVER the green woodland tint: there blue, brown and black all read as dark greens.
They separate (mostly) by blue/red ratio: blue over tint keeps b >= ~0.68 r; brown and black over tint fall to ~0.55.
Even so, blue-over-tint and black-over-tint overlap a little; corridors and priors keep a trace on its own feature.
"""

import numpy as np
from scipy import ndimage


def classes_absolute(a):
    """first calibration, fixed colour thresholds (kept for comparison; see classes() for the one in use)"""
    r, g, b = (a[i].astype(np.int16) for i in range(3))
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    blue_paper = (b > r + 20) & (g > r + 20) & (b >= g - 60)
    blue_tint = (r < 120) & (g > 160) & (g > r + 45) & (b < g) & (b >= 0.68 * r)
    red = (r > 170) & (g < 135) & (b < 135) & (r - b > 60)
    brown = (r - b > 32) & (b < 190) & (r >= g - 45) & ~red
    index_brown = (
        brown & (r < 190) & (mx < 205)
    )  # heavy (index) contour ink; light contours drop out
    dark_tint = (
        (r < 130) & (g > r + 35) & (g < 185) & (b < 0.66 * r)
    )  # brown or black over the tint
    black = (mx < 110) & (r - b <= 40)
    gray = (mx < 190) & (mx - mn < 35)  # dashed road casings scan light gray
    road_tint = (
        (r < 140) & (g > r + 35) & (g < 215) & (b < 0.72 * r)
    )  # road casings over the tint
    return {
        "creek": blue_paper | blue_tint,
        "contour": index_brown | dark_tint,
        "road": black | gray | red | dark_tint | road_tint,
    }


KINDS = ("creek", "contour", "road")


def background(a, size=7):
    """paper or tint under the ink: per-channel grey closing removes dark marks narrower than `size` pixels (~14 m)"""
    return np.stack(
        [ndimage.grey_closing(a[i], size=(size, size)) for i in range(3)]
    ).astype(np.float32)


def classes(a, size=7, px_m=2.03):
    """ink classes from each pixel's ratio to its local background (paper or woodland tint), so the tint's shade --
    which varies between sheets and within one -- does not matter:
      black/gray (roads, casings, lettering): all three channels darkened alike (warmth near 0)
      blue (creeks): red darkened more than blue (warmth below -0.22)
      brown (contours): blue darkened more than red (warmth above +0.22)
      red (highway fill): green and blue darkened, red not
    """
    rgb = a[:3].astype(np.float32)
    bg = np.maximum(background(a[:3], size), 1.0)
    k = rgb / bg
    kr, kg, kb = k[0], k[1], k[2]
    kmean = (kr + kg + kb) / 3
    kmax = np.maximum(np.maximum(kr, kg), kb)
    kmin = np.minimum(np.minimum(kr, kg), kb)
    # printed at all: darker than the background, and green darkened too (woodland tint seen against paper keeps
    # green at ~0.97 while every ink takes green below ~0.8)
    dark = (kmean < 0.82) & (kg < 0.85)
    # warmth: red-vs-blue darkening scaled by how dark the pixel is, so faint and heavy ink of one colour agree
    # (measured: gray dashes +0.04, black road +0.04, brown contour over tint +0.40, blue creek over tint -0.36)
    w = (kr - kb) / np.maximum(1 - kmean, 0.05)
    red = (kr > 0.7) & (kg < 0.62) & (kb < 0.62) & (kr - kg > 0.3)
    # brown darkens blue more than green (contours over tint: kg - kb 0.11-0.18); black darkens all three alike
    # (dashes over tint: kg - kb 0.00-0.06) even when faint ink makes the warmth read high
    # ... but only where the background is the green tint; over paper the plain warmth rules are right (Dan: dashed
    # roads on light ground were almost perfect, the trouble is only on green)
    tinted = (bg[1] > bg[0] + 25) & (bg[1] > bg[2] + 40)
    brown = dark & (w >= 0.22) & ~red & (~tinted | (kg - kb >= 0.06))
    # dotted-creek candidates keep the Oct. 15 brown rule (warmth alone, no tint gate). With the tint gate the
    # anti-aliased edge pixels of contours over the woodland tint fail kg - kb >= 0.06, stop being brown and
    # became "dotlike"; chain_dots took them for creek dots and steps 9, 30 and 90 left their blue line for the
    # neighbouring contour for 10-60 m (Oct. 16, 2026; last night's creek lines are reproduced exactly with this)
    brown_dots = dark & (w >= 0.22) & ~red
    blue = dark & (w <= -0.22) & (kg > kr) & ~red
    black = dark & ~red & ~brown & ((np.abs(w) < 0.22) | (tinted & (w > -0.22)))
    # lettering and other black ink printed over a creek or contour hides it: black (grown 1 px, to take the letters'
    # anti-aliased edges) is never creek or contour ink, so a trace bridges straight across a label
    black_grown = ndimage.binary_dilation(
        black & (kmean < 0.5), iterations=1
    )  # heavy black only: lettering
    # creek ink over the woodland tint often prints as a dark teal that reads near-neutral (warmth ~ -0.1): it keeps
    # green noticeably lighter than red, which black and brown over the tint do not
    teal = dark & (w < 0.1) & (kg - kr > 0.1) & ~red
    # lettering by SHAPE, whatever its colour (contour labels are brown like the contour, road names black like the
    # road): a connected piece of ink of modest extent (8-40 m) carrying much more ink than a line of that extent
    # would (area / extent >= 4.5 m; a 2-3 m line gives 2-3, a dash ~3, a digit or letter 5-12)
    text_loose, text_a, text_b = lettering(
        dark & ~red & ~blue & ~teal, px_m
    )  # labels are brown or black; a thick creek stroke is not a letter
    # the eroded-core pass (text_b) also bites pieces out of heavy contours, so contours and creeks use only the
    # whole-shape pass; roads (where black labels like 'GAP' sit against the road) use both
    ta = ndimage.binary_dilation(text_loose, iterations=1)
    tb = ndimage.binary_dilation(text_a | text_b, iterations=1)
    # digits ON the contour by their HOLES (contours only): an index contour and its label print at the same weight,
    # so no shape or erosion test separates them, but a 0, 8, 6 or 9 encloses a hole of 30-450 m2 and a contour never
    # does (Oct. 16, 2026, "1800" along step 3's contour: the trace looped through the 8 and both 0s). Black text
    # ("High Point") and its halo are left out first: its o's and P's read brown at the edges and made holes too, and
    # on a steep slope the zone around them sent step 59 onto the next contour
    label, digits = digit_holes(brown & ~black_grown, px_m)
    not_feature = black_grown | ta
    # over some tints a black road dash prints olive, the same colour as a brown contour: a brown piece that is
    # DASH-SHAPED (8-35 m long, elongated, isolated) is road ink too; contours are continuous lines
    road_dash = dashes(
        brown & tinted, px_m
    )  # over paper a brown dash is a contour fragment
    # a highway's black casings print blended with the red fill beside them and read WARM (brown) at 2 m/px: measured
    # Oct. 16, 2026 on steps 21 and 28, 97% of the pixels 1 m outside the fill classed brown, <1% black. Brown ink
    # touching the fill (within 2 px) is casing ink; the fill itself is not road ink (the centre is between the casings)
    casing = brown & ndimage.binary_dilation(red, iterations=2) & ~red
    return {
        "creek": (blue | teal) & ~not_feature,
        "contour": brown & ~not_feature & ~digits,
        "label": label,
        # red highway fill is NOT road ink (Dan, Oct. 16, 2026): a highway is centred between its two black casings
        # like any double-line road; with the fill counted, casing + fill read as a "pair" and biased the centre 3 m
        "road": ((black & ~teal) | road_dash | casing)
        & ~tb,  # a dark creek over the tint reads near-neutral: not road ink
        "dotlike": dark
        & ~brown_dots
        & ~red
        & ~ta,  # any small dot a dotted creek might be printed with
        # faint neutral marks (the lighter casing of an unimproved road prints at ~0.86 of the paper): too noisy
        # to be road ink in general, used only where a casing is expected (centerline.edge_offsets)
        "road_faint": (kmean < 0.93) & (kmax - kmin < 0.08) & ~dark & ~brown,
        "text": text_loose | text_b | digits,
        "black": black,
        "red": red,
        "brown": brown,
        "blue": blue,
    }


def lettering(
    ink,
    px_m=2.03,
    min_extent_m=8.0,
    max_extent_m=40.0,
    min_fill_m=5.5,
    min_px=20,
):
    """connected pieces of ink that are letters or digits by shape, found two ways (returned separately):
    (a) on the ink as is: extent between min and max m, and area / extent (mean thickness along the longest side)
        at least min_fill_m -- lines, dashes and dots are thinner than that;
    (b) on the ink with 2-pixel lines eroded away (letter strokes print heavier than contour and road lines), so a
        label that touches a line is found on its own: extent 5-40 m there, then grown back 2 px within the ink.
    """

    def pick(mask, lo, hi, fill, compact=False, px=0):
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        if n == 0:
            return np.zeros_like(mask)
        ids = np.arange(1, n + 1)
        npx = ndimage.sum(np.ones(lab.shape), lab, ids)
        area = npx * px_m * px_m
        objs = ndimage.find_objects(lab)
        h = np.array([o[0].stop - o[0].start for o in objs]) * px_m
        w = np.array([o[1].stop - o[1].start for o in objs]) * px_m
        ext = np.maximum(h, w)
        keep = (
            (ext >= lo)
            & (ext <= hi)
            & (area / np.maximum(ext, 1e-6) >= fill)
            & (npx >= px)
        )
        if compact:  # letters and digits are not elongated; a dash or a line piece is, whatever its bearing (a
            # diagonal dash has a square box, so elongation is measured on the pixels' principal axes, not the box)
            for i in np.flatnonzero(keep):
                ys, xs = np.nonzero(lab[objs[i]] == ids[i])
                if len(ys) < 4:
                    keep[i] = False
                    continue
                pix = np.column_stack([ys, xs]).astype(float)
                pix -= pix.mean(0)
                sv = np.linalg.svd(pix, compute_uv=False)
                keep[i] = (sv[0] / max(sv[1], 1e-6)) <= (
                    compact if compact is not True else 2.5
                )
        return np.isin(lab, ids[keep]) if keep.any() else np.zeros_like(mask)

    # compact: a heavy road dash over the tint is not a letter; min_px / fill 5.5 (Oct. 16, 2026): with fill 4.5 the pass
    # took 9-15 px dash bits and, at point 94, a 43 px blob of two dash rows joined by a fence line (fill 5.1) -- the
    # road lost its casings at the junction and the trace rode the fence; measured letters on these sheets fill 6-12
    # pass (a) at two strengths. LOOSE (fill 4.5, any size; the Oct. 15 setting) is what contours and creeks use: it
    # catches the digits of a contour label printed on the line and the trace bridges them straight (Dan, Oct. 16:
    # "you had it working by passing through the middles of the numbers"). STRICT (fill 5.5, >= 20 px) is for roads:
    # the loose pass took 9-15 px dash bits and, at point 94, a 43 px blob of two dash rows joined by a fence line
    # (fill 5.1), so the road lost its casings at the junction and the trace rode the fence.
    a_loose = pick(ink, min_extent_m, max_extent_m, 4.5, compact=True)
    a = pick(
        ink, min_extent_m, max_extent_m, min_fill_m, compact=True, px=min_px
    )
    core = ndimage.binary_erosion(ink, structure=np.ones((3, 3)))
    b = pick(core, 5.0, 30.0, 2.0, compact=True)
    b = ndimage.binary_dilation(b, iterations=2) & ink
    return a_loose, a, b


def digit_holes(
    ink,
    px_m=2.03,
    min_m2=30.0,
    max_m2=450.0,
    max_extent_m=26.0,
    pair_m=40.0,
    label_beyond_m=32.0,
    label_half_m=6.0,
    grow_px=4,
    label_px=4,
):
    """ink around the small enclosed holes of printed digits (0, 8, 6, 9): the holes of `ink` (filled minus ink) with
    an area of min_m2-max_m2 (a 0 of a 1:24,000 contour label: ~320 m2, 22 m; an 8's two holes 50-100 m2) and an extent
    up to max_extent_m, grown grow_px pixels -- that is the digit's stroke
    """
    # NO morphological closing first: on a steep slope it welds contours 2-3 px apart into one mass and the pockets
    # between them become "holes" (step 59 jumped onto the next contour, Oct. 16, 2026); a 0 whose ring is broken
    # at this scan is simply not caught
    holes = ndimage.binary_fill_holes(ink) & ~ink
    lab, n = ndimage.label(holes)
    if n == 0:
        return np.zeros_like(ink), np.zeros_like(ink)
    ids = np.arange(1, n + 1)
    area = ndimage.sum(np.ones(lab.shape), lab, ids) * px_m * px_m
    objs = ndimage.find_objects(lab)
    h = np.array([o[0].stop - o[0].start for o in objs])
    w = np.array([o[1].stop - o[1].start for o in objs])
    ext = np.maximum(h, w) * px_m
    boxfill = area / np.maximum(
        h * w * px_m * px_m, 1e-6
    )  # a digit's hole is round-ish: fills its box
    keep = (
        (area >= min_m2)
        & (area <= max_m2)
        & (ext <= max_extent_m)
        & (boxfill >= 0.45)
        & (np.maximum(h, w) <= 3 * np.minimum(h, w))
    )
    if not keep.any():
        return np.zeros_like(ink), np.zeros_like(ink)
    # a label's digits come in a group (every index-contour label here, 1500-2000, has at least two of 0 8 6 9), a
    # tiny closed contour (a knob or sink, 20 m across) is alone: a hole counts only with another one within pair_m
    # (step 59 at "High Point", Oct. 16, 2026: a lone 25 x 15 m closed contour was taken for a digit and the zone
    # around it cut the followed contour, which then jumped to its neighbour)
    cy = np.array([(o[0].start + o[0].stop) / 2 for o in objs]) * px_m
    cx = np.array([(o[1].start + o[1].stop) / 2 for o in objs]) * px_m
    kid = np.flatnonzero(keep)
    for i in kid:
        d = np.hypot(cx[kid] - cx[i], cy[kid] - cy[i])
        d[kid == i] = np.inf
        if d.min() > pair_m:
            keep[i] = False
    if not keep.any():
        return np.zeros_like(ink), np.zeros_like(ink)
    # the whole LABEL, not just the digits with holes: a 1 or 7 has no hole and a 0 whose ring breaks at this scan
    # has none either, and with them left in the path spiked to the 1 and dipped under the last 0 (step 3's "1800",
    # Oct. 16, 2026). Each group of holes (within pair_m of each other) is one label: a strip along the line through
    # the holes, label_beyond_m past the outermost hole each way and label_half_m either side of the line
    kid = list(np.flatnonzero(keep))
    group = {i: i for i in kid}

    def find(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i in kid:
        for j in kid:
            if j > i and np.hypot(cx[i] - cx[j], cy[i] - cy[j]) <= pair_m:
                group[find(j)] = find(i)
    out = np.zeros(ink.shape, bool)
    yy, xx = np.mgrid[0 : ink.shape[0], 0 : ink.shape[1]]
    yy = yy * px_m
    xx = xx * px_m
    for g in {find(i) for i in kid}:
        mem = [i for i in kid if find(i) == g]
        c = np.array([[cx[i], cy[i]] for i in mem])
        ctr = c.mean(0)
        if len(mem) >= 2:
            _u, _sv, vt = np.linalg.svd(c - ctr, full_matrices=False)
            ax = vt[0]
        else:
            ax = np.array([1.0, 0.0])
        nrm = np.array([-ax[1], ax[0]])
        along = (c - ctr) @ ax
        half_ext = max(ext[i] for i in mem) / 2
        half_u = np.abs(along).max() + half_ext + label_beyond_m
        half_v = half_ext + label_half_m
        u_off = (xx - ctr[0]) * ax[0] + (yy - ctr[1]) * ax[1]
        v_off = (xx - ctr[0]) * nrm[0] + (yy - ctr[1]) * nrm[1]
        out |= (np.abs(u_off) <= half_u) & (np.abs(v_off) <= half_v)
    digits = (
        ndimage.binary_dilation(np.isin(lab, ids[keep]), iterations=grow_px)
        & ink
    )  # the digits' strokes
    # What is REMOVED from the contour ink is the digits grown label_px (the strokes between them): the version Dan
    # called "way better". The strip `out` is returned for information only. Two strip-based variants were dead ends
    # (Oct. 16, 2026): (1) strip ink removed and the path on the prior -- a straight bridge across "1700" on step 65
    # landed on the neighbouring contour; (2) prior-guided strip with the contour's own ink as tie-breaker -- at the
    # "1885" spot elevation on step 59 (steep slope, contours 6 m apart) the line still left on the wrong contour
    # for 300 m. The prior is not accurate enough to pick a contour on a steep slope; only the ink is.
    zone = ndimage.binary_dilation(digits, iterations=label_px) & ink
    return out, zone


def dashes(ink, px_m=2.03, min_m=8.0, max_m=35.0, min_elong=3.0):
    """connected pieces of ink shaped like road dashes: min_m-max_m long, elongated (principal axes ratio >= min_elong)"""
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros_like(ink)
    ids = np.arange(1, n + 1)
    objs = ndimage.find_objects(lab)
    ext = (
        np.array(
            [max(o[0].stop - o[0].start, o[1].stop - o[1].start) for o in objs]
        )
        * px_m
    )
    keep = (ext >= min_m) & (ext <= max_m * 1.5)
    for i in np.flatnonzero(keep):
        ys, xs = np.nonzero(lab[objs[i]] == ids[i])
        if len(ys) < 4:
            keep[i] = False
            continue
        pix = np.column_stack([ys, xs]).astype(float)
        pix -= pix.mean(0)
        sv = np.linalg.svd(pix, compute_uv=False)
        length = (
            2 * np.sqrt(3) * sv[0] / np.sqrt(len(pix)) * px_m
        )  # length of a uniform bar with this spread
        keep[i] = (sv[0] / max(sv[1], 1e-6) >= min_elong) and (length <= max_m)
    return np.isin(lab, ids[keep]) if keep.any() else np.zeros_like(ink)
