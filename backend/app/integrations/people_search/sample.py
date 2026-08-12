"""The demo people-search dataset.

Twenty fictional professionals, filtered locally so search behaves like a real
provider: titles and skills rank results, location and seniority exclude them.

Two deliberate choices about contact details:

- **No profile has a hard-coded phone number.** Inventing plausible Indian
  mobile numbers would put real strangers behind a "Reach out" button. The
  fifteen "contactable" profiles instead borrow `SAMPLE_CONTACT_PHONE` -- point
  it at a phone you control and the whole flow is demonstrable end to end. Left
  unset, they report a withheld number, which is what People Data Labs actually
  returns on its free plan.
- **Five profiles have no number at all**, so the "add a number before you can
  call anyone" path is always exercised.

Emails use example.com, which RFC 2606 reserves and which cannot route.
"""

from __future__ import annotations

from app.config import settings
from app.integrations.people_search.base import PersonResult, SearchFilters

# `contactable` decides whether a profile carries the demo phone number. The
# five without it are the ones a user has to supply a number for.
_PROFILES: list[dict] = [
    {
        "external_id": "sample-001",
        "name": "Ananya Iyer",
        "title": "Senior Backend Engineer",
        "company": "Fintech startup",
        "location": "Bengaluru, Karnataka, India",
        "skills": ["python", "fastapi", "postgresql", "aws", "docker"],
        "experience_years": 6.0,
        "seniority": ["senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-002",
        "name": "Rohan Deshpande",
        "title": "Backend Developer",
        "company": "Logistics platform",
        "location": "Pune, Maharashtra, India",
        "skills": ["python", "django", "celery", "postgresql"],
        "experience_years": 3.5,
        "seniority": ["mid"],
        "contactable": True,
    },
    {
        "external_id": "sample-003",
        "name": "Fatima Sheikh",
        "title": "Staff Software Engineer",
        "company": "Payments company",
        "location": "Hyderabad, Telangana, India",
        "skills": ["go", "kubernetes", "python", "aws", "docker"],
        "experience_years": 9.0,
        "seniority": ["staff", "senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-004",
        "name": "Karthik Raman",
        "title": "Frontend Engineer",
        "company": "Design tooling startup",
        "location": "Chennai, Tamil Nadu, India",
        "skills": ["react", "typescript", "css", "next.js"],
        "experience_years": 4.0,
        "seniority": ["mid"],
        "contactable": True,
    },
    {
        "external_id": "sample-005",
        "name": "Meera Krishnan",
        "title": "Senior Frontend Engineer",
        "company": "Healthcare SaaS",
        "location": "Bengaluru, Karnataka, India",
        "skills": ["react", "typescript", "graphql", "next.js"],
        "experience_years": 7.0,
        "seniority": ["senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-006",
        "name": "Arjun Nair",
        "title": "Full Stack Engineer",
        "company": "Edtech company",
        "location": "Kochi, Kerala, India",
        "skills": ["node.js", "react", "mongodb", "typescript"],
        "experience_years": 5.0,
        "seniority": ["mid", "senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-007",
        "name": "Sneha Kulkarni",
        "title": "Data Engineer",
        "company": "Retail analytics",
        "location": "Pune, Maharashtra, India",
        "skills": ["python", "spark", "airflow", "sql", "aws"],
        "experience_years": 5.5,
        "seniority": ["senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-008",
        "name": "Vikram Singh",
        "title": "Engineering Manager",
        "company": "Marketplace",
        "location": "Gurugram, Haryana, India",
        "skills": ["java", "kubernetes", "aws", "postgresql"],
        "experience_years": 11.0,
        "seniority": ["manager", "director"],
        "contactable": True,
    },
    {
        "external_id": "sample-009",
        "name": "Priya Venkatesh",
        "title": "Machine Learning Engineer",
        "company": "Conversational AI startup",
        "location": "Bengaluru, Karnataka, India",
        "skills": ["python", "pytorch", "nlp", "machine learning"],
        "experience_years": 4.5,
        "seniority": ["mid"],
        "contactable": True,
    },
    {
        "external_id": "sample-010",
        "name": "Aditya Bose",
        "title": "Junior Backend Developer",
        "company": "Travel startup",
        "location": "Kolkata, West Bengal, India",
        "skills": ["python", "flask", "mysql"],
        "experience_years": 1.5,
        "seniority": ["entry"],
        "contactable": True,
    },
    {
        "external_id": "sample-011",
        "name": "Neha Agarwal",
        "title": "DevOps Engineer",
        "company": "Cloud consultancy",
        "location": "Noida, Uttar Pradesh, India",
        "skills": ["kubernetes", "terraform", "aws", "python", "ci/cd"],
        "experience_years": 6.5,
        "seniority": ["senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-012",
        "name": "Sameer Qureshi",
        "title": "Product Engineer",
        "company": "B2B SaaS",
        "location": "Mumbai, Maharashtra, India",
        "skills": ["typescript", "react", "node.js", "postgresql"],
        "experience_years": 3.0,
        "seniority": ["mid"],
        "contactable": True,
    },
    {
        "external_id": "sample-013",
        "name": "Divya Menon",
        "title": "Senior Data Scientist",
        "company": "Insurance analytics",
        "location": "Bengaluru, Karnataka, India",
        "skills": ["python", "machine learning", "sql", "spark"],
        "experience_years": 8.0,
        "seniority": ["senior"],
        "contactable": True,
    },
    {
        "external_id": "sample-014",
        "name": "Harpreet Gill",
        "title": "Backend Engineer",
        "company": "Gaming studio",
        "location": "Chandigarh, India",
        "skills": ["golang", "redis", "kafka", "docker"],
        "experience_years": 4.5,
        "seniority": ["mid"],
        "contactable": True,
    },
    {
        "external_id": "sample-015",
        "name": "Ishaan Kapoor",
        "title": "Site Reliability Engineer",
        "company": "Streaming platform",
        "location": "Delhi, India",
        "skills": ["kubernetes", "terraform", "python", "aws", "ci/cd"],
        "experience_years": 7.5,
        "seniority": ["senior"],
        "contactable": True,
    },
    # ---- The five with no number on file ----
    {
        "external_id": "sample-016",
        "name": "Lakshmi Subramanian",
        "title": "Senior Backend Engineer",
        "company": "Supply chain startup",
        "location": "Chennai, Tamil Nadu, India",
        "skills": ["python", "fastapi", "postgresql", "kafka"],
        "experience_years": 6.0,
        "seniority": ["senior"],
        "contactable": False,
    },
    {
        "external_id": "sample-017",
        "name": "Tanvi Joshi",
        "title": "Frontend Developer",
        "company": "Media company",
        "location": "Mumbai, Maharashtra, India",
        "skills": ["react", "javascript", "css"],
        "experience_years": 2.5,
        "seniority": ["mid"],
        "contactable": False,
    },
    {
        "external_id": "sample-018",
        "name": "Zaid Ansari",
        "title": "Data Engineer",
        "company": "Adtech platform",
        "location": "Bengaluru, Karnataka, India",
        "skills": ["python", "airflow", "spark", "sql", "aws"],
        "experience_years": 5.0,
        "seniority": ["mid", "senior"],
        "contactable": False,
    },
    {
        "external_id": "sample-019",
        "name": "Ritika Malhotra",
        "title": "Product Manager",
        "company": "Fintech scale-up",
        "location": "Gurugram, Haryana, India",
        "skills": ["product management", "sql", "figma"],
        "experience_years": 8.5,
        "seniority": ["senior", "manager"],
        "contactable": False,
    },
    {
        "external_id": "sample-020",
        "name": "Nikhil Reddy",
        "title": "Software Engineer",
        "company": "Enterprise software",
        "location": "Hyderabad, Telangana, India",
        "skills": ["java", "spring", "mysql", "docker"],
        "experience_years": 3.5,
        "seniority": ["mid"],
        "contactable": False,
    },
]


class SampleProvider:
    name = "sample"
    label = "Sample dataset"

    async def search(self, filters: SearchFilters) -> list[PersonResult]:
        scored = []
        for profile in _PROFILES:
            score = _score(profile, filters)
            if score > 0 or filters.is_empty():
                scored.append((score, profile))

        scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
        return [_to_result(p) for _, p in scored[: filters.limit]]


def _score(profile: dict, filters: SearchFilters) -> int:
    """Rank the same way the real provider is asked to: title and skills are
    preferences, location and seniority are requirements."""
    if filters.locations and not any(
        loc.lower() in profile["location"].lower() for loc in filters.locations
    ):
        return 0
    if filters.seniority and not any(
        s.lower() in profile["seniority"] for s in filters.seniority
    ):
        return 0

    score = 0
    title = profile["title"].lower()
    for wanted in filters.titles:
        words = [w for w in wanted.lower().split() if len(w) > 2]
        if words and all(w in title for w in words):
            score += 3
        elif any(w in title for w in words):
            score += 1
    for skill in filters.skills:
        if skill.lower() in profile["skills"]:
            score += 2
    return score


def _email_for(name: str) -> str:
    return f"{name.lower().replace(' ', '.')}@example.com"


def _to_result(profile: dict) -> PersonResult:
    """Build a result, attaching the demo number only to contactable profiles."""
    demo_phone = settings.sample_contact_phone.strip()
    contactable = profile["contactable"]

    return PersonResult(
        external_id=profile["external_id"],
        name=profile["name"],
        headline=f"{profile['title']} at {profile['company']}",
        title=profile["title"],
        company=profile["company"],
        location=profile["location"],
        skills=profile["skills"],
        experience_years=profile["experience_years"],
        email=_email_for(profile["name"]),
        has_email=True,
        phone=demo_phone if (contactable and demo_phone) else None,
        # Contactable profiles without a configured demo number report the same
        # thing a real provider does on a free plan: a number exists upstream
        # but is not released.
        has_phone=contactable,
        raw={k: v for k, v in profile.items() if k not in ("external_id", "contactable")},
    )
