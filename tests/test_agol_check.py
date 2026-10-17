"""agol_check.holds(): a dashboard link's text matches its item's title word by word, in order (#59; the phone layout's
buttons put a caption under the title, so the text runs on: "Read me first what is in this group, and the license").
"""

from src.publish.agol_check import holds


def test_holds_title_with_caption():
    assert holds(
        "0 Read me first - what is in this group, and the license",
        "Read me first what is in this group, and the license",
    )
    assert holds(
        "3a Changes side by side - TTB's text, the petition, the proposed text and why (PDF)",
        "Changes side by side TTB's text, the petition, the proposed text and why (PDF)",
    )


def test_holds_rejects_the_wrong_item():
    assert not holds(
        "3a Changes side by side - TTB's text, the petition, the proposed text and why (PDF)",
        "Read me first",
    )
    assert not holds(
        "0 Read me first - what is in this group, and the license",
        "license first",
    )  # wrong order
