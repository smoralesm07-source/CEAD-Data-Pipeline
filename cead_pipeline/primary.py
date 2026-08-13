from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

import requests

PRIMARY_ENDPOINT = "https://cead.minsegpublica.gob.cl/wp-content/themes/gobcl-wp-master/data/get_estadisticas_delictuales.php"
LANDING_URL = "https://cead.minsegpublica.gob.cl/estadisticas-delictuales/"
MONTHS = [(1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"), (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"), (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre")]


def headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (compatible; CEAD-Data-Pipeline/0.1; public-data research)", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Accept": "text/html, */*; q=0.01", "X-Requested-With": "XMLHttpRequest", "Referer": LANDING_URL}


def probe_payload(year: int, commune_code: str) -> list[tuple[str, str]]:
    text = re.sub(r"\D", "", str(commune_code or ""))
    commune = str(int(text)) if text else ""
    data: list[tuple[str, str]] = [("medida", "1"), ("tipoVal", "1,2"), ("anio[]", str(year))]
    data += [("trimestre[]", str(q)) for q in (4, 3, 2, 1)]
    data += [("mes[]", str(m)) for m, _ in MONTHS]
    data += [("mes_nombres[]", name) for _, name in MONTHS]
    data += [("comuna[]", commune), ("familia[]", "4"), ("familia_nombres[]", "Delitos asociados a drogas"), ("grupo[]", "401"), ("grupo_nombres[]", "Crímenes y simples delitos ley de drogas")]
    for sid, name in [("40101", "Tráfico de sustancias"), ("40102", "Microtráfico de sustancias"), ("40103", "Elaboración o producción de sustancias"), ("40104", "Otras infracciones a la ley de drogas")]:
        data += [("subgrupo[]", sid), ("subgrupo_nombres[]", name)]
    data += [("seleccion", "2"), ("descarga", "false")]
    return data


def probe(year: int | None = None, commune_code: str = "01101", timeout: int = 30) -> dict:
    year = year or datetime.now().year
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        r = requests.post(PRIMARY_ENDPOINT, data=probe_payload(year, commune_code), headers=headers(), timeout=timeout, allow_redirects=True)
        return {"source_id": "cead_direct_post", "endpoint": PRIMARY_ENDPOINT, "retrieved_at": retrieved_at, "ok": bool(r.ok and len(r.content) > 100), "http_status": r.status_code, "bytes": len(r.content), "response_sha256": hashlib.sha256(r.content).hexdigest(), "blocking_message": re.sub(r"\s+", " ", r.text[:160]).strip() if not r.ok else None, "note": "Sonda primaria sin bypass; un bloqueo no se interpreta como ausencia de delitos."}
    except Exception as exc:
        return {"source_id": "cead_direct_post", "endpoint": PRIMARY_ENDPOINT, "retrieved_at": retrieved_at, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
