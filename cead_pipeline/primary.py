from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PRIMARY_ENDPOINT = "https://cead.minsegpublica.gob.cl/wp-content/themes/gobcl-wp-master/data/get_estadisticas_delictuales.php"
LANDING_URL = "https://cead.minsegpublica.gob.cl/estadisticas-delictuales/"
CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "cead_catalog.json"
MONTHS = [(1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"), (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"), (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre")]
MONTH_LOOKUP = {name.lower(): number for number, name in MONTHS}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (compatible; CEAD-Data-Pipeline/0.2; public-data research)", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Accept": "text/html, */*; q=0.01", "X-Requested-With": "XMLHttpRequest", "Referer": LANDING_URL}


def _post_cut(commune_code: str) -> str:
    text = re.sub(r"\D", "", str(commune_code or ""))
    return str(int(text)) if text else ""


def _base_payload(year: int, commune_code: str) -> list[tuple[str, str]]:
    data: list[tuple[str, str]] = [("medida", "1"), ("tipoVal", "1,2"), ("anio[]", str(year))]
    data += [("trimestre[]", str(q)) for q in (4, 3, 2, 1)]
    data += [("mes[]", str(m)) for m, _ in MONTHS]
    data += [("mes_nombres[]", name) for _, name in MONTHS]
    data += [("comuna[]", _post_cut(commune_code))]
    return data


def probe_payload(year: int, commune_code: str) -> list[tuple[str, str]]:
    data = _base_payload(year, commune_code)
    data += [("familia[]", "4"), ("familia_nombres[]", "Delitos asociados a drogas"), ("grupo[]", "401"), ("grupo_nombres[]", "Crímenes y simples delitos ley de drogas")]
    for sid, name in [("40101", "Tráfico de sustancias"), ("40102", "Microtráfico de sustancias"), ("40103", "Elaboración o producción de sustancias"), ("40104", "Otras infracciones a la ley de drogas")]:
        data += [("subgrupo[]", sid), ("subgrupo_nombres[]", name)]
    data += [("seleccion", "2"), ("descarga", "false")]
    return data


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def full_catalog_payload(year: int, commune_code: str, catalog: dict | None = None) -> list[tuple[str, str]]:
    catalog = catalog or load_catalog()
    data = _base_payload(year, commune_code)
    for fid, name in (catalog.get("families") or {}).items():
        data += [("familia[]", str(fid)), ("familia_nombres[]", str(name))]
    for gid, name in (catalog.get("groups") or {}).items():
        data += [("grupo[]", str(gid)), ("grupo_nombres[]", str(name))]
    for sid, name in (catalog.get("subgroups") or {}).items():
        data += [("subgrupo[]", str(sid)), ("subgrupo_nombres[]", str(name))]
    data += [("seleccion", "2"), ("descarga", "false")]
    return data


def _post(payload: list[tuple[str, str]], timeout: int = 35) -> requests.Response:
    return requests.post(PRIMARY_ENDPOINT, data=payload, headers=headers(), timeout=timeout, allow_redirects=True)


def _num(value: str) -> int | None:
    text = re.sub(r"[^0-9-]", "", str(value or ""))
    if text in {"", "-"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_cead_html(html_text: str, year: int, commune_code: str) -> list[dict]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    out: list[dict] = []
    code = str(commune_code).zfill(5)
    for table in soup.find_all("table"):
        raw = []
        for tr in table.find_all("tr"):
            cells = [" ".join(c.get_text(" ", strip=True).split()) for c in tr.find_all(["th", "td"])]
            if cells:
                raw.append(cells)
        if not raw:
            continue
        header_idx = None
        headers_row: list[str] = []
        for i, row in enumerate(raw):
            low = [c.lower() for c in row]
            if sum(1 for month in MONTH_LOOKUP if month in low) >= 3:
                header_idx = i
                headers_row = row
                break
        if header_idx is None:
            continue
        month_cols = {i: MONTH_LOOKUP.get(str(h).strip().lower()) for i, h in enumerate(headers_row)}
        month_cols = {i: m for i, m in month_cols.items() if m}
        for row in raw[header_idx + 1 :]:
            if not row:
                continue
            label = row[0].strip()
            if not label or label.lower() in {"total", "nivel territorial"}:
                continue
            for col, month in month_cols.items():
                if col >= len(row):
                    continue
                value = _num(row[col])
                if value is None:
                    continue
                out.append({"period": f"{int(year):04d}-{int(month):02d}", "year": int(year), "month": int(month), "territory_id": f"CL-{code}", "commune_code": code, "crime_category": label, "crime_category_norm": _norm(label), "metric": "casos_policiales", "value": value, "source_id": "cead_direct_post", "ultimate_source_id": "cead_estadisticas_delictuales", "source_tier": "primary_direct", "quality_status": "usable_direct"})
    return out


def probe(year: int | None = None, commune_code: str = "01101", timeout: int = 30) -> dict:
    year = year or datetime.now().year
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        r = _post(probe_payload(year, commune_code), timeout=timeout)
        rows = parse_cead_html(r.text, year, commune_code) if r.ok else []
        periods = sorted({x["period"] for x in rows if int(x.get("value") or 0) > 0})
        return {"source_id": "cead_direct_post", "endpoint": PRIMARY_ENDPOINT, "retrieved_at": retrieved_at, "ok": bool(r.ok and rows), "http_status": r.status_code, "bytes": len(r.content), "response_sha256": hashlib.sha256(r.content).hexdigest(), "parsed_rows": len(rows), "latest_nonzero_period": periods[-1] if periods else None, "blocking_message": re.sub(r"\s+", " ", r.text[:160]).strip() if not r.ok else None, "note": "Sonda primaria sin bypass; un bloqueo no se interpreta como ausencia de delitos."}
    except Exception as exc:
        return {"source_id": "cead_direct_post", "endpoint": PRIMARY_ENDPOINT, "retrieved_at": retrieved_at, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def collect_direct_year(year: int, communes: list[dict], allowed_categories: set[str], min_pause: float = 0.45) -> tuple[list[dict], dict]:
    catalog = load_catalog()
    allowed = {_norm(x) for x in allowed_categories}
    records: list[dict] = []
    statuses: list[dict] = []
    blocked = False
    for commune in communes:
        code = str(commune.get("commune_code") or "").zfill(5)
        if len(code) != 5 or not code.isdigit() or code == "12202":
            continue
        started = time.monotonic()
        try:
            r = _post(full_catalog_payload(year, code, catalog=catalog))
            parsed = parse_cead_html(r.text, year, code) if r.ok else []
            parsed = [row for row in parsed if row.get("crime_category_norm") in allowed]
            for row in parsed:
                row.update({"commune_name": commune.get("commune_name"), "region_code": commune.get("region_code"), "region_name": commune.get("region_name")})
            records.extend(parsed)
            statuses.append({"commune_code": code, "ok": bool(r.ok and parsed), "http_status": r.status_code, "records": len(parsed)})
            if not r.ok and r.status_code in {403, 429}:
                blocked = True
                break
        except Exception as exc:
            statuses.append({"commune_code": code, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(max(0.0, min_pause - (time.monotonic() - started)))
    successful = sum(1 for status in statuses if status.get("ok"))
    periods = sorted({row["period"] for row in records})
    summary = {"attempted": True, "year": int(year), "requested_communes": len([c for c in communes if str(c.get("commune_code") or "").zfill(5) != "12202"]), "processed_communes": len(statuses), "successful_communes": successful, "records": len(records), "latest_period": periods[-1] if periods else None, "blocked": blocked, "usable": successful >= 300 and bool(records), "quality_rule": "El lote directo solo se acepta con al menos 300 comunas exitosas; un lote parcial nunca reemplaza el último dato bueno."}
    return records, summary
