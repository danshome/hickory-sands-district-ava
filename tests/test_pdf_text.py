"""src/documents/pdf_text.py: paragraphs rebuilt from poppler's -bbox-layout positions, and the line-end hyphen rules.
Small synthetic pages (a line is (xMin, xMax, y, "its words"); points, as poppler gives them), and one run of the real
pdftotext on TTB's Notice No. 243 when poppler is installed."""
import html, json, pathlib, re, shutil
import pytest
from src.documents import pdf_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICE = ROOT / "resources" / "ttb" / "TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf"
TTB_STEPS = ROOT / "resources" / "boundary" / "description" / "ttb-notice-243-steps.json"


def xhtml(*pages):
    """poppler's -bbox-layout XHTML: pages of blocks of lines"""
    out = ["<doc>"]
    for blocks in pages:
        out.append('  <page width="612.000000" height="792.000000">')
        for lines in blocks:
            bx0, bx1 = min(ln[0] for ln in lines), max(ln[1] for ln in lines)
            by0, by1 = min(ln[2] for ln in lines), max(ln[2] for ln in lines) + 10
            out.append(f'    <flow>\n      <block xMin="{bx0:f}" yMin="{by0:f}" xMax="{bx1:f}" yMax="{by1:f}">')
            for x0, x1, y, words in lines:
                out.append(f'        <line xMin="{x0:f}" yMin="{y:f}" xMax="{x1:f}" yMax="{y + 10:f}">')
                out += [f'          <word xMin="{x0:f}" yMin="{y:f}" xMax="{x1:f}" yMax="{y + 10:f}">{html.escape(w)}</word>'
                        for w in words.split()]
                out.append("        </line>")
            out.append("      </block>\n    </flow>")
        out.append("  </page>")
    return "\n".join(out + ["</doc>"])


def text(*pages):
    paras, printed = pdf_text.paragraphs(xhtml(*pages))
    return pdf_text.text_of(paras, printed, "test.txt")


# ---- paragraphs: a left column x 50-300 and a right column x 320-570; a line ending at x >= 275 is full

def test_an_indented_line_starts_a_paragraph():
    block = [(60, 300, 100, "The boundary of the viticultural"), (50, 300, 110, "area is as described as follows. It"),
             (50, 180, 120, "ends here."), (60, 300, 130, "A second paragraph starts with an"), (50, 120, 140, "indent.")]
    assert text([block]) == ["The boundary of the viticultural area is as described as follows. It ends here.",
                             "A second paragraph starts with an indent."]


@pytest.mark.parametrize("x0, paragraphs", [(53.0, 1), (53.5, 2)])
def test_indent_is_more_than_3_points(x0, paragraphs):
    block = [(50, 300, 100, "One line runs the full width of the"), (x0, 200, 110, "column and this one follows.")]
    assert len(text([block])) == paragraphs


def test_a_flush_line_in_the_same_block_carries_on_even_after_a_sentence():
    block = [(60, 300, 100, "Proceed east. Then proceed"), (50, 200, 110, "Proceed north.")]
    assert text([block]) == ["Proceed east. Then proceed Proceed north."]


def test_a_flush_block_carries_on_a_paragraph_cut_by_a_column_break():
    left = [(60, 300, 100, "Proceed east along the road for"), (50, 299, 110, "2.9 miles to its intersection with")]
    right = [(320, 570, 100, "Honey Creek; then"), (330, 570, 110, "(2) Proceed north to the end.")]
    assert text([left, right]) == ["Proceed east along the road for 2.9 miles to its intersection with Honey Creek; then",
                                   "(2) Proceed north to the end."]


def test_a_flush_block_starts_a_paragraph_when_the_last_line_was_short():
    left = [(60, 300, 100, "Proceed east along the road for"), (50, 274, 110, "2.9 miles to its intersection with")]
    right = [(320, 570, 100, "Honey Creek; then")]
    assert text([left, right]) == ["Proceed east along the road for 2.9 miles to its intersection with", "Honey Creek; then"]


