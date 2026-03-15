#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any


QWEN_QUERY_SYSTEM_PROMPT = (
    "You rewrite user questions into compact retrieval directives for a Neo4j academic graph. "
    "Graph fields are: Author names, Article title/year, and Chunk text terms. "
    "Do NOT use boolean operators (AND/OR/NOT), parentheses, or pseudo-logic. "
    "Return exactly one line in this format: "
    "authors: <names or none> | years: <years or none> | title_terms: <terms or none> | content_terms: <terms or none>."
)
USER_SUFFIX = "Return only the single-line directive in the required format."
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")

CULTURES: list[dict[str, Any]] = [
    {
        "name": "Fremont",
        "years": (300, 1300),
        "title_terms": ["fremont", "utah", "range creek"],
        "content_terms": ["pithouse", "granary", "maize", "foraging", "ceramics", "rock art"],
        "sites": ["Range Creek", "Nine Mile Canyon", "Parowan Valley"],
        "regions": ["Great Basin", "Colorado Plateau"],
    },
    {
        "name": "Ancestral Puebloan",
        "years": (500, 1300),
        "title_terms": ["ancestral puebloan", "san juan", "chaco"],
        "content_terms": ["kiva", "masonry", "aggregation", "migration", "ceramics", "maize"],
        "sites": ["Chaco Canyon", "Mesa Verde", "Cedar Mesa"],
        "regions": ["Four Corners", "Colorado Plateau"],
    },
    {
        "name": "Hohokam",
        "years": (450, 1450),
        "title_terms": ["hohokam", "sonoran", "gila"],
        "content_terms": ["irrigation", "canal", "ballcourt", "craft production", "shell trade"],
        "sites": ["Snaketown", "Pueblo Grande", "Casa Grande"],
        "regions": ["Sonoran Desert", "Lower Gila Basin"],
    },
    {
        "name": "Mogollon",
        "years": (200, 1450),
        "title_terms": ["mogollon", "mimbres", "southwest"],
        "content_terms": ["mimbres pottery", "pithouse", "village", "exchange", "subsistence"],
        "sites": ["Mimbres Valley", "Harris Village", "Grasshopper Pueblo"],
        "regions": ["U.S. Southwest", "Mogollon Rim"],
    },
    {
        "name": "Clovis",
        "years": (13000, 12700),
        "title_terms": ["clovis", "paleoindian", "fluted point"],
        "content_terms": ["big game hunting", "mobility", "lithic technology", "colonization"],
        "sites": ["Blackwater Draw", "Gault", "Anzick"],
        "regions": ["Great Plains", "North America"],
    },
    {
        "name": "Folsom",
        "years": (12700, 12000),
        "title_terms": ["folsom", "paleoindian", "bison"],
        "content_terms": ["fluted point", "bison procurement", "kill site", "mobility"],
        "sites": ["Lindenmeier", "Folsom Site", "Agate Basin"],
        "regions": ["Great Plains", "Rocky Mountain foothills"],
    },
    {
        "name": "Hopewell",
        "years": (100, 500),
        "title_terms": ["hopewell", "middle woodland", "earthwork"],
        "content_terms": ["interaction sphere", "ritual", "mound", "craft specialization"],
        "sites": ["Newark Earthworks", "Mound City", "Seip Earthworks"],
        "regions": ["Ohio Valley", "Midwest"],
    },
    {
        "name": "Mississippian",
        "years": (800, 1600),
        "title_terms": ["mississippian", "cahokia", "platform mound"],
        "content_terms": ["chiefdom", "agriculture", "urbanism", "exchange", "ritual"],
        "sites": ["Cahokia", "Moundville", "Etowah"],
        "regions": ["Southeastern United States", "Mississippi Valley"],
    },
    {
        "name": "Maya",
        "years": (250, 900),
        "title_terms": ["maya", "classic period", "mesoamerica"],
        "content_terms": ["epigraphy", "political economy", "household archaeology", "collapse"],
        "sites": ["Tikal", "Copan", "Calakmul"],
        "regions": ["Yucatan", "Mesoamerica"],
    },
    {
        "name": "Inca",
        "years": (1400, 1533),
        "title_terms": ["inca", "andes", "tawantinsuyu"],
        "content_terms": ["state expansion", "road system", "storage", "labor tax"],
        "sites": ["Cusco", "Machu Picchu", "Ollantaytambo"],
        "regions": ["Central Andes", "Peru"],
    },
    {
        "name": "Jomon",
        "years": (14000, 300),
        "title_terms": ["jomon", "prehistoric japan", "pottery"],
        "content_terms": ["hunter gatherer", "sedentism", "shell midden", "subsistence"],
        "sites": ["Sannai Maruyama", "Torihama", "Kasori"],
        "regions": ["Japan", "Honshu"],
    },
    {
        "name": "Harappan",
        "years": (2600, 1900),
        "title_terms": ["harappan", "indus valley", "urbanism"],
        "content_terms": ["craft production", "trade", "standardization", "water management"],
        "sites": ["Mohenjo Daro", "Harappa", "Dholavira"],
        "regions": ["Indus Valley", "South Asia"],
    },
]

