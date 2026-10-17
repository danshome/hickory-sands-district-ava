"""README.txt and the read-me-first page from documents/ templates, with the figures taken from the build
(agreed-steps.json, written by build_agreed.py). Writes <work>/README.txt and <work>/documents/...read-me-first...html.
The page is typeset from README.txt itself (one source): its ALL-CAPS headings become headings, the package listing
becomes a table per folder (file | what it is), blank-line-separated paragraphs and "- " items become paragraphs and
lists. A check stops the build if any word of README.txt or LICENSE.txt is missing from the page.
"""

import html
import json
import os
import re

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")
DOC = os.path.join(ROOT, "documents")


def text(s):  # escaped, with web addresses as links
    return re.sub(
        r"(https?://[^\s<]+[^\s<.,;)])", r'<a href="\1">\1</a>', html.escape(s)
    )


def heading(
    s,
):  # "WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243 (details ...)" -> sentence case, note kept
    m = re.match(r"([A-Z0-9 ',.]+?)\s*(\(.*\))?$", s)
    title = re.sub(
        r"\bnotice no\.",
        "Notice No.",
        re.sub(r"\bttb\b", "TTB", m.group(1).capitalize()),
    )
    note = f" <small>{text(m.group(2))}</small>" if m.group(2) else ""
    return f"<h2>{html.escape(title)}{note}</h2>"


def is_heading(
    s,
):  # an ALL-CAPS line at column 0, with an optional "(note)": "... NOTICE NO. 243" too
    return (
        s
        and not s.startswith(" ")
        and re.match(r"[A-Z][A-Z0-9 ',.]+[A-Z0-9](\s*\(.*\))?$", s)
    )


def prose(lines):
    """paragraphs (blank-line separated) and '- ' list items (continuation lines indented past the dash)"""
    out, para, items = [], [], []

    def flush_para():
        if para:
            out.append("<p>" + text(" ".join(para)) + "</p>")
            para.clear()

    def flush_items():
        if items:
            out.append(
                "<ul>" + "".join(f"<li>{text(i)}</li>" for i in items) + "</ul>"
            )
            items.clear()

    for s in lines:
        t = s.strip()
        if not t:
            flush_para()
            flush_items()
        elif t.startswith("- "):
            flush_para()
            items.append(t[2:])
        elif items and len(s) - len(s.lstrip()) > 3:
            items[-1] += " " + t
        else:
            flush_items()
            para.append(t)
    flush_para()
    flush_items()
    return "".join(out)


def file_names(names):
    """The names for a table cell, one per line; a long one breaks after - _ /.

    Args:
        names: the file names, as README.txt lists them.

    Returns:
        HTML: the names escaped, separated by <br>, with a <wbr> after each
        -, _ and / so a long name can break there.
    """
    return "<br>".join(
        re.sub(r"([-_/])", r"\1<wbr>", html.escape(n)) for n in names
    )


def package(lines):
    """folder lines at column 0; under each, 'name   description' rows (or a name alone with its description indented
    below it, or several names sharing one), description continuations indented further, or plain prose
    """
    out, folder, rows, names, desc, para = [], None, [], [], [], []

    def end_row():
        if names:
            rows.append((names[:], " ".join(desc)))
            names.clear()
            desc.clear()

    def end_folder():
        end_row()
        if folder:
            name, note = folder
            small = f" <small>{text(note)}</small>" if note else ""
            out.append(
                f'<h3><span class="path">{html.escape(name)}</span>{small}</h3>'
            )
            if rows:
                out.append(
                    '<table class="files">'
                    + "".join(
                        f'<tr><td class="f">{file_names(ns)}</td>'
                        f"<td>{text(d)}</td></tr>"
                        for ns, d in rows
                    )
                    + "</table>"
                )
            if para:
                out.append("<p>" + text(" ".join(para)) + "</p>")
        rows.clear()
        para.clear()

    for s in lines:
        t = s.strip()
        if not t:
            continue
        indent = len(s) - len(s.lstrip())
        if indent == 0:
            end_folder()
            m = re.match(r"(\S+/)\s*(.*)", t)
            folder = (m.group(1), m.group(2))
            continue
        if indent > 3 and names:
            desc.append(t)
            continue
        m = re.match(r"(.+?\S)\s{2,}(\S.*)", t)
        if m and not para:
            end_row()
            names.append(m.group(1))
            desc.append(m.group(2))
        elif re.fullmatch(r"\S+", t) and not para:
            if desc:
                end_row()
            names.append(t)
        else:
            para.append(t)
    end_folder()
    return "".join(out)


