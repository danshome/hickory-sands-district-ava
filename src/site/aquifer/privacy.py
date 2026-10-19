"""People's names and addresses, removed from the TWDB well reports.

The 3D aquifer page shows TWDB's Submitted Driller's Reports (SDR) and
Groundwater Database (GWDB) records as reported, but without any person's
name or address:

- whole fields are removed: REMOVED_SDR, REMOVED_PLUG and REMOVED_GWDB
  (owners, drillers, apprentices, pluggers, companies, licence numbers,
  street and mailing addresses, the free-text location description, owner
  and district well numbers);
- free text that is kept (FREE_TEXT: the lithology log, and NOTE_TEXT, the
  notes a driller types: comments, remarks, how distances were checked,
  water type, plug seal, casing notes and the like) is cleaned by
  Scrubber.clean() of: a word of a name on that record, its owner's and
  driller's initials and two-letter words included (name_tokens()); a
  whole name from the area, or a short one joined by "&" ("A&W"); a title
  such as "Mr."; a person's role ("owner", "drilled by", "plugged by"); a
  company's name ("... Well Service", "Inc.", "L & L Drilling", outside the
  log the first two words of a company in the area, "Glass Well"); a name
  or an initial after "by" ("pump by Ramm"); a word found in fewer than
  RARE_REPORTS reports' text (a person's name is rare; the vocabulary of
  wells is not); a telephone number, an e-mail address, a street or
  post-office address; a well's number in a groundwater district's
  register ("BPGCD # 20250027", which leads to its owner); and initials
  glued to a number ("57481JP"); and, in the notes where drillers write
  about people (COMMENT_LIKE: comments, remarks, how distances were
  checked, variances), any word of any name in the area, a word for a way
  to reach someone (phone, contact) or initials (^AB, ~CD).

A note that holds any of these is blanked whole, so a name the rules miss
beside one they find goes with it. A line of the well log (SPAN_FIELDS)
keeps its geology: only the part that names someone is replaced by MARK
(from a role, a title or "by" to the end of the line), and the line is
blanked whole only when nothing else is left or something still matches.
A lithology line keeps its rock class (params.CLASS_RULES), which the page
draws, either way. check() is the generator's hard check on what it wrote;
scan() is the part of it that needs no names list, which the unit tests run
on the committed files. Standard library only.
"""

import collections
import hashlib
import itertools
import json
import os
import re