@pytest.mark.parametrize("end", ["miles.", "follows:", "it;", "true?", "now!", "\u201cQuarry.\u201d", "(b)."])
def test_a_flush_block_starts_a_paragraph_after_a_sentence_or_clause(end):
    left = [(60, 300, 100, "Proceed east along the road for"), (50, 300, 110, "2.9 " + end)]
    right = [(320, 570, 100, "Next text.")]
    assert text([left, right]) == ["Proceed east along the road for 2.9 " + end, "Next text."]


HEAD1 = [(124, 487, 34, "Federal Register / Vol. 91, No. 156")]    # yMax 44 < 50: the running head
SLUG = [(45, 300, 760, "VerDate Sep<11>2014 Jkt 268001")]          # yMin 760 > 750: GPO's slug along the bottom
NOTE = [(10, 20, 300, "margin note")]                              # xMax 20 < 30: the note in the left margin
HEAD2 = [(45, 75, 34, "52588")]


def test_page_furniture_waits_for_a_paragraph_carried_over_the_page_break():
    page1 = [HEAD1, [(60, 300, 100, "Proceed east along the road for"), (50, 300, 110, "2.9 miles to its intersection with")],
             SLUG, NOTE]
    page2 = [HEAD2, [(50, 300, 100, "Honey Creek; then"), (60, 300, 110, "(2) Proceed north.")]]
    assert text(page1, page2) == ["Federal Register / Vol. 91, No. 156",
                                  "Proceed east along the road for 2.9 miles to its intersection with Honey Creek; then",
                                  "margin note", "VerDate Sep<11>2014 Jkt 268001", "52588", "(2) Proceed north."]


def test_page_furniture_goes_at_the_page_break_between_paragraphs():
    page1 = [HEAD1, [(60, 300, 100, "Proceed east along the road for"), (50, 300, 110, "2.9 miles to the creek.")], SLUG, NOTE]
    page2 = [HEAD2, [(50, 300, 100, "Honey Creek runs north.")]]
    assert text(page1, page2) == ["Federal Register / Vol. 91, No. 156", "Proceed east along the road for 2.9 miles to the creek.",
                                  "margin note", "VerDate Sep<11>2014 Jkt 268001", "52588", "Honey Creek runs north."]


@pytest.mark.parametrize("block, paragraphs", [                    # a block's yMax is its last line's y + 10 here
    ([(60, 300, 39.9, "head")], ["head", "Main text runs on"]),       # yMax < 50: the running head, before the page's text
    ([(60, 300, 40, "body")], ["Main text runs on body"]),
    ([(60, 300, 750.1, "slug")], ["Main text runs on", "slug"]),      # yMin > 750: the slug, after it
    ([(60, 300, 750, "body")], ["Main text runs on body"]),
    ([(5, 29.9, 300, "note")], ["Main text runs on", "note"]),        # xMax < 30: the margin note, after it
    ([(5, 30, 300, "body")], ["Main text runs on body"])])
def test_page_furniture_limits(block, paragraphs):
    assert text([[(60, 300, 400, "Main text runs on")], block]) == paragraphs


def test_gpo_stars_one_per_line_become_one_line():
    stars = [(100, 105, 200, "*"), (140, 145, 200, "*"), (180, 185, 200, "*"), (220, 225, 200, "*"), (260, 265, 200, "*")]
    after = [(60, 300, 220, "Next paragraph starts with an"), (50, 120, 230, "indent.")]
    assert text([[(60, 300, 100, "The end of the amendment.")], stars, after]) == [
        "The end of the amendment.", "* * * * *", "Next paragraph starts with an indent."]


def test_space_before_a_colon_is_dropped():
    block = [(60, 300, 100, "ACTION : Notice of proposed rulemaking at 10:30 a.m.:"), (50, 200, 110, "SUMMARY :")]
    assert text([block]) == ["ACTION: Notice of proposed rulemaking at 10:30 a.m.: SUMMARY:"]


