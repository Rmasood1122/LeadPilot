"""Phase 2 help center -- the corpus, its chunks, and drift against the code.

Everything here is offline and reads only files in the repository. The point
of the drift tests is that an article which states a number the code
enforces cannot silently disagree with the code: change PLANS and the plans
article test fails until the article is updated in the same PR.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.core.plans import PLANS
from app.services import help_center, support_kb
from scripts.help_center import build_index

REPO = Path(__file__).resolve().parents[2]
HELP = REPO / "docs" / "help-center"
ARTICLE_FILES = sorted(HELP.glob("[0-9][0-9]-*.md"))
ARTICLES = [p for p in ARTICLE_FILES if not p.name.startswith("00-")]


@pytest.fixture(scope="module")
def corpus() -> help_center.Corpus:
    return help_center.load_corpus(HELP)


# --------------------------------------------------------------------------
# Articles and front matter
# --------------------------------------------------------------------------


class TestArticles:
    def test_thirty_articles_plus_the_index(self):
        assert len(ARTICLES) == 30, [p.name for p in ARTICLES]
        assert (HELP / "00-index.md").is_file()

    def test_front_matter_is_complete_and_ids_are_unique(self, corpus):
        ids = [a.id for a in corpus.articles]
        assert len(ids) == len(set(ids)), ids
        for article in corpus.articles:
            assert article.id and article.title, article.filename
            assert article.audience in {"prospect", "customer", "admin"}, article.filename
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", article.last_verified), article.filename
            assert article.owner, article.filename
            assert article.sources, f"{article.filename} cites no sources"
            assert article.sections, f"{article.filename} has no H2 sections"

    def test_the_loader_reads_front_matter_exactly_like_yaml(self, corpus):
        """The loader slices the front matter itself; this proves the slice
        is the whole block, for every article."""
        by_file = {a.filename: a for a in corpus.articles}
        for path in ARTICLES:
            raw = path.read_text(encoding="utf-8")
            block = raw.split("---", 2)[1]
            meta = yaml.safe_load(block)
            article = by_file[path.name]
            assert article.id == meta["id"]
            assert article.title == meta["title"]
            assert list(article.sources) == list(meta["sources"])

    def test_every_sources_path_exists(self, corpus):
        missing = [f"{a.filename}: {src}" for a in corpus.articles
                   for src in a.sources if not (REPO / src).exists()]
        assert not missing, "sources that do not exist:\n" + "\n".join(missing)

    def test_every_relative_link_resolves(self):
        broken = []
        for path in sorted(HELP.glob("*.md")):
            for target in re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
                if re.match(r"^[a-z]+:", target):        # http:, https:, mailto:
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / file_part) if file_part else path
                if not resolved.is_file():
                    broken.append(f"{path.name} -> {target}")
                    continue
                if anchor:
                    slugs = {help_center.slugify(h) for h in re.findall(
                        r"^#{1,6}\s+(.*?)\s*$", resolved.read_text(encoding="utf-8"),
                        flags=re.MULTILINE)}
                    if anchor not in slugs:
                        broken.append(f"{path.name} -> {target} (no such heading)")
        assert not broken, "broken links:\n" + "\n".join(broken)

    def test_no_article_can_break_the_prompt_structure(self, corpus):
        """Chunks are pasted into <document> elements unescaped. An article
        containing one of the prompt's own tags could end its document early
        and put text outside the documents block."""
        tags = ("<document", "</document", "<question", "</question", "<history", "</history")
        found = [f"{a.filename}: {tag}" for a in corpus.articles
                 for tag in tags
                 if tag in a.intro or any(tag in s.body for s in a.sections)]
        assert not found, found


class TestIndex:
    def test_index_is_generated_and_current(self):
        """00-index.md is generated from the articles; hand edits or a new
        article without regenerating it fail here."""
        current = (HELP / "00-index.md").read_text(encoding="utf-8")
        assert current == build_index.render_index(HELP), (
            "docs/help-center/00-index.md is stale -- run "
            "`python -m scripts.help_center.build_index`")

    def test_index_lists_every_article_once_and_is_not_retrievable(self, corpus):
        text = (HELP / "00-index.md").read_text(encoding="utf-8")
        assert text.startswith("---\nid: index\n")
        for article in corpus.articles:
            assert text.count(f"]({article.filename})") == 1, article.filename
        assert not any(c.article_id == "index" for c in corpus.chunks)


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------


class TestChunks:
    def test_chunk_ids_are_unique_and_well_formed(self, corpus):
        ids = [c.id for c in corpus.chunks]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        assert not duplicates, duplicates
        article_ids = {a.id for a in corpus.articles}
        for chunk in corpus.chunks:
            article_id, _, slug = chunk.id.partition("#")
            assert article_id in article_ids and re.fullmatch(r"[a-z0-9_-]+", slug), chunk.id

    def test_chunk_ids_are_stable_across_loads(self, corpus):
        assert [c.id for c in help_center.load_corpus(HELP).chunks] == [c.id for c in corpus.chunks]

    def test_every_section_is_in_exactly_one_chunk(self, corpus):
        for article in corpus.articles:
            chunked = [s.slug for c in corpus.chunks if c.article_id == article.id
                       for s in c.sections]
            expected = [help_center.slugify(article.title)] if article.intro else []
            expected += [s.slug for s in article.sections]
            assert chunked == expected, article.filename

    def test_related_sections_are_not_indexed(self, corpus):
        assert not any(s.heading.lower() == "related"
                       for c in corpus.chunks for s in c.sections)

    def test_size_bounds(self, corpus):
        """Merge under ~120 tokens, split over ~700. A chunk may stay small
        only when it is its article's only chunk."""
        per_article: dict[str, int] = {}
        for chunk in corpus.chunks:
            per_article[chunk.article_id] = per_article.get(chunk.article_id, 0) + 1
        for chunk in corpus.chunks:
            if per_article[chunk.article_id] > 1:
                assert chunk.tokens >= help_center.MERGE_BELOW_TOKENS, chunk.id
            # A split part may exceed the bound only if it is one paragraph.
            for section in chunk.sections:
                if section.tokens > help_center.SPLIT_ABOVE_TOKENS:
                    assert "\n\n" not in section.body.strip(), section.slug

    def test_split_and_merge_rules_on_a_synthetic_article(self, tmp_path):
        """The real corpus has no section over 700 tokens, so the split path
        is proven on a synthetic article."""
        para = ("Word " * 200).strip() + "."          # ~250 tokens
        body = "\n\n".join([para] * 4)                  # ~1000 tokens
        (tmp_path / "01-big.md").write_text(
            "---\nid: big\ntitle: Big\naudience: customer\nlast_verified: 2026-10-10\n"
            "owner: t\nsources: [x]\n---\n\n# Big\n\nIntro line.\n\n"
            f"## How long is it?\n\n{body}\n\n## Tiny?\n\nYes.\n\n## Related\n- [x](01-big.md)\n",
            encoding="utf-8")
        chunks = help_center.load_corpus(tmp_path).chunks
        ids = [c.id for c in chunks]
        # Intro (tiny) merges forward; the long section splits; "Tiny?" merges back.
        assert ids == ["big#how-long-is-it", "big#how-long-is-it-2"], ids
        assert all(c.tokens <= help_center.SPLIT_ABOVE_TOKENS + 10 for c in chunks)
        assert [s.slug for s in chunks[0].sections] == ["big", "how-long-is-it"]
        assert [s.slug for s in chunks[-1].sections] == ["how-long-is-it-2", "tiny"]