TOPICS: list[dict[str, Any]] = [
    {
        "label": "subsistence strategies",
        "title_terms": ["subsistence", "diet"],
        "content_terms": ["faunal", "botanical", "maize", "foraging", "agriculture"],
    },
    {
        "label": "settlement patterns",
        "title_terms": ["settlement", "village", "household"],
        "content_terms": ["mobility", "landscape", "architecture", "aggregation"],
    },
    {
        "label": "exchange networks",
        "title_terms": ["exchange", "trade", "interaction"],
        "content_terms": ["obsidian", "shell", "procurement", "regional interaction"],
    },
    {
        "label": "chronology",
        "title_terms": ["chronology", "dating", "sequence"],
        "content_terms": ["radiocarbon", "bayesian model", "temporal change"],
    },
    {
        "label": "lithic technology",
        "title_terms": ["lithic", "stone tool", "flaking"],
        "content_terms": ["core reduction", "retouch", "raw material", "knapping"],
    },
    {
        "label": "ceramic production",
        "title_terms": ["ceramic", "pottery", "style"],
        "content_terms": ["temper", "firing", "typology", "provenance"],
    },
    {
        "label": "mobility and migration",
        "title_terms": ["mobility", "migration", "movement"],
        "content_terms": ["isotope", "residential mobility", "colonization"],
    },
    {
        "label": "ritual practices",
        "title_terms": ["ritual", "ceremony", "symbolism"],
        "content_terms": ["feasting", "burial", "iconography", "public architecture"],
    },
    {
        "label": "social network structure",
        "title_terms": ["social network", "interaction network"],
        "content_terms": ["network analysis", "communities", "centrality", "connectivity"],
    },
    {
        "label": "climate and resilience",
        "title_terms": ["paleoclimate", "drought", "resilience"],
        "content_terms": ["hydrology", "adaptation", "environmental change", "risk"],
    },
]

METHODS: list[dict[str, Any]] = [
    {
        "label": "radiocarbon dating",
        "title_terms": ["radiocarbon", "14c"],
        "content_terms": ["calibration", "chronology", "dating model"],
    },
    {
        "label": "OSL dating",
        "title_terms": ["osl", "luminescence"],
        "content_terms": ["sediment", "alluvial stratigraphy", "depositional age"],
    },
    {
        "label": "stable isotope analysis",
        "title_terms": ["stable isotope", "delta13c", "delta15n"],
        "content_terms": ["diet", "mobility", "paleoenvironment"],
    },
    {
        "label": "zooarchaeology",
        "title_terms": ["zooarchaeology", "faunal analysis"],
        "content_terms": ["taxa", "butchery", "seasonality", "subsistence"],
    },
    {
        "label": "archaeobotany",
        "title_terms": ["archaeobotany", "macrobotanical", "phytolith"],
        "content_terms": ["plant use", "crop processing", "domestication"],
    },
    {
        "label": "GIS spatial analysis",
        "title_terms": ["gis", "spatial analysis", "least cost path"],
        "content_terms": ["landscape", "proximity", "terrain", "site catchment"],
    },
    {
        "label": "agent-based modeling",
        "title_terms": ["agent based model", "abm", "simulation"],
        "content_terms": ["emergence", "parameter sensitivity", "behavioral rules"],
    },
    {
        "label": "network analysis",
        "title_terms": ["network analysis", "graph", "centrality"],
        "content_terms": ["exchange", "interaction", "community structure"],
    },
]

