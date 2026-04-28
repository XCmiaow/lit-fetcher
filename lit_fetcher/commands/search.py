"""文献搜索模块 — 支持 OpenAlex, Semantic Scholar"""

import requests
from typing import List, Dict

EMAIL = "lit-fetcher@example.com"


def search_papers(
    query: str,
    max_results: int = 20,
    year_from: int = 2018,
    source: str = "openalex",
) -> List[Dict]:
    """搜索学术论文，返回统一格式的记录列表"""
    records = []

    if source in ("openalex", "both"):
        records = _search_openalex(query, max_results, year_from)
    if source in ("semantic_scholar", "both"):
        ss_records = _search_semantic_scholar(query, max_results, year_from)
        existing = {r["doi"] for r in records if r["doi"]}
        for r in ss_records:
            if r["doi"] not in existing:
                records.append(r)

    return records


def _search_openalex(query: str, max_results: int, year_from: int) -> List[Dict]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{year_from}-01-01,type:article",
        "per-page": min(max_results, 200),
        "sort": "cited_by_count:desc",
        "mailto": EMAIL,
        "select": "id,doi,title,authorships,publication_year,cited_by_count,primary_location,open_access",
    }
    r = requests.get("https://api.openalex.org/works", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    records = []
    for w in data.get("results", []):
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        authors = [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")]
        loc = w.get("primary_location")
        journal = loc["source"]["display_name"] if (loc and loc.get("source")) else ""
        oa = w.get("open_access", {})
        records.append({
            "doi": doi,
            "title": w.get("title", ""),
            "authors": authors,
            "year": w.get("publication_year", ""),
            "journal": journal,
            "cited_by_count": w.get("cited_by_count", 0),
            "is_oa": oa.get("is_oa", False) if oa else False,
            "oa_url": oa.get("oa_url", "") if oa else "",
            "source": "openalex",
        })
    return records


def _search_semantic_scholar(query: str, max_results: int, year_from: int) -> List[Dict]:
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "year": f"{year_from}-",
        "fields": "title,authors,year,externalIds,journal,citationCount,openAccessPdf",
    }
    r = requests.get("https://api.semanticscholar.org/graph/v1/paper/search", params=params, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()

    records = []
    for p in data.get("data", []):
        doi = p.get("externalIds", {}).get("DOI", "")
        oa = p.get("openAccessPdf") or {}
        records.append({
            "doi": doi or "",
            "title": p.get("title", ""),
            "authors": [a["name"] for a in p.get("authors", [])],
            "year": str(p.get("year", "")),
            "journal": (p.get("journal") or {}).get("name", ""),
            "cited_by_count": p.get("citationCount", 0),
            "is_oa": bool(oa.get("url")),
            "oa_url": oa.get("url", ""),
            "source": "semantic_scholar",
        })
    return records