# --------------------------------------------------------------------------
# Synonyms
# --------------------------------------------------------------------------


class TestSynonyms:
    def test_file_parses_and_groups_are_real_groups(self, corpus):
        data = yaml.safe_load((HELP / "_synonyms.yaml").read_text(encoding="utf-8"))
        groups = data["groups"]
        assert len(groups) >= 20
        assert len(corpus.synonyms) == len(groups)   # none dropped by the loader
        for group in groups:
            assert len(group) >= 2, group

    def test_no_term_is_in_two_groups(self):
        """A term in two groups would silently chain them together."""
        data = yaml.safe_load((HELP / "_synonyms.yaml").read_text(encoding="utf-8"))
        seen: dict[str, int] = {}
        clashes = []
        for index, group in enumerate(data["groups"]):
            for term in group:
                key = " ".join(help_center.normalize(str(term))) or str(term)
                if key in seen and seen[key] != index:
                    clashes.append(term)
                seen[key] = index
        assert not clashes, clashes


# --------------------------------------------------------------------------
# Drift: plan limits in article 22 == app/core/plans.py
# --------------------------------------------------------------------------


def _plan_table() -> list[dict[str, str]]:
    text = (HELP / "22-plans-limits-billing.md").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:                 # skip the |---| separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(dict(zip(header, cells)))
    return rows


