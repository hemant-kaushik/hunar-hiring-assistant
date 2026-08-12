"""Turning a pasted job description into people-search filters.

Rule-based on purpose. An LLM would read messy prose better, but this runs with
no extra key, no cost, no latency and no new failure mode in the demo path --
and because every extracted filter is shown to the recruiter for editing before
the search runs, a missed term costs a few seconds rather than a bad result.

The vocabulary is deliberately small and hiring-specific. It is not trying to
understand the document, only to recognise the handful of things a people
search can actually filter on.
"""

from __future__ import annotations

import re

from app.integrations.people_search.base import SearchFilters

# Skills worth searching for. Order matters only for multi-word terms, which
# are matched first so "machine learning" is not reduced to "learning".
SKILL_VOCABULARY = [
    "machine learning",
    "deep learning",
    "data engineering",
    "natural language processing",
    "computer vision",
    "product management",
    "next.js",
    "node.js",
    "ci/cd",
    "javascript",
    "typescript",
    "postgresql",
    "kubernetes",
    "tensorflow",
    "elasticsearch",
    "terraform",
    "fastapi",
    "graphql",
    "pytorch",
    "airflow",
    "django",
    "python",
    "mongodb",
    "react",
    "spark",
    "docker",
    "kafka",
    "redis",
    "mysql",
    "flask",
    "celery",
    "golang",
    "scala",
    "swift",
    "kotlin",
    "figma",
    "nlp",
    "aws",
    "gcp",
    "sql",
    "css",
    "java",
    "ruby",
    "rust",
    "php",
    "go",
    "c++",
]

TITLE_VOCABULARY = [
    "backend engineer",
    "backend developer",
    "frontend engineer",
    "frontend developer",
    "full stack engineer",
    "fullstack engineer",
    "software engineer",
    "software developer",
    "data engineer",
    "data scientist",
    "machine learning engineer",
    "devops engineer",
    "site reliability engineer",
    "mobile engineer",
    "android developer",
    "ios developer",
    "qa engineer",
    "test engineer",
    "product manager",
    "engineering manager",
    "product designer",
    "ux designer",
    "business analyst",
    "sales executive",
    "account executive",
    "customer success manager",
    "recruiter",
]

# Where the roles in this project are likely to be. A production version would
# geocode instead; this covers the demo without pulling in a location service.
LOCATION_VOCABULARY = [
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "mumbai",
    "pune",
    "delhi",
    "new delhi",
    "gurugram",
    "gurgaon",
    "noida",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "coimbatore",
    "indore",
    "chandigarh",
    "remote",
    "london",
    "singapore",
    "dubai",
    "new york",
    "san francisco",
]

SENIORITY_PATTERNS: list[tuple[str, list[str]]] = [
    ("director", [r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bhead of\b"]),
    ("manager", [r"\bmanager\b", r"\bmanaging\b", r"\bteam lead\b"]),
    ("staff", [r"\bstaff\b", r"\bprincipal\b", r"\barchitect\b"]),
    ("senior", [r"\bsenior\b", r"\bsr\.?\b", r"\blead\b"]),
    ("entry", [r"\bjunior\b", r"\bjr\.?\b", r"\bgraduate\b", r"\bfresher\b", r"\bentry.level\b"]),
]

MAX_TITLES = 3
MAX_SKILLS = 8


class ParsedJD(SearchFilters):
    """Filters plus a short note on how they were derived.

    Shown in the UI so an odd result set is explainable rather than magic.
    """

    matched_terms: list[str] = []


def parse_job_description(text: str, *, limit: int = 5) -> ParsedJD:
    lowered = f" {(text or '').lower()} "
    matched: list[str] = []

    titles = _find_phrases(lowered, TITLE_VOCABULARY, MAX_TITLES)
    skills = _find_phrases(lowered, SKILL_VOCABULARY, MAX_SKILLS)
    locations = _find_phrases(lowered, LOCATION_VOCABULARY, 2)

    seniority: list[str] = []
    for level, patterns in SENIORITY_PATTERNS:
        if any(re.search(p, lowered) for p in patterns):
            seniority.append(level)
            matched.append(level)
            break  # the most senior match wins; the list is ordered for that

    # Fall back to the first non-empty line, which is the job title far more
    # often than not, so an unusual role still searches for something.
    if not titles:
        first_line = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
        if first_line:
            titles = [re.sub(r"[^\w\s/+-]", " ", first_line).strip()[:60]]
            matched.append(f"title from first line: {titles[0]}")

    matched = [*titles, *skills, *locations, *matched]

    return ParsedJD(
        titles=titles,
        skills=skills,
        locations=[_canonical_location(loc) for loc in locations],
        seniority=seniority,
        limit=limit,
        matched_terms=_dedupe(matched),
    )


def _find_phrases(haystack: str, vocabulary: list[str], cap: int) -> list[str]:
    """Longest-first matching so 'node.js' is not also reported as a bare 'js'."""
    found: list[str] = []
    for phrase in sorted(vocabulary, key=len, reverse=True):
        if len(found) >= cap:
            break
        # Escape first: several entries contain regex-significant characters
        # like "c++", "node.js" and "ci/cd".
        pattern = r"(?<![\w])" + re.escape(phrase) + r"(?![\w])"
        if re.search(pattern, haystack):
            if not any(phrase in existing for existing in found):
                found.append(phrase)
    return found


def _canonical_location(name: str) -> str:
    """Search providers index the current spelling, not the historical one."""
    aliases = {"bangalore": "bengaluru", "gurgaon": "gurugram", "new delhi": "delhi"}
    return aliases.get(name, name)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out