REMOVED_SDR = frozenset(
    {
        "OwnerName",
        "OwnerAddress1",
        "OwnerAddress2",
        "OwnerCity",
        "OwnerState",
        "OwnerZip",
        "OwnerOtherCountry",
        "OwnerCountry",
        "OwnerWellNumber",
        "WellAddress1",
        "WellAddress2",
        "WellCity",
        "WellZip",
        "WellLocationDescription",
        "SealedByName",
        "CompanyName",
        "DrillerName",
        "DrillerSigned",
        "ApprenticeSigned",
        "DrillerAddress1",
        "DrillerAddress2",
        "DrillerCity",
        "DrillerState",
        "DrillerZip",
        "DrillerOtherCountry",
        "DrillerCountry",
        "LicenseNumber",
        "ApprenticeRegistrationNumber",
    }
)
NAMES_SDR = (
    "OwnerName",
    "SealedByName",
    "CompanyName",
    "DrillerName",
    "DrillerSigned",
    "ApprenticeSigned",
)
REMOVED_PLUG = frozenset(
    {
        "OwnerName",
        "OwnerAddress1",
        "OwnerAddress2",
        "OwnerCity",
        "OwnerState",
        "OwnerZip",
        "OwnerOtherCountry",
        "OwnerCountry",
        "OwnerWellNumber",
        "WellAddress1",
        "WellAddr2",
        "WellCity",
        "WellZip",
        "WellLocationDescription",
        "OriginalCompanyName",
        "OriginalDrillerName",
        "OriginalLicenseNumber",
        "CompanyName",
        "PluggerName",
        "DrillerAddress1",
        "DrillerAddress2",
        "DrillerCity",
        "DrillerState",
        "DrillerZip",
        "DrillerOtherCountry",
        "DrillerCountry",
        "LicenseNumber",
        "DrillerSigned",
        "ApprenticeSigned",
        "ApprenticeRegistrationNumber",
    }
)
NAMES_PLUG = (
    "OwnerName",
    "OriginalCompanyName",
    "OriginalDrillerName",
    "CompanyName",
    "PluggerName",
    "DrillerSigned",
    "ApprenticeSigned",
)
REMOVED_GWDB = frozenset(
    {
        "Owner",
        "Driller",
        "GCDWellNumber",
        "OwnerWellNumber",
        "OtherWellNumber",
    }
)
NAMES_GWDB = ("Owner", "Driller")
REMOVED = REMOVED_SDR | REMOVED_PLUG | REMOVED_GWDB
# Every field name that could hold a person's name, an address or a contact,
# whatever the table: none may appear in what the page reads.
NAME_FIELD = re.compile(
    r"owner|driller|apprentice|plugger|company|licen[cs]e|contact|address"
    r"|sealedby|signed|phone|email",
    re.IGNORECASE,
)
# TWDB's yes-or-no flags whose names NAME_FIELD would catch: kept, and only
# while every value is one of FLAG_VALUES.
FLAG_FIELDS = frozenset(
    {
        "LocationVerifiedByDriller",
        "SealedByDriller",
        "CompletedByDriller",
    }
)
FLAG_VALUES = frozenset({"Yes", "No", ""})
# The notes a driller or TWDB types, in every table: each is free text.
NOTE_TEXT = frozenset(
    {
        "Comments",
        "Remarks",
        "KnownLocationError",
        "TypeOfWorkOtherDesc",
        "ProposedUseOtherDesc",
        "SealMethodOtherDesc",
        "SurfaceCompletionOtherDesc",
        "PumpTypeOtherDesc",
        "PluggingMethodOtherDesc",
        "OriginalWellUseOtherDesc",
        "MigratedCasingInfo",
        "MigratedStrataDepth",
        "CasingMaterialOtherDesc",
        "CasingTypeOtherDesc",
        "TestTypeOtherDesc",
        "MeasurementMethodOtherDesc",
        "DistanceVerificationMethod",
        "ApprovedByVariance",
        "DistanceToPropertyLine",
        "DistanceToSepticTank",
        "DistanceToSepticOrOtherContamination",
        "WaterType",
        "PlugSeal",
        "Schedule",
    }
)
FREE_TEXT = NOTE_TEXT | {"LithologyDescription"}
# The notes where a driller writes about people (who said, who checked):
# they are blanked also for any word of any name in the area, a role word
# or initials.
COMMENT_LIKE = frozenset(
    {
        "Comments",
        "Remarks",
        "KnownLocationError",
        "DistanceVerificationMethod",
        "ApprovedByVariance",
    }
)
# A word in fewer reports' free text than this is taken for a name.
RARE_REPORTS = 8

# Words in names too common to identify anyone, and the vocabulary of well
# logs, so a name such as "Rock" or "Sand" does not blank a lithology line.
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "the",
        "of",
        "for",
        "at",
        "by",
        "on",
        "in",
        "to",
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "llc",
        "ltd",
        "lp",
        "llp",
        "pc",
        "dba",
        "water",
        "well",
        "wells",
        "drilling",
        "drill",
        "driller",
        "drillers",
        "service",
        "services",
        "supply",
        "pump",
        "pumps",
        "pumping",
        "ranch",
        "ranches",
        "farm",
        "farms",
        "cattle",
        "land",
        "lands",
        "properties",
        "property",
        "investments",
        "investment",
        "group",
        "holdings",
        "enterprises",
        "development",
        "developers",
        "trust",
        "estate",
        "family",
        "partners",
        "partnership",
        "texas",
        "tx",
        "city",
        "county",
        "state",
        "usa",
        "us",
        "mud",
        "wsc",
        "sud",
        "district",
        "authority",
        "utility",
        "utilities",
        "association",
        "assoc",
        "church",
        "school",
        "isd",
        "camp",
        "club",
        "park",
        "lake",
        "river",
        "creek",
        "hill",
        "hills",
        "valley",
        "oak",
        "oaks",
        "springs",
        "spring",
        "north",
        "south",
        "east",
        "west",
        "new",
        "old",
        "first",
        "second",
        "third",
        "mr",
        "mrs",
        "ms",
        "dr",
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
        "sand",
        "sandstone",
        "stone",
        "rock",
        "rocks",
        "lime",
        "limestone",
        "clay",
        "shale",
        "gravel",
        "granite",
        "gray",
        "grey",
        "brown",
        "red",
        "white",
        "black",
        "blue",
        "green",
        "yellow",
        "tan",
        "pink",
        "hard",
        "soft",
        "top",
        "soil",
        "caliche",
        "shell",
        "sandy",
        "silt",
        "silty",
        "marble",
        "schist",
        "gneiss",
        "hickory",
        "brush",
        "cedar",
        "pine",
        "wood",
        "woods",
        "field",
        "fields",
        "home",
        "homes",
        "road",
        "del",
        "rio",
        "san",
        "santa",
        "los",
        "las",
    ]
)
# The vocabulary of sealing and plugging, which some name fields carry
# instead of a name ("slurried and poured", "pressure cemented").
TECH = frozenset(
    [
        "slurried",
        "slurry",
        "poured",
        "pour",
        "pressure",
        "pressured",
        "cemented",
        "cement",
        "grout",
        "grouting",
        "grouted",
        "hand",
        "trimmy",
        "tremie",
        "tremmie",
        "trimmie",
        "tube",
        "pipe",
        "backfilled",
        "backfill",
        "cuttings",
        "within",
        "feet",
        "data",
        "no",
        "green",
        "light",
        "dry",
        "hole",
        "well",
        "wells",
        "plugged",
        "plug",
        "by",
        "mixed",
        "mix",
        "cap",
        "rock",
        "dug",
        "ready",
        "installed",
        "not",
        "previous",
        "see",
        "comments",
        "top",
        "job",
        "oil",
        "unknown",
        "lost",
        "bh",
        "gray",
        "shell",
        "and",
        "with",
        "to",
        "the",
        "of",
        "in",
        "from",
        "bentonite",
        "chips",
        "pellets",
        "surface",
        "seal",
        "sealed",
        "sealing",
        "method",
        "none",
        "other",
        "n/a",
        "na",
        "annular",
    ]
)