def _shown(value) -> str:
    if isinstance(value, list):
        return ", ".join(value)
    if value == -1:
        return "Unlimited"
    return str(value)


class TestPlanTableDrift:
    COLUMNS = ("Plan", "Strategies", "Leads per strategy", "Sequence steps",
               "Channels", "Daily AI limit (USD)")

    def test_columns_are_the_documented_ones(self):
        assert tuple(_plan_table()[0].keys()) == self.COLUMNS

    def test_every_plan_row_equals_PLANS(self):
        expected = {
            name: {
                "Plan": name,
                "Strategies": _shown(plan["max_strategies"]),
                "Leads per strategy": _shown(plan["max_leads_per_strategy"]),
                "Sequence steps": _shown(plan["max_sequence_steps"]),
                "Channels": _shown(plan["channels"]),
                "Daily AI limit (USD)": _shown(plan["max_ai_spend_usd_per_day"]),
            }
            for name, plan in PLANS.items()
        }
        documented = {row["Plan"]: row for row in _plan_table()}
        assert set(documented) == set(expected), (
            f"plans in article 22 {sorted(documented)} != PLANS {sorted(expected)}")
        for name, row in expected.items():
            assert documented[name] == row, f"plan {name!r} drifted from app/core/plans.py"


# --------------------------------------------------------------------------
# Legacy FAQ aliases
# --------------------------------------------------------------------------


class TestLegacyAliases:
    def test_every_old_faq_id_has_an_alias(self):
        assert set(help_center.LEGACY_FAQ_ALIASES) == {e.id for e in support_kb.FAQ}

    def test_every_alias_target_exists(self, corpus):
        missing = {old: new for old, new in help_center.LEGACY_FAQ_ALIASES.items()
                   if new not in corpus.by_id}
        assert not missing, missing

    def test_resolve_citation_accepts_both_id_kinds(self):
        target = help_center.LEGACY_FAQ_ALIASES["contact-support"]
        assert help_center.resolve_citation("contact-support").id == target
        assert help_center.resolve_citation(target).id == target
        for bogus in ("made-up", "", None, 42, "contact-support#nope"):
            assert help_center.resolve_citation(bogus) is None


# --------------------------------------------------------------------------
# Deployment: the files ship, and their dependency is declared
# --------------------------------------------------------------------------


