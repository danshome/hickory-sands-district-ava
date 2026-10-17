"""src/checks/check_step_text.py (the commit hook and build check, PR #23): TTB's 96 steps are identical to the Federal
Register's XML, and step text with a character the Federal Register does not use is refused with its fix. Run as the
hook runs it (a script, in its own process); the edge cases in a copy of the repository's layout under a temporary folder."""
import json, pathlib, re, shutil, subprocess, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "checks" / "check_step_text.py"
XML = ROOT / "resources" / "ttb" / "federal-register-2026-16670-full-text.xml"
DESC = ROOT / "resources" / "boundary" / "description"
if not (SCRIPT.exists() and XML.exists()):
    pytest.skip("src/checks/check_step_text.py and the Federal Register's XML are not on main yet (PR #23)", allow_module_level=True)


def run(script, *args):
    p = subprocess.run([sys.executable, "-I", "-B", str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout


def layout(tmp_path, ttb=None, petition=None, agreed='STEPS = ["Proceed east along the road; then"]\n'):
    """the script with its inputs where it looks for them (it finds the repository from its own path)"""
    root = tmp_path / "repo"
    for d in ("src/checks", "src/boundary", "resources/ttb", "resources/boundary/description"): (root / d).mkdir(parents=True)
    shutil.copy(SCRIPT, root / "src" / "checks" / SCRIPT.name)
    shutil.copy(XML, root / "resources" / "ttb" / XML.name)
    ttb = ttb if ttb is not None else json.loads((DESC / "ttb-notice-243-steps.json").read_text(encoding="utf-8"))
    petition = petition if petition is not None else json.loads((DESC / "petition-steps.json").read_text(encoding="utf-8"))
    (root / "resources/boundary/description/ttb-notice-243-steps.json").write_text(json.dumps(ttb), encoding="utf-8")
    (root / "resources/boundary/description/petition-steps.json").write_text(json.dumps(petition), encoding="utf-8")
    (root / "src/boundary/build_agreed.py").write_text(agreed, encoding="utf-8")
    return root / "src" / "checks" / SCRIPT.name


def test_ttb_steps_identical_to_the_federal_register():
    rc, out = run(SCRIPT)
    assert rc == 0, out
    assert "TTB's 96 steps identical to the Federal Register" in out


def test_a_changed_ttb_step_is_named(tmp_path):
    ttb = json.loads((DESC / "ttb-notice-243-steps.json").read_text(encoding="utf-8"))
    ttb["5"] = ttb["5"].replace("Proceed", "Go", 1)
    rc, out = run(layout(tmp_path, ttb=ttb))
    assert rc == 1 and "TTB's step (5) differs from the Federal Register at" in out


def test_a_missing_ttb_step_is_counted(tmp_path):
    ttb = json.loads((DESC / "ttb-notice-243-steps.json").read_text(encoding="utf-8"))
    del ttb["96"]
    rc, out = run(layout(tmp_path, ttb=ttb))
    assert rc == 1 and re.search(r"TTB's steps: 95 in .*, 96 in the Federal Register", out)


BLOCKED = [("\u2013", "EN DASH", "-"), ("\u2014", "EM DASH", "-"), ("\u2018", "LEFT SINGLE QUOTATION MARK", "'"),
           ("\u2019", "RIGHT SINGLE QUOTATION MARK", "'"), ("\u00a0", "NO-BREAK SPACE", "a space"),
           ("\u2009", "THIN SPACE", "a space"), ("\u202f", "NARROW NO-BREAK SPACE", "a space"), ("\t", "U+0009", "a space"),
           ("\u200b", "ZERO WIDTH SPACE", "nothing"), ("\u00ad", "SOFT HYPHEN", "nothing"),
           ("\ufeff", "ZERO WIDTH NO-BREAK SPACE", "nothing"), ("\u00e9", "LATIN SMALL LETTER E WITH ACUTE",
                                                                  "a character the Federal Register uses")]


@pytest.mark.parametrize("char, name, fix", BLOCKED, ids=[n for _, n, _ in BLOCKED])
def test_a_blocked_character_in_the_proposed_steps(tmp_path, char, name, fix):
    agreed = tmp_path / "agreed-steps.json"
    agreed.write_text(json.dumps({"steps": [{"step": 7, "text": f"Proceed east{char}along the road; then"}]}), encoding="utf-8")
    rc, out = run(SCRIPT, agreed)
    assert rc == 1
    assert re.search(rf"^proposed step \(7\): {re.escape(name)} \(U\+{ord(char):04X}\) at '.*'; use {re.escape(fix)}$", out, re.M), out


def test_the_federal_registers_curly_double_quotes_are_allowed(tmp_path):
    agreed = tmp_path / "agreed-steps.json"
    agreed.write_text(json.dumps({"steps": [{"step": 36, "text": "Proceed to the marked \u201cQuarry\u201d; then"}]}), encoding="utf-8")
    assert run(SCRIPT, agreed)[0] == 0


def test_step_text_in_build_agreed_and_the_petition_is_checked(tmp_path):
    rc, out = run(layout(tmp_path, petition={"1": "Proceed\u00a0east; then"},
                         agreed='X = 1\nSTEP = "Proceed east\u2014along the road; then"\nNOTE = "not a step \u2014"\n'))
    assert rc == 1
    assert re.search(r"^petition step \(1\) in petition-steps.json: NO-BREAK SPACE \(U\+00A0\)", out, re.M), out
    assert re.search(r"^step text in build_agreed.py line 2: EM DASH \(U\+2014\)", out, re.M), out
    assert len(out.splitlines()) == 2   # "NOTE" is not step text