TITLE = re.compile(r"\b(mr|mrs|ms|miss|dr)\.?\s+[a-z]", re.IGNORECASE)
# A person's role, in any free text: who owns, drilled, plugged, logged or
# inspected a well.
ROLE = re.compile(
    r"\b(owner|owned|landowner|driller|drilled\s+by|plugged\s+by|plugger"
    r"|licen[cs]e|lic\.?\s*#|apprentice|logged\s+by|insp\.?|inspector"
    r"|surveyo?e?r|engineer|realtor|builder|customer|contractor)\b",
    re.IGNORECASE,
)
# A way to reach someone: in the notes about people only (in a well log, a
# "contact" is where two rocks meet).
CONTACT = re.compile(r"\b(contact|phone|cell|tel\.?)\b", re.IGNORECASE)
COMPANY = re.compile(
    r"\b(well|water|pump|drilling|drill)\s*(services?|serv|drilling|supply"
    r"|wells|co|company)\b|\b(inc|llc|ltd|corp)\b\.?|&\s*supply\b",
    re.IGNORECASE,
)
# A company's name in capitals or capitalized words, then its trade: "L & L
# Drilling", "MH DRILLING", "Glass Well Service" (case-sensitive). Not when
# every word before the trade is a word of the log (NOT_NAMES: "Hard
# Drilling", "SANDY DRILLING").
COMPANY_NAMED = re.compile(
    r"\b((?:[A-Z][A-Za-z'.]*\s*(?:&\s*)?){1,4})"
    r"(?:Drilling|DRILLING|Well\s+Services?|WELL\s+SERVICES?|Pump\s+Service"
    r"|PUMP\s+SERVICE)\b"
)
INITIALS = re.compile(r"[\^~$]\s*[a-z]{1,5}\b|\b[a-z]{1,5}\s*\$", re.IGNORECASE)
# A name or an initial after "by", "By" or "BY" ("pump by Ramm", "Drilled By
# L & L"), unless the word after it is not a name (NOT_NAMES: "by hand").
BY_NAME = re.compile(r"\b[Bb][Yy]\s+([A-Z][A-Za-z']*)")
# A well's number in a groundwater district's register, which leads to its
# owner: "BPGCD # 20250027", "SWTCGCD - 57482CR", "District Well # 8178".
DISTRICT_ID = re.compile(
    r"\b[A-Z]{1,8}(?:GCD|CD|WD|GWD|UWCD)\b\s*(?:[Ww]ell\s*)?(?:#|[Nn]o\.?|-|@)?"
    r"\s*\d[\w-]*"
    r"|\b[A-Z]{3,7}\s*(?:#|[Ww]ell\s*#)\s*\d{4,}\w*"
    r"|(?i:\bdistrict\s+well\s*(?:#|no\.?|number)?\s*\d[\w-]*)"
)
# Two or three capitals glued to a number, as someone's initials on it
# ("57481JP", "56-13-91EK"), unless they are a unit or a direction (UNITS).
GLUED = re.compile(r"(?<=\d)([A-Z]{2,3})\b")
UNITS = frozenset(
    {
        "OD",
        "ID",
        "FT",
        "GPM",
        "GPH",
        "GAL",
        "YR",
        "IB",
        "PSI",
        "TDS",
        "PPM",
        "ST",
        "ND",  # an ordinal, as in 2ND; codespell:ignore
        "RD",
        "TH",
        "IN",
        "PVC",
        "MM",
        "CM",
        "HP",
        "TD",
        "SDR",
        "SS",
        "HRS",
        "YDS",
        "LB",
        "LBS",
        "AM",
        "PM",
        "BGS",
        "MSL",
        "NE",
        "NW",
        "SE",
        "SW",
        "NNE",
        "NNW",
        "SSE",
        "SSW",
        "ENE",
        "ESE",
        "WNW",
        "WSW",
    }
)
# Short names joined by "&" ("A & W", "A&W"): looked for in every free text
# when a name in the area has one (Scrubber.amps).
AMP = re.compile(r"\b([A-Za-z]{1,3})\s*&\s*([A-Za-z]{1,3})\b")
# The second word of a company's name that makes its first two words a name
# to look for in the notes ("Glass Well ..."): see Scrubber.finish().
TRADE_WORDS = frozenset({"well", "wells", "water", "pump", "drilling"})
PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
EMAIL = re.compile(r"\S+@\S+")
STREET = re.compile(
    r"\b\d{2,6}\s+([a-z0-9.]+\s+){0,3}(road|rd|street|st|drive|dr|lane|ln"
    r"|avenue|ave|blvd|boulevard|hwy|highway|circle|cir|court|ct|trail|trl"
    r"|loop|way|parkway|pkwy|place|pl)\b\.?"
    r"|\b(p\.?\s*o\.?\s*box|box\s+\d+|rr\s*\d+|rt\.?\s*\d+)\b"
    r"|\b(tx|tex|texas)\.?,?\s+\d{5}(-\d{4})?\b",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z][a-z']+")
# The same words in text of any case, with their places in it.
WORD_ANY = re.compile(r"[A-Za-z][A-Za-z']+")
# The words of the drilling itself, which the words of a company's name or
# a name after "by" are not ("Hard Drilling", "by hand").
DRILL_WORDS = frozenset(
    {
        "hard",
        "harder",
        "soft",
        "softer",
        "sandy",
        "porous",
        "pourous",
        "blind",
        "void",
        "med",
        "medium",
        "slow",
        "fast",
        "easy",
        "rough",
        "good",
        "poor",
        "firm",
        "smooth",
        "tight",
        "rocky",
        "hammer",
        "air",
        "rotary",
        "cable",
        "break",
        "normal",
        "very",
        "fair",
        "broken",
        "loose",
        "dense",
        "solid",
        "this",
        "that",
        "same",
    }
)
# Two-letter words that are never taken for a name's.
SHORT_STOP = frozenset(
    {"no", "ok", "or", "is", "it", "be", "as", "so", "up", "do", "if", "me"}
)
# Fields whose values come from TWDB's code tables or registers (a use, an
# aquifer, a county, a public water system's number): never a person's
# name, though a rare code may share a word or initials with one.
CODED = frozenset(
    {
        "WellUse",
        "ProposedUse",
        "OriginalWellUse",
        "PWSNo",
        "County",
        "Aquifer",
        "AquiferCode",
        "AquiferCodeDescription",
        "OtherDataAvailable",
    }
)
# What replaces the part of a well log's line that names someone.
MARK = "[removed]"
# The free text whose matches are replaced by MARK, not blanked whole.
SPAN_FIELDS = frozenset({"LithologyDescription"})


def rules_digest():
    """A digest of every rule here, for the record's parameters.

    Returns:
        "sha256:" and the hex digest of the field lists, word lists and
        patterns, so a change to any of them makes the page's data stale.
    """
    rules = {
        "removed": sorted(REMOVED),
        "names": [NAMES_SDR, NAMES_PLUG, NAMES_GWDB],
        "free_text": sorted(FREE_TEXT),
        "note_text": sorted(NOTE_TEXT),
        "comment_like": sorted(COMMENT_LIKE),
        "rare_reports": RARE_REPORTS,
        "stop": sorted(STOP),
        "tech": sorted(TECH),
        "patterns": [
            p.pattern
            for p in (
                NAME_FIELD,
                TITLE,
                ROLE,
                CONTACT,
                COMPANY,
                COMPANY_NAMED,
                INITIALS,
                BY_NAME,
                DISTRICT_ID,
                GLUED,
                AMP,
                PHONE,
                EMAIL,
                STREET,
                WORD_ANY,
            )
        ],
        "flags": [sorted(FLAG_FIELDS), sorted(FLAG_VALUES)],
        "trade_words": sorted(TRADE_WORDS),
        "units": sorted(UNITS),
        "drill_words": sorted(DRILL_WORDS),
        "short_stop": sorted(SHORT_STOP),
        "mark": MARK,
        "coded": sorted(CODED),
        "span_fields": sorted(SPAN_FIELDS),
    }
    text = json.dumps(rules, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(text).hexdigest()


def tokens(text):
    """The words of a name that could identify someone.

    Args:
        text: A name as a report gives it.

    Returns:
        Its lower-case words of three letters or more, less STOP.
    """
    return {
        t
        for t in WORD.findall((text or "").lower())
        if len(t) >= 3 and t not in STOP
    }


def name_tokens(names):
    """The words of a record's own names, initials and short words included.

    Args:
        names: The record's name fields' values (owner, driller, company,
            plugger ...).

    Returns:
        tokens() of each, its two-letter words (less STOP and SHORT_STOP),
        and its initials (of its first four words): every two of them either
        way round, and all of them in the order written and with the first
        last, as "Smith, John Paul" is written "JPS".
    """
    out = set()
    for name in names:
        if not name:
            continue
        out |= tokens(name)
        words = re.findall(r"[a-z]+", name.lower())
        out |= {
            w
            for w in words
            if len(w) == 2 and w not in STOP and w not in SHORT_STOP
        }
        letters = [w[0] for w in words if w not in STOP][:4]
        if len(letters) >= 2:
            # Every pair, either way round, and all of them, in the order
            # written and with the first word last ("Smith, John Paul"):
            # "jp", "js", "sjp", "jps" ...
            out |= {
                a + b
                for i, a in enumerate(letters)
                for j, b in enumerate(letters)
                if i != j
            }
            out |= {"".join(letters), "".join(letters[1:] + letters[:1])}
    return {t for t in out if t not in SHORT_STOP}


def not_a_name(word):
    """Whether a word is a word of the logs, never a name's."""
    word = word.lower()
    return word in STOP or word in TECH or word in DRILL_WORDS


def name_start(text, start):
    """Where a company's name begins, before its trade words.

    Args:
        text: Free text.
        start: Where the trade words ("Well Service") begin.

    Returns:
        The place of the first of up to four capitalized words, initials or
        "&" just before them.
    """
    pos = start
    for _ in range(4):
        m = re.search(r"(?:[A-Z][A-Za-z'.]*|&)\s*$", text[:pos])
        if not m or (m.start() > 0 and text[m.start() - 1].isalnum()):
            break
        pos = m.start()
    return pos


def company_spans(text):
    """The parts of a text that are a company's name.

    Args:
        text: Free text.

    Returns:
        A list of (start, end): COMPANY's matches with the name before
        them, and COMPANY_NAMED's whose name words are not all NOT_NAMES.
    """
    out = [
        (name_start(text, m.start()), m.end()) for m in COMPANY.finditer(text)
    ]
    for m in COMPANY_NAMED.finditer(text):
        words = re.findall(r"[A-Za-z']+", m.group(1))
        if not words or not all(not_a_name(w) for w in words):
            out.append(m.span())
    return out


def by_names(text):
    """Where each name after "by" begins (at the "by").

    Args:
        text: Free text.

    Returns:
        A list of places.
    """
    return [
        m.start() for m in BY_NAME.finditer(text) if not not_a_name(m.group(1))
    ]


def glued_spans(text):
    """The initials glued to a number in a text, less units ("57481JP").

    Args:
        text: Free text.

    Returns:
        A list of (start, end) of the letters.
    """
    return [m.span(1) for m in GLUED.finditer(text) if m.group(1) not in UNITS]


def mask(text, spans):
    """A text with its spans replaced.

    Args:
        text: The text.
        spans: (start, end, replacement) triples, in any order; they may
            overlap.

    Returns:
        The text, each run of spans replaced once, spaces tidied.
    """
    out = []
    pos = 0
    for start, end, repl in sorted(spans):
        if end <= pos:
            continue
        if start >= pos:
            out.append(text[pos:start])
            out.append(repl)
        elif repl and not out[-1]:
            out[-1] = repl  # a span reaching past an empty one
        pos = end
    out.append(text[pos:])
    joined = "".join(out)
    marks = re.escape(MARK)
    joined = re.sub(rf"{marks}(?:[\s,;:&/-]*{marks})+", MARK, joined)
    return re.sub(r"\s{2,}", " ", joined).strip()


class Scrubber:
    """Blanks free text that may name a person or give an address.

    Attributes:
        area_tokens: Every name word from every report in the area.
        blanked: How many texts were blanked, by field.
    """

    def __init__(self, extra_words=()):
        """Starts with no names.

        Args:
            extra_words: More words that blank any free text holding them
                (the gitignored .private-words, when the generator finds it).
        """
        self.area_tokens = set()
        self.area_names = set()
        self.blanked = collections.Counter()
        self.grams = set()
        self.starts = set()
        self.lengths = []
        self.extra = {w.lower() for w in extra_words if w.strip()}
        self.reports = collections.Counter()
        self.amps = set()
        self.redacted = collections.Counter()

    def count(self, record):
        """Counts the words of a record's free text, once per record.

        Args:
            record: A report (a dict), its tables included.
        """
        words = set()
        for _, text in free_texts(record):
            words |= set(WORD.findall(text.lower()))
        self.reports.update(words)

    def rare_in(self, text):
        """The first word of a text found in fewer than RARE_REPORTS reports.

        Args:
            text: Free text.

        Returns:
            The word, or None. Words of fewer than three letters and the
            STOP and TECH words are never rare.
        """
        for word in WORD.findall(text.lower()):
            if self.is_rare(word):
                return word
        return None

    def is_rare(self, word):
        """Whether a word is in fewer than RARE_REPORTS reports' text.

        Args:
            word: A lower-case word.

        Returns:
            False for words of fewer than three letters and the STOP and TECH
            words.
        """
        return (
            len(word) >= 3
            and word not in STOP
            and word not in TECH
            and self.reports[word] < RARE_REPORTS
        )

    def amp_spans(self, text):
        """The short names joined by "&" from the area in a text ("A&W").

        Args:
            text: Free text.

        Returns:
            A list of (start, end).
        """
        return [
            m.span()
            for m in AMP.finditer(text)
            if f"{m.group(1)}&{m.group(2)}".lower() in self.amps
        ]

    def learn(self, names):
        """Adds a report's names to the area's.

        Args:
            names: The report's name fields' values.
        """
        for name in names:
            if name:
                self.area_tokens |= tokens(name)
                self.area_names.add(name.lower())
                self.amps |= {f"{a}&{b}" for a, b in AMP.findall(name.lower())}

    def finish(self):
        """Makes the whole names from the area into word sequences."""
        for name in self.area_names:
            words = tuple(WORD.findall(name))
            if len(words) >= 2 and any(
                w not in STOP and w not in TECH and len(w) >= 3 for w in words
            ):
                self.grams.add(words)
            if (
                len(words) >= 2
                and words[1] in TRADE_WORDS
                and len(words[0]) >= 2
                and words[0] not in STOP
                and words[0] not in TECH
                and words[0] not in SHORT_STOP
            ):
                self.starts.add(words[:2])
        self.lengths = sorted({len(g) for g in self.grams})

    def start_in(self, text):
        """The first company name's start ("glass well") in a text, or None.

        Args:
            text: Free text.

        Returns:
            The two words joined by a space, or None.
        """
        words = WORD.findall(text.lower())
        for pair in itertools.pairwise(words):
            if pair in self.starts:
                return " ".join(pair)
        return None

    def area_name_in(self, text):
        """The first whole name from the area in a text, or None.

        Args:
            text: Free text.

        Returns:
            The name, as its words joined by spaces, or None.
        """
        words = WORD.findall(text.lower())
        for n in self.lengths:
            for i in range(len(words) - n + 1):
                if tuple(words[i : i + n]) in self.grams:
                    return " ".join(words[i : i + n])
        return None

    def extra_in(self, text):
        """Whether a text holds one of the extra words."""
        low = text.lower()
        return any(w in low for w in self.extra)

    def hit(self, text, record_tokens, field):
        """Whether a free text may name someone or give an address.

        Args:
            text: The text.
            record_tokens: The name words of the record the text is on
                (name_tokens()).
            field: The field's name.

        Returns:
            True when any rule in the module's docstring matches.
        """
        note = field in COMMENT_LIKE
        words = set(WORD.findall(text.lower()))
        return bool(
            (words & record_tokens)
            or (note and (words & self.area_tokens))
            or TITLE.search(text)
            or ROLE.search(text)
            or (note and CONTACT.search(text))
            or (note and INITIALS.search(text))
            or company_spans(text)
            or by_names(text)
            or (field not in SPAN_FIELDS and self.start_in(text))
            or PHONE.search(text)
            or EMAIL.search(text)
            or STREET.search(text)
            or DISTRICT_ID.search(text)
            or glued_spans(text)
            or self.amp_spans(text)
            or self.area_name_in(text)
            or self.extra_in(text)
            or self.rare_in(text)
        )

    def spans(self, text, record_tokens):
        """The parts of a well log's line that may name someone.

        Args:
            text: The line.
            record_tokens: The name words of the record it is on.

        Returns:
            (start, end, replacement) triples: from a title, a role or a
            name after "by" to the end of the line; a company's name; a
            phone number, an e-mail, a street or a district's well number;
            a short "&" name from the area; a word of the record's names, a
            rare word, a whole name from the area or a private word; each
            replaced by MARK, and initials glued to a number by nothing.
        """
        end = len(text)
        found = [
            (m.start(), end) for rx in (TITLE, ROLE) if (m := rx.search(text))
        ]
        found += [(start, end) for start in by_names(text)]
        found += company_spans(text)
        for rx in (PHONE, EMAIL, STREET, DISTRICT_ID):
            found += [m.span() for m in rx.finditer(text)]
        found += self.amp_spans(text)
        words = [(m.group().lower(), m.span()) for m in WORD_ANY.finditer(text)]
        found += [
            span
            for word, span in words
            if word in record_tokens or self.is_rare(word)
        ]
        for n in self.lengths:
            for i in range(len(words) - n + 1):
                if tuple(w for w, _ in words[i : i + n]) in self.grams:
                    found.append((words[i][1][0], words[i + n - 1][1][1]))
        low = text.lower()
        for word in self.extra:
            at = low.find(word)
            while at >= 0:
                found.append((at, at + len(word)))
                at = low.find(word, at + 1)
        out = [(a, b, MARK) for a, b in found]
        out += [(a, b, "") for a, b in glued_spans(text)]
        return out

    def clean(self, text, record_tokens, field):
        """A free text without what may name someone or give an address.

        Args:
            text: The text.
            record_tokens: The name words of the record the text is on
                (name_tokens()).
            field: The field's name.

        Returns:
            A note unchanged, or "" when hit() finds anything in it; a line
            of the log (SPAN_FIELDS) with the spans() replaced, or "" when
            nothing else is left or hit() still finds something.
        """
        if not text:
            return text
        if field not in SPAN_FIELDS:
            if self.hit(text, record_tokens, field):
                self.blanked[field] += 1
                return ""
            return text
        spans = self.spans(text, record_tokens)
        if not spans:
            return text
        out = mask(text, spans)
        rest = out.replace(MARK, " ")
        if not re.search(r"[A-Za-z]{2}", rest) or self.hit(
            rest, record_tokens, field
        ):
            self.blanked[field] += 1
            return ""
        self.redacted[field] += 1
        return out

    def walk(self, item, record_tokens):
        """Cleans every free text in a record, in place.

        Args:
            item: A record (a dict), or a list of them.
            record_tokens: The record's name words.
        """
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, str) and key in FREE_TEXT:
                    item[key] = self.clean(value, record_tokens, key)
                elif isinstance(value, (dict, list)):
                    self.walk(value, record_tokens)
        elif isinstance(item, list):
            for value in item:
                self.walk(value, record_tokens)


def free_texts(item):
    """Every free-text value in a record, with its field.

    Args:
        item: A record (a dict) or a list.

    Returns:
        A list of (field, text).
    """
    out = []
    stack = [item]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            for key, value in x.items():
                if isinstance(value, str) and key in FREE_TEXT:
                    out.append((key, value))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(x, list):
            stack.extend(x)
    return out


def field_names(item):
    """Every key at any depth of a record.

    Args:
        item: A record (a dict) or a list.

    Returns:
        The set of keys.
    """
    out = set()
    stack = [item]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            out |= set(x)
            stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            stack.extend(x)
    return out


def flag_values(item):
    """Every value of a FLAG_FIELDS field at any depth of a record.

    Args:
        item: A record (a dict) or a list.

    Returns:
        A list of (field, value).
    """
    out = []
    stack = [item]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            out += [(k, v) for k, v in x.items() if k in FLAG_FIELDS]
            stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            stack.extend(x)
    return out


def named_fields(item):
    """The field names in a record that could hold a person's name.

    Args:
        item: A record (a dict) or a list, or a whole file's data.

    Returns:
        A list of problems: each removed field, each field whose name
        NAME_FIELD catches but FLAG_FIELDS does not hold, and each flag
        whose value is not a yes or a no.
    """
    problems = [
        f"field {k}"
        for k in sorted(field_names(item))
        if k in REMOVED or (NAME_FIELD.search(k) and k not in FLAG_FIELDS)
    ]
    problems += [
        f"flag {k} holds {v!r}"
        for k, v in flag_values(item)
        if v not in FLAG_VALUES
    ]
    return problems


def scan_record(record):
    """What a record holds that may name someone, needing no names list.

    Args:
        record: A well's raw report as the page reads it.

    Returns:
        A list of problems, each a short description: a removed field or a
        field name that could hold a name, or free text (MARK aside) with a
        title, a role word, a company's name, a name after "by", a
        telephone number, an e-mail, a street address, a district's well
        number or initials glued to a number, or a note with a word for a
        way to reach someone or initials.
    """
    problems = named_fields(record)
    for field, raw in free_texts(record):
        text = raw.replace(MARK, " ")
        for name, found in (
            ("title", TITLE.search(text)),
            ("role word", ROLE.search(text)),
            ("company", company_spans(text)),
            ("a name after by", by_names(text)),
            ("phone", PHONE.search(text)),
            ("e-mail", EMAIL.search(text)),
            ("address", STREET.search(text)),
            ("district well number", DISTRICT_ID.search(text)),
            ("initials on a number", glued_spans(text)),
        ):
            if found:
                problems.append(f"{name} in {field}")
        if field in COMMENT_LIKE:
            if CONTACT.search(text):
                problems.append(f"contact word in {field}")
            if INITIALS.search(text):
                problems.append(f"initials in {field}")
    return problems


def strings(item):
    """Every string at any depth of a record, with its field.

    Args:
        item: A record (a dict) or a list.

    Returns:
        A list of (field, value).
    """
    out = []
    stack = [item]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            for key, value in x.items():
                if isinstance(value, str):
                    out.append((key, value))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(x, list):
            stack.extend(x)
    return out


def scan(folder):
    """Scans every JSON file under a folder for names and contacts.

    Args:
        folder: docs/assets/aquifer, or the generator's new copy of it.

    Returns:
        A list of (file, record id or "", problem).
    """
    bad = []
    for top, _, names in os.walk(folder):
        for name in sorted(names):
            if not name.endswith((".json", ".geojson")):
                continue
            path = os.path.join(top, name)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            rel = os.path.relpath(path, folder)
            if name.startswith("detail-"):
                for uid, record in data.items():
                    bad += [(rel, uid, p) for p in scan_record(record)]
            else:
                bad += [(rel, "", p) for p in named_fields(data)]
    return bad


def check(folder, names_by_record, scrubber):
    """The generator's hard check: no name survives in what it wrote.

    Args:
        folder: The new copy of docs/assets/aquifer.
        names_by_record: The name words of each record (name_tokens(), the
            owner's and driller's initials included), by its id ("S" and the
            report's tracking number, or "G" and the state well number).
        scrubber: The Scrubber that cleaned the records (its area names).

    Returns:
        A list of (file, record id, problem); empty when nothing survives.
        Beside scan()'s problems: a word of the record's own names (its
        initials included) anywhere in its free text, or in any other text
        of its but TWDB's code fields (CODED) and the words of a field that
        RARE_REPORTS records or more hold (codes); and in its free text
        a whole name or a short "&" name from the area, a private word, a
        rare word, a company's name in a note, or (in the notes about
        people) any word of a name in the area.
    """
    bad = scan(folder)
    wells = os.path.join(folder, "wells")
    records = {}
    for name in sorted(os.listdir(wells)):
        if name.startswith("detail-"):
            with open(os.path.join(wells, name), encoding="utf-8") as fh:
                for uid, record in json.load(fh).items():
                    records[uid] = (name, record)
    # How many records hold each word of each field that is not free text:
    # a word in RARE_REPORTS records or more is one of TWDB's codes.
    codes = collections.Counter()
    for _, record in records.values():
        codes.update(
            {
                (k, w)
                for k, v in strings(record)
                if k not in FREE_TEXT and k not in CODED
                for w in WORD.findall(v.lower())
            }
        )
    for uid, (name, record) in records.items():
        own = names_by_record.get(uid, set())
        for field, value in strings(record):
            if field in FREE_TEXT or field in CODED:
                continue
            words = {
                w
                for w in WORD.findall(value.lower())
                if codes[field, w] < RARE_REPORTS
            }
            if words & own:
                bad.append((name, uid, f"a word of its own names in {field}"))
        for field, raw in free_texts(record):
            text = raw.replace(MARK, " ")
            words = set(WORD.findall(text.lower()))
            problem = (
                (words & own and "a word of the record's own names")
                or (scrubber.area_name_in(text) and "a name from the area")
                or (scrubber.amp_spans(text) and "a short & name from the area")
                or (scrubber.extra_in(text) and "a private word")
                or (scrubber.rare_in(text) and "a rare word")
                or (
                    field not in SPAN_FIELDS
                    and scrubber.start_in(text)
                    and "a company's name"
                )
                or (
                    field in COMMENT_LIKE
                    and words & scrubber.area_tokens
                    and "an area name word"
                )
            )
            if problem:
                bad.append((name, uid, f"{problem} in {field}"))
    return bad