def test_a_hyphenated_form_printed_elsewhere_keeps_its_hyphen():
    broken = [(60, 300, 120, "Proceed along the light-"), (50, 200, 130, "duty road.")]
    assert text([[(60, 300, 100, "An unnamed light-duty road.")], broken]) == ["An unnamed light-duty road.",
                                                                                "Proceed along the light-duty road."]
    assert text([broken]) == ["Proceed along the lightduty road."]


def test_every_printed_word_must_reach_the_text():
    with pytest.raises(SystemExit, match=r"out.txt: 3 printed words but 2 in the text"):
        pdf_text.text_of([[["a", "b"]]], ["a", "b", "c"], "out.txt")


def test_main_needs_pdftotext(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda exe: None)
    with pytest.raises(SystemExit, match="pdftotext"):
        pdf_text.main(str(NOTICE), str(tmp_path / "out.txt"))


# ---- a word broken at a line end

@pytest.mark.parametrize("lines, flat, joined", [
    ([["the", "1,668-"], ["foot", "elevation"]], "", "the 1,668-foot elevation"),                # a digit before it
    ([["the", "Mason-"], ["McCulloch", "line"]], "", "the Mason-McCulloch line"),                # a capitalised word after
    ([["West", "Farm-"], ["to-Market", "Road"]], "", "West Farm-to-Market Road"),               # another hyphen after
    ([["see", "https://www.ttb.gov/regulated-commodities/beverage-"], ["alcohol"]], "",         # a URL
     "see https://www.ttb.gov/regulated-commodities/beverage-alcohol"),
    ([["a", "light-"], ["duty", "road"]], "an unnamed light-duty road", "a light-duty road"),    # printed elsewhere
    ([["a", "light-"], ["duty,", "road"]], "an unnamed light-duty road", "a light-duty, road"),
    ([["a", "light-"], ["duty", "road"]], "", "a lightduty road"),                               # otherwise joined
    ([["the", "bound-"], ["ary", "of"]], "", "the boundary of"),
    ([["Notice", "243\u2014"], ["Hickory"]], "", "Notice 243\u2014Hickory"),                    # a dash at the end: no space
    ([["1,705\u2013"], ["foot"]], "", "1,705\u2013foot"),
    ([["https://www.regulations.gov/"], ["docket"]], "", "https://www.regulations.gov/docket"),  # a URL's slash
    ([["see", "-"], ["below"]], "", "see - below"),                                             # a hyphen alone is a word
    ([["one", "two"], ["three"]], "", "one two three")])
def test_line_end_hyphens(lines, flat, joined):
    assert pdf_text.join(lines, flat) == joined


# ---- the real thing: TTB's Notice No. 243, as the build makes its compare-text file

GPO = lambda s: s.replace("\u2018\u2018", "\u201c").replace("\u2019\u2019", "\u201d").replace("\u2019", "'").replace("\u2013", "-")


@pytest.mark.build
@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler's pdftotext is not installed (brew install poppler)")
def test_notice_243(tmp_path, capsys):
    out = tmp_path / "compare-text.txt"
    pdf_text.main(str(NOTICE), str(out))
    assert capsys.readouterr().out == "compare-text.txt: 471 paragraphs from 11534 printed words\n"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 471
    start = next(i for i, s in enumerate(lines) if s.startswith("(c) Boundary.") and "Hickory Sands District" in s)
    steps = [(int(m.group(1)), s) for s in lines[start + 1:] if (m := re.match(r"\((\d+)\) ", s))][:96]
    assert [n for n, _ in steps] == list(range(1, 97))
    ttb = json.loads(TTB_STEPS.read_text(encoding="utf-8"))
    for n, s in steps:   # each step one whole line: the printed text, GPO's quotes and dashes aside, is TTB's step
        assert GPO(s) == " ".join(ttb[str(n)].split()), f"step ({n})"
