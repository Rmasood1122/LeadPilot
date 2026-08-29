"""The tutorial catalogue — the single source of truth for "Learn LeadPilot".

WHY THIS IS CODE AND NOT A DATABASE TABLE
-----------------------------------------
The videos are editorial content that changes when someone records a new one,
not user data. Keeping the catalogue here means:

  * replacing a placeholder with a real YouTube id is a one-line edit in a
    reviewed, version-controlled file -- not hand-written SQL against the
    production database, and not an admin CMS nobody asked for;
  * the catalogue is identical in every environment, so a bug reproduces
    locally instead of depending on which rows a database happens to hold;
  * there is one migration for this feature instead of two tables.

The cost, stated plainly: adding a video needs a deploy, not a form. If
admin-editable tutorials are ever wanted, this module becomes the seed data
for a `tutorials` table and the API contract below does not change -- the
endpoints already speak in slugs, not row ids, exactly so that swap stays
cheap.

PROGRESS is the opposite kind of data -- per user, high write volume -- and
lives in the `tutorial_progress` table (models.py, migration 0016).

REPLACING THE PLACEHOLDERS
--------------------------
Set `youtube_id` on each entry to the 11-character id from the video's URL:

    https://www.youtube.com/watch?v=dQw4w9WgXcQ
                                   ^^^^^^^^^^^ this part

Leave it None until the video exists. `None` is deliberately not an empty
string or a fake id: the API reports `is_placeholder: true` and the UI shows a
"coming soon" panel instead of an <iframe> pointing at nothing. A fake id
would render a broken YouTube player and look like a bug.

Set `duration_seconds` too when you know it -- it drives the progress bar's
denominator before the player has reported a duration.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Tutorial",
    "LEVELS",
    "LEVEL_LABELS",
    "CATALOGUE",
    "BADGES",
    "by_slug",
    "search",
    "slugs_for_level",
    "badge_definitions",
]

# Ordered easiest-first. The API and the UI both rely on this order, so it is
# defined once here rather than being re-sorted at each call site.
LEVELS = ("beginner", "intermediate", "advanced")

LEVEL_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}


@dataclass(frozen=True)
class Tutorial:
    """One video in the catalogue.

    Frozen: the catalogue is read-only at runtime. A mutable dataclass would
    let one request's handler mutate the object every other request shares.
    """

    slug: str
    title: str
    description: str
    level: str
    order: int
    # None until the real video exists -- see the module docstring.
    youtube_id: str | None = None
    duration_seconds: int | None = None

    @property
    def is_placeholder(self) -> bool:
        return not self.youtube_id

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "level": self.level,
            "order": self.order,
            "youtube_id": self.youtube_id,
            "duration_seconds": self.duration_seconds,
            "is_placeholder": self.is_placeholder,
        }


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------
# `order` is within a level, not global. Slugs are permanent: they are the
# foreign key tutorial_progress rows point at, so RENAMING A SLUG ORPHANS every
# user's progress for that video. Change titles freely; change slugs never.

CATALOGUE: tuple[Tutorial, ...] = (
    # -- Beginner -----------------------------------------------------------
    Tutorial(
        slug="getting-started-with-leadpilot",
        title="Getting Started with LeadPilot",
        description=(
            "A tour of the platform end to end: what LeadPilot automates, how a "
            "strategy becomes a booked meeting, and what to set up first."
        ),
        level="beginner",
        order=1,
    ),
    Tutorial(
        slug="setting-up-your-first-campaign",
        title="Setting Up Your First Campaign",
        description=(
            "Create a product, run the intake wizard, and launch your first "
            "outreach sequence without sending anything you did not mean to."
        ),
        level="beginner",
        order=2,
    ),
    Tutorial(
        slug="understanding-your-icp",
        title="Understanding Your ICP",
        description=(
            "What an Ideal Customer Profile is, how LeadPilot extracts one from "
            "your past clients, and how to correct it when it gets you wrong."
        ),
        level="beginner",
        order=3,
    ),
    # -- Intermediate -------------------------------------------------------
    Tutorial(
        slug="advanced-lead-sourcing-with-apollo",
        title="Advanced Lead Sourcing with Apollo",
        description=(
            "Build precise Apollo searches, use enrichment without paying twice "
            "for the same contact, and keep your lead quality high at volume."
        ),
        level="intermediate",
        order=1,
    ),
    Tutorial(
        slug="writing-high-converting-dms",
        title="Writing High-Converting DMs",
        description=(
            "The anatomy of a message that gets replies: personalisation that is "
            "real, openers that are not templates, and asks people can say yes to."
        ),
        level="intermediate",
        order=2,
    ),
    Tutorial(
        slug="using-the-leadpilot-dashboard",
        title="Using the LeadPilot Dashboard",
        description=(
            "Pipeline, campaigns, strategies and settings -- what each view is "
            "for and the fastest path through your daily workflow."
        ),
        level="intermediate",
        order=3,
    ),
    # -- Advanced -----------------------------------------------------------
    Tutorial(
        slug="multi-channel-outreach-strategy",
        title="Multi-Channel Outreach Strategy",
        description=(
            "Sequencing email and WhatsApp together: when each channel earns its "
            "place, opt-in rules that keep you compliant, and timing that works."
        ),
        level="advanced",
        order=1,
    ),
    Tutorial(
        slug="reading-your-analytics",
        title="Reading Your Analytics",
        description=(
            "Which numbers actually predict booked meetings, which are noise at "
            "your volume, and how to tell a real lift from a small sample."
        ),
        level="advanced",
        order=2,
    ),
    Tutorial(
        slug="scaling-your-pipeline",
        title="Scaling Your Pipeline",
        description=(
            "Growing send volume without wrecking deliverability: warm-up, "
            "bounce thresholds, and what to fix first when reply rates fall."
        ),
        level="advanced",
        order=3,
    ),
)


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------
# Earned state is DERIVED from progress, never stored. A stored badge row can
# disagree with the progress that is supposed to justify it -- and then the
# only honest answer to "why does this user have this badge?" is "we don't
# know". Deriving it means the badge is always exactly as true as the data.


@dataclass(frozen=True)
class Badge:
    slug: str
    label: str
    description: str
    # None = "every tutorial in the catalogue"; otherwise a level name.
    level: str | None


BADGES: tuple[Badge, ...] = (
    Badge("beginner-complete", "Beginner Complete",
          "Finished every Beginner tutorial.", "beginner"),
    Badge("intermediate-complete", "Intermediate Complete",
          "Finished every Intermediate tutorial.", "intermediate"),
    Badge("advanced-complete", "Advanced Complete",
          "Finished every Advanced tutorial.", "advanced"),
    Badge("leadpilot-certified", "LeadPilot Certified",
          "Finished every tutorial in the library.", None),
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

_BY_SLUG: dict[str, Tutorial] = {t.slug: t for t in CATALOGUE}

# Fail at import time rather than at request time. A duplicate slug would make
# one tutorial permanently unreachable and silently merge two videos' progress.
assert len(_BY_SLUG) == len(CATALOGUE), "duplicate tutorial slug in CATALOGUE"
assert all(t.level in LEVELS for t in CATALOGUE), "unknown level in CATALOGUE"


def by_slug(slug: str) -> Tutorial | None:
    return _BY_SLUG.get(slug)


def slugs_for_level(level: str) -> list[str]:
    return [t.slug for t in CATALOGUE if t.level == level]


def _sort_key(t: Tutorial) -> tuple[int, int]:
    return (LEVELS.index(t.level), t.order)


def search(query: str | None = None, level: str | None = None) -> list[Tutorial]:
    """Filter the catalogue by free text and/or level, in catalogue order.

    Matching is case-insensitive substring over title AND description. Nine
    items do not need an index or a ranking function, and a substring match is
    what a user typing "apollo" or "icp" into a search box expects. Searching
    the description as well as the title is deliberate: "deliverability"
    appears only in a description, and a user who types it should still find
    "Scaling Your Pipeline".
    """
    results = list(CATALOGUE)

    if level:
        wanted = level.strip().lower()
        results = [t for t in results if t.level == wanted]

    if query:
        needle = query.strip().lower()
        if needle:
            results = [
                t for t in results
                if needle in t.title.lower() or needle in t.description.lower()
            ]

    return sorted(results, key=_sort_key)


def badge_definitions() -> tuple[Badge, ...]:
    return BADGES