def _docker_excluded(path: str, rules: list[str]) -> bool:
    """Emulates Docker's .dockerignore matching (moby patternmatcher): rules
    apply in order, the last match wins, '!' re-includes, a rule matching a
    parent directory matches everything under it, '*' never crosses '/'."""
    def to_regex(pattern: str) -> re.Pattern:
        out = ""
        i = 0
        while i < len(pattern):
            if pattern.startswith("**", i):
                out += ".*"
                i += 2
            elif pattern[i] == "*":
                out += "[^/]*"
                i += 1
            elif pattern[i] == "?":
                out += "[^/]"
                i += 1
            else:
                out += re.escape(pattern[i])
                i += 1
        return re.compile(f"^{out}$")

    parents = path.split("/")
    candidates = ["/".join(parents[:i + 1]) for i in range(len(parents))]
    excluded = False
    for raw in rules:
        exclusion = raw.startswith("!")
        pattern = raw[1:] if exclusion else raw
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue
        regex = to_regex(pattern)
        if any(regex.match(c) for c in candidates):
            excluded = not exclusion
    return excluded


class TestShipping:
    @pytest.fixture(scope="class")
    def rules(self):
        lines = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]

    def test_help_center_is_in_the_docker_build_context(self, rules):
        for path in ARTICLES + [HELP / "00-index.md", HELP / "_synonyms.yaml"]:
            rel = path.relative_to(REPO).as_posix()
            assert not _docker_excluded(rel, rules), f"{rel} is excluded from the image"

    def test_the_rest_of_docs_and_secrets_stay_out(self, rules):
        for rel in ("docs/program/STAR_PROMPT.md", "docs/ICP.md", ".env",
                    "frontend/node_modules/x/index.js", "CLAUDE.md"):
            assert _docker_excluded(rel, rules), f"{rel} would ship in the image"

    def test_dockerfile_points_the_service_at_the_copied_directory(self):
        dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
        assert re.search(r"^ENV HELP_CENTER_DIR=/code/docs/help-center$", dockerfile,
                         flags=re.MULTILINE)
        assert "WORKDIR /code" in dockerfile and "COPY . ." in dockerfile

    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv(help_center.HELP_CENTER_DIR_ENV, str(tmp_path))
        assert help_center.help_center_dir() == tmp_path
        monkeypatch.delenv(help_center.HELP_CENTER_DIR_ENV)
        assert help_center.help_center_dir() == HELP

    def test_a_missing_directory_degrades_to_an_empty_corpus(self, monkeypatch, tmp_path):
        """Never an exception: this runs inside the support widget."""
        monkeypatch.setenv(help_center.HELP_CENTER_DIR_ENV, str(tmp_path / "nope"))
        help_center.reset_cache()
        try:
            assert help_center.get_corpus().chunks == ()
            assert help_center.retrieve("how do I connect gmail") == []
            assert help_center.mock_match("how do I connect gmail") is None
        finally:
            monkeypatch.delenv(help_center.HELP_CENTER_DIR_ENV)
            help_center.reset_cache()
        assert help_center.get_corpus().chunks

    def test_pyyaml_arrives_through_a_declared_dependency(self):
        """help_center imports yaml at runtime. It is not named in
        requirements.txt or pyproject.toml; it is installed by
        uvicorn[standard], which both declare. If either stops declaring the
        extra, or uvicorn drops pyyaml from it, the image loses yaml and the
        help center would load empty -- so pin the chain here."""
        requirements = (REPO / "requirements.txt").read_text(encoding="utf-8")
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r"^uvicorn\[standard\]", requirements, flags=re.MULTILINE)
        assert '"uvicorn[standard]' in pyproject
        extras = importlib.metadata.requires("uvicorn") or []
        assert any(r.lower().startswith("pyyaml") and "standard" in r for r in extras), extras


class TestSettings:
    def test_config_defaults_equal_the_measured_constants(self):
        """The thresholds are measured in help_center.py; config.py repeats
        them as literals (importing help_center there would load yaml at
        settings time). They must not drift apart."""
        fields = Settings.model_fields
        assert fields["support_chat_mock_min_bm25"].default == help_center.MOCK_MIN_SCORE
        assert (fields["support_chat_mock_min_heading_coverage"].default
                == help_center.MOCK_MIN_HEADING_COVERAGE)