AUTHORS: list[dict[str, Any]] = [
    {"name": "Lewis Binford", "tokens": ["binford"], "years": (1962, 2001)},
    {"name": "Colin Renfrew", "tokens": ["renfrew"], "years": (1972, 2018)},
    {"name": "Ian Hodder", "tokens": ["hodder"], "years": (1982, 2024)},
    {"name": "Kent Flannery", "tokens": ["flannery"], "years": (1967, 2013)},
    {"name": "Bruce Trigger", "tokens": ["trigger"], "years": (1968, 2006)},
    {"name": "Vere Gordon Childe", "tokens": ["childe"], "years": (1928, 1958)},
    {"name": "Timothy Earle", "tokens": ["earle"], "years": (1977, 2020)},
    {"name": "R. Lee Lyman", "tokens": ["lyman"], "years": (1980, 2022)},
    {"name": "Patricia Crown", "tokens": ["crown"], "years": (1989, 2023)},
    {"name": "Michael Schiffer", "tokens": ["schiffer"], "years": (1972, 2018)},
    {"name": "Stephen Lekson", "tokens": ["lekson"], "years": (1985, 2024)},
    {"name": "Barbara Mills", "tokens": ["mills"], "years": (1990, 2024)},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic Qwen3 query-rewrite JSONL dataset for RAG retrieval directives."
    )
    parser.add_argument("--output-jsonl", default="data/qwen3_query_rewrite_train_500.jsonl")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--summary-json", default="data/qwen3_query_rewrite_train_500_summary.json")
    return parser.parse_args()


def _tokens(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for token in TOKEN_RE.findall((value or "").lower()):
            if token in {"and", "or", "not"}:
                continue
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def _join_or_none(values: list[str]) -> str:
    return " ".join(values) if values else "none"


def _year_bounds(culture: dict[str, Any]) -> tuple[int, int]:
    raw = culture.get("years") or (0, 0)
    a = int(raw[0]) if len(raw) > 0 else 0
    b = int(raw[1]) if len(raw) > 1 else a
    return (a, b) if a <= b else (b, a)


def build_directive(
    *,
    authors: list[str] | None = None,
    years: list[int] | None = None,
    title_terms: list[str] | None = None,
    content_terms: list[str] | None = None,
) -> str:
    author_tokens = _tokens(authors or [])
    title_tokens = _tokens(title_terms or [])
    content_tokens = _tokens(content_terms or [])
    year_values = sorted(
        {
            int(y)
            for y in (years or [])
            if isinstance(y, int) and 0 <= int(y) <= 30000
        }
    )
    year_tokens = [str(y) for y in year_values]
    return (
        f"authors: {_join_or_none(author_tokens)} | "
        f"years: {_join_or_none(year_tokens)} | "
        f"title_terms: {_join_or_none(title_tokens)} | "
        f"content_terms: {_join_or_none(content_tokens)}"
    )


def _compact_query_from_directive(directive: str) -> str:
    line = directive.strip()
    parts: list[str] = []
    for field in ("authors", "years", "title_terms", "content_terms"):
        match = re.search(rf"{field}\s*:\s*([^|]+)", line, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip().lower()
        if value and value != "none":
            parts.append(value)
    return " ".join(parts).strip()


def _message_row(question: str, directive: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": QWEN_QUERY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Question:\n{question}\n\n{USER_SUFFIX}"},
            {"role": "assistant", "content": directive},
        ],
        "meta": {
            **meta,
            "task": "query_rewrite_directive",
            "query": question,
            "compact_query": _compact_query_from_directive(directive),
        },
    }


def _template_overview(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    topic = rng.choice(TOPICS)
    start, end = _year_bounds(culture)
    question = rng.choice(
        [
            f"Tell me about the {culture['name']} archaeological culture.",
            f"Give me an overview of {culture['name']} archaeology.",
            f"What should I read first on {culture['name']} culture history?",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], *culture["title_terms"]],
        content_terms=["archaeology", "culture", *culture["content_terms"], *topic["content_terms"][:2]],
    )
    return question, directive, {"template": "culture_overview", "culture": culture["name"], "topic": topic["label"]}


def _template_topic_in_culture(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    topic = rng.choice(TOPICS)
    start, end = _year_bounds(culture)
    question = rng.choice(
        [
            f"What do we know about {topic['label']} in {culture['name']} archaeology?",
            f"Find work on {topic['label']} for the {culture['name']}.",
            f"How is {topic['label']} discussed at {culture['name']} sites?",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], *topic["title_terms"], *culture["title_terms"][:2]],
        content_terms=[*topic["content_terms"], *culture["content_terms"][:3], "archaeology"],
    )
    return question, directive, {"template": "topic_in_culture", "culture": culture["name"], "topic": topic["label"]}


