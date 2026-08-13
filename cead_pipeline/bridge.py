from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import requests

UPSTREAM_REPO = "bastianolea/delincuencia_chile"
UPSTREAM_PATH = "datos/procesados/cead_delincuencia_chile.parquet"
UPSTREAM_RAW = "https://raw.githubusercontent.com/bastianolea/delincuencia_chile/main/datos/procesados/cead_delincuencia_chile.parquet"
UPSTREAM_API = f"https://api.github.com/repos/{UPSTREAM_REPO}/contents/{UPSTREAM_PATH}"
EXPECTED = {"comuna", "cut_comuna", "region", "cut_region", "fecha", "delito", "delito_n"}
EXPECTED_COMMUNES = 346


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _code(value, width: int) -> str | None:
    if pd.isna(value):
        return None
    try:
        return str(int(float(value))).zfill(width)
    except Exception:
        return None


def fetch_snapshot(timeout: int = 90) -> tuple[bytes, dict]:
    meta = {"repo": UPSTREAM_REPO, "path": UPSTREAM_PATH, "source_id": "cead_community_bridge", "ultimate_source_id": "cead_estadisticas_delictuales", "source_tier": "mirror_of_primary", "license_upstream": "GPL-3.0"}
    url = UPSTREAM_RAW
    try:
        r = requests.get(UPSTREAM_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "CEAD-Data-Pipeline/0.1"}, timeout=20)
        if r.ok:
            doc = r.json()
            url = doc.get("download_url") or url
            meta.update({"upstream_blob_sha": doc.get("sha"), "upstream_size": doc.get("size")})
    except Exception:
        pass
    r = requests.get(url, headers={"User-Agent": "CEAD-Data-Pipeline/0.1"}, timeout=timeout)
    r.raise_for_status()
    content = r.content
    meta.update({"download_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "bytes": len(content), "content_sha256": hashlib.sha256(content).hexdigest()})
    return content, meta


def normalize(content: bytes, start_year: int = 2020) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_parquet(io.BytesIO(content), engine="pyarrow")
    missing = EXPECTED - set(raw.columns)
    if missing:
        raise ValueError(f"CEAD bridge schema missing columns: {sorted(missing)}")
    df = raw[["comuna", "cut_comuna", "region", "cut_region", "fecha", "delito", "delito_n"]].copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["value"] = pd.to_numeric(df["delito_n"], errors="coerce")
    df = df[df["fecha"].notna() & df["value"].notna()].copy()
    df = df[df["fecha"].dt.year >= int(start_year)].copy()
    df["year"] = df["fecha"].dt.year.astype(int)
    df["month"] = df["fecha"].dt.month.astype(int)
    df["period"] = df["fecha"].dt.strftime("%Y-%m")
    df["commune_code"] = df["cut_comuna"].map(lambda x: _code(x, 5))
    df["region_code"] = df["cut_region"].map(lambda x: _code(x, 2))
    df["commune_name"] = df["comuna"].astype(str)
    df["region_name"] = df["region"].astype(str)
    df["crime_category"] = df["delito"].astype(str)
    df["crime_category_norm"] = df["crime_category"].map(_norm)
    df = df[df["commune_code"].notna()].copy()
    df["territory_id"] = "CL-" + df["commune_code"]
    df["metric"] = "casos_policiales"
    df["source_id"] = "cead_community_bridge"
    df["ultimate_source_id"] = "cead_estadisticas_delictuales"
    df["source_tier"] = "mirror_of_primary"
    df["quality_status"] = "usable_bridge"
    cols = ["period", "year", "month", "territory_id", "commune_code", "commune_name", "region_code", "region_name", "crime_category", "crime_category_norm", "metric", "value", "source_id", "ultimate_source_id", "source_tier", "quality_status"]
    monthly = df[cols].sort_values(["year", "month", "commune_code", "crime_category_norm"]).reset_index(drop=True)
    stats = {"min_date": df["fecha"].min().date().isoformat(), "max_date": df["fecha"].max().date().isoformat(), "communes": int(monthly["commune_code"].nunique()), "expected_communes": EXPECTED_COMMUNES, "offenses": int(monthly["crime_category"].nunique()), "monthly_rows": int(len(monthly)), "years": sorted(monthly["year"].unique().tolist())}
    return monthly, stats


def annualize(monthly: pd.DataFrame) -> pd.DataFrame:
    keys = ["year", "territory_id", "commune_code", "commune_name", "region_code", "region_name", "crime_category", "crime_category_norm", "metric", "source_id", "ultimate_source_id", "source_tier", "quality_status"]
    out = monthly.groupby(keys, as_index=False, dropna=False)["value"].sum(min_count=1)
    out.insert(0, "period", out["year"].astype(str))
    return out
