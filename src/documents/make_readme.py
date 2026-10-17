"""README.txt and the read-me-first page from documents/ templates, with the figures taken from the build
(agreed-steps.json, written by build_agreed.py). Writes <work>/README.txt and <work>/documents/...read-me-first...html.
The page is typeset from README.txt itself (one source): its ALL-CAPS headings become headings, the package listing
becomes a table per folder (file | what it is), blank-line-separated paragraphs and "- " items become paragraphs and
lists. A check stops the build if any word of README.txt or LICENSE.txt is missing from the page."""
import html, json, os, re
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")
DOC = os.path.join(ROOT, "documents")
built = json.load(open(os.path.join(HERE, "agreed-steps.json")))
fill = {"AREA_SQMI": "%.2f" % built["sqmi"], "STEPS": str(len(built["steps"]))}
readme = open(os.path.join(DOC, "README.template.txt"), encoding="utf-8").read()
for k, v in fill.items(): readme = readme.replace("{" + k + "}", v)
assert not re.search(r"\{[A-Z_]+\}", readme), "unfilled placeholder in README.template.txt: %s" % re.findall(r"\{[A-Z_]+\}", readme)
open(os.path.join(HERE, "README.txt"), "w", encoding="utf-8").write(readme)
lic = open(os.path.join(ROOT, "LICENSE.txt"), encoding="utf-8").read()

def text(s):   # escaped, with web addresses as links
    return re.sub(r"(https?://[^\s<]+[^\s<.,;)])", r'<a href="\1">\1</a>', html.escape(s))

def heading(s):   # "WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243 (details ...)" -> sentence case, note kept
    m = re.match(r"([A-Z0-9 ',.]+?)\s*(\(.*\))?$", s)
    title = re.sub(r"\bnotice no\.", "Notice No.", re.sub(r"\bttb\b", "TTB", m.group(1).capitalize()))
    return f"<h2>{html.escape(title)}{' <small>' + text(m.group(2)) + '</small>' if m.group(2) else ''}</h2>"

def prose(lines):
    """paragraphs (blank-line separated) and '- ' list items (continuation lines indented past the dash)"""
    out, para, items = [], [], []
    def flush_para():
        if para: out.append("<p>" + text(" ".join(para)) + "</p>"); para.clear()
    def flush_items():
        if items: out.append("<ul>" + "".join(f"<li>{text(i)}</li>" for i in items) + "</ul>"); items.clear()
    for s in lines:
        t = s.strip()
        if not t:
            flush_para(); flush_items()
        elif t.startswith("- "):
            flush_para(); items.append(t[2:])
        elif items and len(s) - len(s.lstrip()) > 3:
            items[-1] += " " + t
        else:
            flush_items(); para.append(t)
    flush_para(); flush_items()
    return "".join(out)

def package(lines):
    """folder lines at column 0; under each, 'name   description' rows (or a name alone with its description indented
    below it, or several names sharing one), description continuations indented further, or plain prose"""
    out, folder, rows, names, desc, para = [], None, [], [], [], []
    def end_row():
        if names: rows.append((names[:], " ".join(desc))); names.clear(); desc.clear()
    def end_folder():
        end_row()
        if folder:
            name, note = folder
            out.append(f'<h3><span class="path">{html.escape(name)}</span>{" <small>" + text(note) + "</small>" if note else ""}</h3>')
            if rows:
                out.append('<table class="files">' + "".join(
                    f'<tr><td class="f">{"<br>".join(re.sub(r"([-_/])", r"\1<wbr>", html.escape(n)) for n in ns)}</td><td>{text(d)}</td></tr>'
                    for ns, d in rows) + "</table>")   # long file names break after - _ /
            if para:
                out.append("<p>" + text(" ".join(para)) + "</p>")
        rows.clear(); para.clear()
    for s in lines:
        t = s.strip()
        if not t:
            continue
        indent = len(s) - len(s.lstrip())
        if indent == 0:
            end_folder(); m = re.match(r"(\S+/)\s*(.*)", t); folder = (m.group(1), m.group(2)); continue
        if indent > 3 and names:
            desc.append(t); continue
        m = re.match(r"(.+?\S)\s{2,}(\S.*)", t)
        if m and not para:
            end_row(); names.append(m.group(1)); desc.append(m.group(2))
        elif re.fullmatch(r"\S+", t) and not para:
            if desc: end_row()
            names.append(t)
        else:
            para.append(t)
    end_folder()
    return "".join(out)

page_readme = readme.replace("(see LICENSE.txt)", "(full text at the end of this page)")   # the page has no LICENSE.txt beside it
lines = page_readme.splitlines()
title, meta = lines[0], lines[1:3]
sections, cur = [], None
for s in lines[3:]:
    if s and not s.startswith(" ") and re.match(r"[A-Z][A-Z0-9 ',.]+[A-Z0-9](\s*\(.*\))?$", s):   # "... NOTICE NO. 243" too
        cur = [s, []]; sections.append(cur)
    elif cur:
        cur[1].append(s)
body = "".join(heading(h) + (package(b) if h.startswith("WHAT IS IN THIS PACKAGE") else prose(b)) for h, b in sections)
lic_lines = lic.splitlines()
license_html = "<h2>" + html.escape(lic_lines[0]) + "</h2>" + prose(["   " + s if s else s for s in lic_lines[1:]])
readme_html = (f"<h1>{html.escape(title)}</h1>" + '<p class="meta">' + "<br>".join(text(m) for m in meta) + "</p>")

def words(s):   # the README's list dashes become list bullets, so a lone "-" is not a word
    s = re.sub(r"<[^>]+>", " ", s.replace("<wbr>", ""))   # <wbr> is only a place a long name may break
    return [w for w in re.findall(r"[\w.'/:()-]+", html.unescape(s).lower()) if w != "-"]
want = words(html.escape(page_readme)) + words(html.escape(lic))
got = words(readme_html + "<!--intro-->" + body + license_html)
assert got == want, next(f"read-me page differs from README.txt/LICENSE.txt at word {i}: {got[i:i+8]} vs {want[i:i+8]}"
                         for i in range(max(len(got), len(want))) if got[i:i + 1] != want[i:i + 1])

page = open(os.path.join(DOC, "read-me-first.template.html"), encoding="utf-8").read()
page = page.replace("{HEADER}", readme_html).replace("{README}", body).replace("{LICENSE}", license_html)
os.makedirs(os.path.join(HERE, "documents"), exist_ok=True)
open(os.path.join(HERE, "documents", "Hickory-Sands-District-read-me-first-2026-10-15.html"), "w", encoding="utf-8").write(page)
print("README.txt and read-me-first page: AVA %s sq mi, %s steps" % (fill["AREA_SQMI"], fill["STEPS"]))