def _template_method_topic(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    topic = rng.choice(TOPICS)
    method = rng.choice(METHODS)
    start, end = _year_bounds(culture)
    question = rng.choice(
        [
            f"How does {method['label']} help explain {topic['label']} in {culture['name']} research?",
            f"Find {method['label']} papers about {topic['label']} for {culture['name']}.",
            f"Which {culture['name']} studies use {method['label']} on {topic['label']}?",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], *method["title_terms"], *topic["title_terms"]],
        content_terms=[*method["content_terms"], *topic["content_terms"], "analysis"],
    )
    return question, directive, {
        "template": "method_topic",
        "culture": culture["name"],
        "topic": topic["label"],
        "method": method["label"],
    }


def _template_author_claim(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    author = rng.choice(AUTHORS)
    culture = rng.choice(CULTURES)
    topic = rng.choice(TOPICS)
    year = rng.randint(int(author["years"][0]), int(author["years"][1]))
    question = rng.choice(
        [
            f"What did {author['name']} argue in {year} about {topic['label']} in {culture['name']} research?",
            f"Summarize {author['name']}'s {year} position on {topic['label']} for {culture['name']}.",
            f"How did {author['name']} frame {topic['label']} in {year}?",
        ]
    )
    directive = build_directive(
        authors=list(author["tokens"]),
        years=[year],
        title_terms=[culture["name"], *topic["title_terms"], *author["tokens"]],
        content_terms=[*topic["content_terms"], "theory", "model", "archaeology"],
    )
    return question, directive, {
        "template": "author_claim",
        "author": author["name"],
        "year": year,
        "culture": culture["name"],
        "topic": topic["label"],
    }


def _template_compare(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    c1, c2 = rng.sample(CULTURES, 2)
    topic = rng.choice(TOPICS)
    c1_start, c1_end = _year_bounds(c1)
    c2_start, c2_end = _year_bounds(c2)
    question = rng.choice(
        [
            f"Compare {c1['name']} and {c2['name']} on {topic['label']}.",
            f"What are the differences between {c1['name']} and {c2['name']} in {topic['label']}?",
            f"Find comparative studies of {c1['name']} vs {c2['name']} for {topic['label']}.",
        ]
    )
    directive = build_directive(
        years=[c1_start, c1_end, c2_start, c2_end],
        title_terms=[c1["name"], c2["name"], *topic["title_terms"]],
        content_terms=[*topic["content_terms"], "comparison", "regional variation", "archaeology"],
    )
    return question, directive, {
        "template": "compare_cultures",
        "culture_a": c1["name"],
        "culture_b": c2["name"],
        "topic": topic["label"],
    }


def _template_site_evidence(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    site = rng.choice(culture["sites"])
    topic = rng.choice(TOPICS)
    start, end = _year_bounds(culture)
    question = rng.choice(
        [
            f"What evidence for {topic['label']} comes from {site}?",
            f"Find {culture['name']} papers discussing {topic['label']} at {site}.",
            f"How is {topic['label']} interpreted at {site} in {culture['name']} archaeology?",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], site, *topic["title_terms"]],
        content_terms=[*topic["content_terms"], *culture["content_terms"][:2], "site report"],
    )
    return question, directive, {
        "template": "site_evidence",
        "culture": culture["name"],
        "site": site,
        "topic": topic["label"],
    }


def _template_region_timespan(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    region = rng.choice(culture["regions"])
    culture_start, culture_end = _year_bounds(culture)
    start = rng.randint(culture_start, culture_end)
    end = rng.randint(start, culture_end)
    question = rng.choice(
        [
            f"I need literature on {culture['name']} in the {region} between {start} and {end}.",
            f"Find studies of {culture['name']} occupation in {region} from {start} to {end}.",
            f"What should I search for about {culture['name']} chronology in {region}, {start}-{end}?",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], region, "chronology"],
        content_terms=["chronology", "occupation", "settlement", "temporal change", "archaeology"],
    )
    return question, directive, {
        "template": "region_timespan",
        "culture": culture["name"],
        "region": region,
        "start_year": start,
        "end_year": end,
    }


def _template_quoted_phrase(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    culture = rng.choice(CULTURES)
    topic = rng.choice(TOPICS)
    start, end = _year_bounds(culture)
    phrase = rng.choice(
        [
            "household archaeology",
            "ceramic typology",
            "alluvial stratigraphy",
            "exchange network",
            "mobility strategy",
            "social network analysis",
            "ritual landscape",
        ]
    )
    question = rng.choice(
        [
            f"Can you find papers with \"{phrase}\" for {culture['name']} archaeology?",
            f"What should I search to study \"{phrase}\" in {culture['name']} sites?",
            f"Find {culture['name']} literature that uses the phrase \"{phrase}\".",
        ]
    )
    directive = build_directive(
        years=[start, end],
        title_terms=[culture["name"], phrase, *topic["title_terms"][:1]],
        content_terms=[phrase, *topic["content_terms"], "archaeology"],
    )
    return question, directive, {
        "template": "quoted_phrase",
        "culture": culture["name"],
        "phrase": phrase,
        "topic": topic["label"],
    }


def _template_author_method(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    author = rng.choice(AUTHORS)
    culture = rng.choice(CULTURES)
    method = rng.choice(METHODS)
    year = rng.randint(int(author["years"][0]), int(author["years"][1]))
    question = rng.choice(
        [
            f"Which {culture['name']} papers by {author['name']} use {method['label']}?",
            f"Find {year} era work by {author['name']} on {culture['name']} with {method['label']}.",
            f"Search terms for {author['name']} + {method['label']} in {culture['name']} archaeology?",
        ]
    )
    directive = build_directive(
        authors=list(author["tokens"]),
        years=[year],
        title_terms=[culture["name"], *method["title_terms"], *author["tokens"]],
        content_terms=[*method["content_terms"], *culture["content_terms"][:2], "archaeology"],
    )
    return question, directive, {
        "template": "author_method",
        "author": author["name"],
        "year": year,
        "culture": culture["name"],
        "method": method["label"],
    }


def _template_general_topic(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    topic = rng.choice(TOPICS)
    method = rng.choice(METHODS)
    question = rng.choice(
        [
            f"What search terms should I use for {topic['label']} in archaeology?",
            f"Help me query RAG for {topic['label']} archaeological papers.",
            f"Give me retrieval terms for {method['label']} and {topic['label']}.",
        ]
    )
    directive = build_directive(
        years=[],
        title_terms=[*topic["title_terms"], *method["title_terms"][:1]],
        content_terms=[*topic["content_terms"], *method["content_terms"], "archaeology"],
    )
    return question, directive, {"template": "general_topic", "topic": topic["label"], "method": method["label"]}


TEMPLATES: list[tuple[Any, int]] = [
    (_template_overview, 14),
    (_template_topic_in_culture, 20),
    (_template_method_topic, 16),
    (_template_author_claim, 14),
    (_template_compare, 10),
    (_template_site_evidence, 12),
    (_template_region_timespan, 8),
    (_template_quoted_phrase, 8),
    (_template_author_method, 8),
    (_template_general_topic, 6),
]


def generate_rows(count: int, seed: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("count must be at least 1")
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    seen_questions: set[str] = set()

    # Seed with the exact user example requested.
    seed_question = "Tell me about the Fremont archaeological culture."
    seed_directive = build_directive(
        years=[300, 1300],
        title_terms=["fremont", "utah", "range creek"],
        content_terms=["archaeology", "culture", "settlement", "subsistence", "maize", "foraging", "rock art"],
    )
    rows.append(
        _message_row(
            seed_question,
            seed_directive,
            {"template": "seed_fremont_example", "culture": "Fremont", "topic": "culture overview"},
        )
    )
    seen_questions.add(seed_question.lower())

    builders = [item[0] for item in TEMPLATES]
    weights = [item[1] for item in TEMPLATES]
    max_attempts = max(count * 30, 10000)
    attempts = 0
    while len(rows) < count and attempts < max_attempts:
        attempts += 1
        builder = rng.choices(builders, weights=weights, k=1)[0]
        question, directive, meta = builder(rng)
        key = question.strip().lower()
        if not key or key in seen_questions:
            continue
        seen_questions.add(key)
        rows.append(_message_row(question, directive, meta))

    if len(rows) != count:
        raise RuntimeError(f"Could only generate {len(rows)} unique rows (requested {count}).")
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    out_path = Path(args.output_jsonl).resolve()
    summary_path = Path(args.summary_json).resolve()
    rows = generate_rows(count=int(args.count), seed=int(args.seed))
    _write_jsonl(out_path, rows)

    template_counts: dict[str, int] = {}
    for row in rows:
        template = str((row.get("meta") or {}).get("template") or "unknown")
        template_counts[template] = template_counts.get(template, 0) + 1

    summary = {
        "output_jsonl": str(out_path),
        "count": len(rows),
        "seed": int(args.seed),
        "templates": template_counts,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
