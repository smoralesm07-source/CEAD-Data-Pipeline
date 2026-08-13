from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import unicodedata

import pandas as pd

EXPECTED_COMMUNES = 345
EXPECTED_FAMILIES = 8
EXPECTED_YEAR = "2026"


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _read_csv(path: Path) -> pd.DataFrame:
    last = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(path, encoding=encoding, sep=sep)
                if df.shape[1] >= 5:
                    return df
            except Exception as exc:
                last = exc
    raise ValueError(f"No fue posible interpretar el CSV candidato: {last}")


def _pick(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for norm, original in normalized.items():
        if any(candidate in norm for candidate in candidates):
            return original
    return None


def validate_candidate(path: str | Path) -> dict:
    path = Path(path)
    raw = path.read_bytes()
    df = _read_csv(path)
    columns = [str(c) for c in df.columns]

    commune_col = _pick(columns, ("comuna", "nombre comuna"))
    region_col = _pick(columns, ("region", "nombre region"))
    family_col = _pick(columns, ("familia", "familia delito", "familia delictual"))
    year_columns = sorted([c for c in columns if re.fullmatch(r"20\d{2}", str(c).strip())])

    checks = {
        "commune_column_found": commune_col is not None,
        "region_column_found": region_col is not None,
        "family_column_found": family_col is not None,
        "year_2026_found": EXPECTED_YEAR in year_columns,
    }

    communes = int(df[commune_col].dropna().astype(str).nunique()) if commune_col else 0
    families = int(df[family_col].dropna().astype(str).nunique()) if family_col else 0
    checks["commune_coverage_345"] = communes == EXPECTED_COMMUNES
    checks["family_coverage_8"] = families == EXPECTED_FAMILIES

    if EXPECTED_YEAR in df.columns:
        y2026 = pd.to_numeric(df[EXPECTED_YEAR], errors="coerce")
        nonnull_2026 = int(y2026.notna().sum())
        positive_2026 = int((y2026.fillna(0) > 0).sum())
        total_2026 = float(y2026.sum(min_count=1)) if y2026.notna().any() else None
    else:
        nonnull_2026 = positive_2026 = 0
        total_2026 = None

    critical = [
        checks["commune_column_found"],
        checks["family_column_found"],
        checks["year_2026_found"],
        checks["commune_coverage_345"],
        checks["family_coverage_8"],
        positive_2026 > 0,
    ]
    status = "candidate_schema_pass" if all(critical) else "quarantined"

    return {
        "quality_status": status,
        "artifact": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": int(len(df)),
        "columns": columns,
        "year_columns": year_columns,
        "communes": communes,
        "families": families,
        "nonnull_2026_rows": nonnull_2026,
        "positive_2026_rows": positive_2026,
        "total_2026_unvalidated": total_2026,
        "checks": checks,
        "promotion_rule": "Schema pass is necessary but not sufficient: candidate remains outside the canonical CEAD series until overlap validation against trusted historical CEAD and official 2026 controls passes.",
    }


def validate_and_write(path: str | Path, report_path: str | Path) -> dict:
    report = validate_candidate(path)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