def words(
    s,
):  # the README's list dashes become list bullets, so a lone "-" is not a word
    s = re.sub(
        r"<[^>]+>", " ", s.replace("<wbr>", "")
    )  # <wbr> is only a place a long name may break
    return [
        w
        for w in re.findall(r"[\w.'/:()-]+", html.unescape(s).lower())
        if w != "-"
    ]


def main():
    with open(os.path.join(HERE, "agreed-steps.json")) as f:
        built = json.load(f)
    fill = {
        "AREA_SQMI": f"{built['sqmi']:.2f}",
        "STEPS": str(len(built["steps"])),
    }
    with open(os.path.join(DOC, "README.template.txt"), encoding="utf-8") as f:
        readme = f.read()
    for k, v in fill.items():
        readme = readme.replace("{" + k + "}", v)
    unfilled = re.findall(r"\{[A-Z_]+\}", readme)
    assert not unfilled, (
        f"unfilled placeholder in README.template.txt: {unfilled}"
    )
    with open(os.path.join(HERE, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme)
    with open(os.path.join(ROOT, "LICENSE.txt"), encoding="utf-8") as f:
        lic = f.read()

    page_readme = readme.replace(
        "(see LICENSE.txt)", "(full text at the end of this page)"
    )  # the page has no LICENSE.txt beside it
    lines = page_readme.splitlines()
    title, meta = lines[0], lines[1:3]
    sections, cur = [], None
    for s in lines[3:]:
        if is_heading(s):
            cur = [s, []]
            sections.append(cur)
        elif cur:
            cur[1].append(s)
    body = "".join(
        heading(h)
        + (package(b) if h.startswith("WHAT IS IN THIS PACKAGE") else prose(b))
        for h, b in sections
    )
    lic_lines = lic.splitlines()
    license_html = (
        "<h2>"
        + html.escape(lic_lines[0])
        + "</h2>"
        + prose(["   " + s if s else s for s in lic_lines[1:]])
    )
    readme_html = (
        f"<h1>{html.escape(title)}</h1>"
        '<p class="meta">' + "<br>".join(text(m) for m in meta) + "</p>"
    )

    want = words(html.escape(page_readme)) + words(html.escape(lic))
    got = words(readme_html + "<!--intro-->" + body + license_html)
    assert got == want, next(
        f"read-me page differs from README.txt/LICENSE.txt at word {i}: "
        f"{got[i : i + 8]} vs {want[i : i + 8]}"
        for i in range(max(len(got), len(want)))
        if got[i : i + 1] != want[i : i + 1]
    )

    with open(
        os.path.join(DOC, "read-me-first.template.html"), encoding="utf-8"
    ) as f:
        page = f.read()
    page = (
        page.replace("{HEADER}", readme_html)
        .replace("{README}", body)
        .replace("{LICENSE}", license_html)
    )
    os.makedirs(os.path.join(HERE, "documents"), exist_ok=True)
    with open(
        os.path.join(
            HERE,
            "documents",
            "Hickory-Sands-District-read-me-first-2026-10-15.html",
        ),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(page)
    print(
        f"README.txt and read-me-first page: AVA {fill['AREA_SQMI']} sq mi, "
        f"{fill['STEPS']} steps"
    )


if __name__ == "__main__":
    main()
