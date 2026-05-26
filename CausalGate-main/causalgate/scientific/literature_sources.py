from __future__ import annotations

"""Lightweight public scientific literature lookups.

The module uses public metadata APIs where possible and degrades safely when
network access or optional dependencies are unavailable.  It never treats search
results as validation; results are evidence candidates for CausalGate review.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import json
import xml.etree.ElementTree as ET


@dataclass
class LiteratureRecord:
    source: str
    title: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    journal: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _limit(value: Any, default: int = 5, maximum: int = 25) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(1, min(maximum, parsed))


def _get_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "CausalGate/0.1 scientific-literature-search (mailto:research@example.com)"})
    with urlopen(req, timeout=timeout) as response:  # nosec - public metadata API URL built from constants + quoted query
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str, timeout: int = 10) -> str:
    req = Request(url, headers={"User-Agent": "CausalGate/0.1 scientific-literature-search (mailto:research@example.com)"})
    with urlopen(req, timeout=timeout) as response:  # nosec - public metadata API URL built from constants + quoted query
        return response.read().decode("utf-8", errors="replace")


def _crossref(query: str, limit: int) -> List[LiteratureRecord]:
    url = f"https://api.crossref.org/works?query={quote_plus(query)}&rows={limit}&select=title,DOI,URL,published-print,published-online,container-title,author"
    data = _get_json(url)
    records: List[LiteratureRecord] = []
    for item in data.get("message", {}).get("items", [])[:limit]:
        title = " ".join(_as_list(item.get("title"))[:1])
        journal = " ".join(_as_list(item.get("container-title"))[:1])
        year_parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts") or []
        year = str(year_parts[0][0]) if year_parts and year_parts[0] else ""
        authors = []
        for author in _as_list(item.get("author"))[:8]:
            if isinstance(author, Mapping):
                name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
                if name:
                    authors.append(name)
        records.append(LiteratureRecord(source="crossref", title=title, year=year, doi=_clean_str(item.get("DOI")), url=_clean_str(item.get("URL")), journal=journal, authors=authors, raw={"doi": item.get("DOI")}))
    return records


def _openalex(query: str, limit: int) -> List[LiteratureRecord]:
    url = f"https://api.openalex.org/works?search={quote_plus(query)}&per-page={limit}"
    data = _get_json(url)
    records: List[LiteratureRecord] = []
    for item in data.get("results", [])[:limit]:
        authors = []
        for authorship in _as_list(item.get("authorships"))[:8]:
            author = authorship.get("author", {}) if isinstance(authorship, Mapping) else {}
            name = _clean_str(author.get("display_name"))
            if name:
                authors.append(name)
        host = item.get("primary_location", {}).get("source", {}) if isinstance(item.get("primary_location"), Mapping) else {}
        records.append(LiteratureRecord(
            source="openalex",
            title=_clean_str(item.get("title") or item.get("display_name")),
            year=str(item.get("publication_year") or ""),
            doi=_clean_str(str(item.get("doi") or "").replace("https://doi.org/", "")),
            url=_clean_str(item.get("id")),
            journal=_clean_str(host.get("display_name") if isinstance(host, Mapping) else ""),
            authors=authors,
            raw={"openalex_id": item.get("id")},
        ))
    return records


def _pubmed(query: str, limit: int) -> List[LiteratureRecord]:
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax={limit}&term={quote_plus(query)}"
    search = _get_json(search_url)
    ids = search.get("esearchresult", {}).get("idlist", [])[:limit]
    if not ids:
        return []
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(ids)
    summary = _get_json(summary_url)
    result = summary.get("result", {})
    records: List[LiteratureRecord] = []
    for pmid in ids:
        item = result.get(str(pmid), {})
        authors = []
        for author in _as_list(item.get("authors"))[:8]:
            if isinstance(author, Mapping) and author.get("name"):
                authors.append(str(author["name"]))
        records.append(LiteratureRecord(
            source="pubmed",
            title=_clean_str(item.get("title")),
            year=_clean_str(str(item.get("pubdate", ""))[:4]),
            doi="",
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            journal=_clean_str(item.get("fulljournalname") or item.get("source")),
            authors=authors,
            raw={"pmid": pmid},
        ))
    return records


def _arxiv(query: str, limit: int) -> List[LiteratureRecord]:
    url = f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&start=0&max_results={limit}"
    text = _get_text(url)
    root = ET.fromstring(text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    records: List[LiteratureRecord] = []
    for entry in root.findall("a:entry", ns)[:limit]:
        authors = [node.findtext("a:name", default="", namespaces=ns) for node in entry.findall("a:author", ns)]
        published = entry.findtext("a:published", default="", namespaces=ns)
        records.append(LiteratureRecord(
            source="arxiv",
            title=_clean_str(entry.findtext("a:title", default="", namespaces=ns).replace("\n", " ")),
            year=published[:4],
            doi="",
            url=_clean_str(entry.findtext("a:id", default="", namespaces=ns)),
            journal="arXiv",
            authors=[a for a in authors if a][:8],
            abstract=_clean_str(entry.findtext("a:summary", default="", namespaces=ns).replace("\n", " ")),
            raw={},
        ))
    return records


SOURCE_RUNNERS = {
    "crossref": _crossref,
    "openalex": _openalex,
    "pubmed": _pubmed,
    "arxiv": _arxiv,
}


def search_scientific_literature(payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = _clean_str(payload.get("query") or payload.get("goal") or payload.get("research_goal"))
    if not query:
        return {"ok": False, "error": {"code": "MISSING_QUERY", "message": "Provide query, goal, or research_goal."}, "records": []}
    limit = _limit(payload.get("limit"), default=5)
    sources = [_clean_str(source).lower() for source in (_as_list(payload.get("sources")) or ["crossref", "openalex", "pubmed"])]
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for source in sources:
        runner = SOURCE_RUNNERS.get(source)
        if runner is None:
            errors.append({"source": source, "error": "unknown_source"})
            continue
        try:
            records.extend(record.to_dict() for record in runner(query, limit))
        except Exception as exc:  # pragma: no cover - depends on network/public API
            errors.append({"source": source, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "ok": True,
        "query": query,
        "sources": sources,
        "records": records[: limit * max(1, len(sources))],
        "errors": errors,
        "external_evidence_quality": {
            "status": "metadata_only",
            "reason": "Public database metadata was retrieved when available. CausalGate must still assess study design, bias, reproducibility, and fit to the hypothesis before any claim upgrade.",
        },
        "guardrail": "Literature search supplies references, not proof.",
    }


__all__ = ["LiteratureRecord", "search_scientific_literature"]
