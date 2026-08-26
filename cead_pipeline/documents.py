from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://cead.spd.gov.cl/centro-de-documentacion/"
DEFAULT_PAGES = list(range(1, 41)) + [70, 73, 83, 85, 104]
KEYWORDS = {
    "enusc": ["enusc", "encuesta nacional urbana de seguridad ciudadana"],
    "ley_20000_procedimientos": ["procedimientos policiales", "ley de drogas", "infraccion a la ley de drogas", "infracción a la ley de drogas"],
    "historico_delictual": ["estadisticas delictuales", "estadísticas delictuales", "dmcs", "denuncias", "detenciones"],
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _classify(title: str) -> list[str]:
    low = title.lower()
    return [key for key, terms in KEYWORDS.items() if any(term in low for term in terms)]


def _year(text: str) -> int | None:
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    return int(years[-1]) if years else None


def _load_existing(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def refresh_document_catalog(root: str = ".", pages: list[int] | None = None, pause: float = 0.12) -> dict:
    root_path = Path(root)
    out = root_path / "data" / "processed"
    evidence = root_path / "data" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    target = out / "cead_document_catalog.json"
    previous = _load_existing(target)
    pages = pages or DEFAULT_PAGES
    session = requests.Session()
    session.headers.update({"User-Agent": "CEAD-Data-Pipeline/0.4 (+public-data research)"})

    docs: dict[str, dict] = {}
    statuses = []
    for page in pages:
        url = BASE_URL if page == 1 else f"{BASE_URL}?cp={page}"
        try:
            response = session.get(url, timeout=25)
            statuses.append({"page": page, "url": url, "ok": response.ok, "http_status": response.status_code, "bytes": len(response.content)})
            if not response.ok:
                time.sleep(pause)
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a", href=True):
                title = _norm(link.get_text(" ", strip=True))
                href = link.get("href") or ""
                if not title or title.lower() in {"descargar", "ver", "más", "mas"}:
                    parent = link.parent
                    title = _norm(parent.get_text(" ", strip=True)) if parent else title
                tags = _classify(title)
                if not tags:
                    continue
                absolute = requests.compat.urljoin(url, href)
                key = hashlib.sha256(f"{title}|{absolute}".encode("utf-8")).hexdigest()[:20]
                docs[key] = {
                    "id": key,
                    "title": title,
                    "year": _year(title),
                    "url": absolute,
                    "tags": tags,
                    "source_id": "cead_centro_documentacion",
                    "source_tier": "official_primary_document",
                }
        except Exception as exc:
            statuses.append({"page": page, "url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(pause)

    now = datetime.now(timezone.utc).isoformat()
    successful_pages = sum(1 for s in statuses if s.get("ok"))
    if docs and successful_pages >= max(3, int(len(pages) * 0.25)):
        records = sorted(docs.values(), key=lambda x: ((x.get("year") or 0), x.get("title") or ""), reverse=True)
        payload = {
            "generated_at": now,
            "source_id": "cead_centro_documentacion",
            "status": "active",
            "pages_requested": len(pages),
            "pages_successful": successful_pages,
            "documents": len(records),
            "tag_counts": {tag: sum(1 for r in records if tag in r["tags"]) for tag in KEYWORDS},
            "records": records,
            "rule": "Catalog discovery only; document presence is not interpreted as a statistic.",
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        payload = previous or {
            "generated_at": now,
            "source_id": "cead_centro_documentacion",
            "status": "unavailable_no_last_good",
            "documents": 0,
            "records": [],
        }
        payload = {**payload, "last_attempt_at": now, "last_attempt_ok": False, "last_attempt_pages_successful": successful_pages}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    (evidence / "document_discovery_status.json").write_text(json.dumps({"generated_at": now, "statuses": statuses}, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
