from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os

import pandas as pd

from .bridge import fetch_snapshot, normalize, annualize
from .primary import collect_direct_year, load_catalog, probe

VERSION = "0.3.1-exp"
WEEKLY_CRON_UTC = "20 12 * * 1"

# Familias especialmente relevantes para ampliar la explotación territorial
# del IGR. Este listado es diagnóstico: no modifica ponderaciones ni salidas
# consumidas hoy por Radar Delictual / Atlas.
IGR_PRIORITY_CATEGORIES = {
    "Tráfico de sustancias",
    "Microtráfico de sustancias",
    "Elaboración o producción de sustancias",
    "Porte / posesión de armas o explosivos",
    "Comercio ilegal",
    "Abigeato",
}


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _catalog_labels(catalog: dict) -> set[str]:
    """Devuelve todas las etiquetas publicadas por el catálogo técnico CEAD."""
    labels: set[str] = set()
    for level in ("families", "groups", "subgroups"):
        labels.update(str(value) for value in (catalog.get(level) or {}).values() if value)
    return labels


def _catalog_coverage_diagnostic(monthly: pd.DataFrame, catalog: dict) -> dict:
    """Compara el espejo canónico con el catálogo CEAD completo.

    Es deliberadamente informativo. Una categoría ausente en el espejo no se
    interpreta como cero ni altera el dataset canónico.
    """
    observed = set(monthly["crime_category"].dropna().astype(str)) if not monthly.empty else set()
    configured = _catalog_labels(catalog)
    priority = sorted(IGR_PRIORITY_CATEGORIES)
    return {
        "configured_categories": len(configured),
        "observed_categories": len(observed),
        "observed": sorted(observed),
        "missing_from_canonical_bridge": sorted(configured - observed),
        "priority_igr": [
            {
                "category": category,
                "observed_in_canonical_bridge": category in observed,
                "eligible_for_direct_probe": category in configured,
            }
            for category in priority
        ],
        "rule": "missing_never_zero; diagnóstico no modifica IGR ni el backbone canónico",
    }


def _freshness(latest_period: str | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not latest_period:
        return {"latest_period": None, "months_lag": None, "status": "unknown"}
    stamp = pd.Timestamp(str(latest_period))
    months_lag = max(0, (now.year - stamp.year) * 12 + now.month - stamp.month)
    status = "current" if months_lag <= 2 else "lagging" if months_lag <= 6 else "stale"
    return {"latest_period": stamp.strftime("%Y-%m"), "months_lag": int(months_lag), "status": status}


def _merge_direct_cache(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        combined = new.copy()
    elif new.empty:
        combined = existing.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)
    if combined.empty:
        return combined
    keys = ["period", "commune_code", "crime_category_norm"]
    combined = combined.drop_duplicates(keys, keep="last")
    return combined.sort_values(["year", "month", "commune_code", "crime_category_norm"]).reset_index(drop=True)


def _best_monthly(bridge: pd.DataFrame, direct: pd.DataFrame) -> pd.DataFrame:
    if direct.empty:
        return bridge.copy()
    b = bridge.copy(); b["_rank"] = 20
    d = direct.copy(); d["_rank"] = 10
    combined = pd.concat([b, d], ignore_index=True, sort=False)
    keys = ["period", "commune_code", "crime_category_norm"]
    combined = combined.sort_values(keys + ["_rank"]).drop_duplicates(keys, keep="first")
    return combined.drop(columns=["_rank"]).sort_values(["year", "month", "commune_code", "crime_category_norm"]).reset_index(drop=True)


def _annualize_direct(direct: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if direct.empty:
        return direct.copy()
    keys = ["year", "territory_id", "commune_code", "commune_name", "region_code", "region_name", "crime_category", "crime_category_norm", "metric", "source_id", "ultimate_source_id", "source_tier", "quality_status"]
    out = direct.groupby(keys, as_index=False, dropna=False)["value"].sum(min_count=1)
    out.insert(0, "period", out["year"].astype(str))
    out["period_completeness"] = out["year"].map(lambda year: "complete" if int(year) < now.year else "ytd")
    return out


def run_pipeline(start_year: int = 2020, root: str = "."):
    root = Path(root)
    out = root / "data" / "processed"
    ev = root / "data" / "evidence"
    history = root / "data" / "history"
    pub = root / "public"
    previous_path = root / "data" / "previous_manifest.json"
    out.mkdir(parents=True, exist_ok=True); ev.mkdir(parents=True, exist_ok=True); history.mkdir(parents=True, exist_ok=True); pub.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    previous = _load_json(previous_path, {})
    official_controls = _load_json(root / "config" / "cead_2026_official_controls.json", {})
    source_registry = _load_json(root / "config" / "source_registry_v03.json", {})
    catalog = load_catalog()

    content, meta = fetch_snapshot()
    monthly, stats = normalize(content, start_year)
    if stats["communes"] < 340 or stats["max_date"] < "2025-12-01":
        raise ValueError(f"CEAD QA failed: {stats}")
    annual = annualize(monthly)
    catalog_diag = _catalog_coverage_diagnostic(monthly, catalog)

    primary = probe()
    direct_path = out / "cead_direct_monthly.parquet"
    existing_direct = pd.read_parquet(direct_path) if direct_path.exists() else pd.DataFrame()
    direct_meta = {"attempted": False, "usable": False, "cache_reused": bool(len(existing_direct)), "reason": "primary_probe_blocked_or_unavailable"}
    direct = existing_direct

    if primary.get("ok"):
        communes = monthly[["commune_code", "commune_name", "region_code", "region_name"]].drop_duplicates().to_dict("records")
        # Antes este filtro dependía de las categorías visibles en el espejo.
        # Eso impedía recuperar subgrupos válidos del catálogo CEAD que el
        # espejo no publica (p.ej. tráfico/microtráfico, comercio ilegal o
        # abigeato). El directo queda ahora habilitado para todo el catálogo,
        # pero continúa aislado del cead_annual.parquet canónico.
        allowed = _catalog_labels(catalog)
        direct_rows, direct_meta = collect_direct_year(now.year, communes, allowed)
        new_direct = pd.DataFrame(direct_rows)
        if direct_meta.get("usable") and not new_direct.empty:
            direct = _merge_direct_cache(existing_direct, new_direct)
            direct_meta["cache_reused"] = bool(len(existing_direct))
        else:
            direct = existing_direct
            direct_meta["cache_reused"] = bool(len(existing_direct))

    if not direct.empty:
        direct.to_parquet(direct_path, index=False)
        _annualize_direct(direct, now).to_parquet(out / "cead_direct_annual_ytd.parquet", index=False)
    best_monthly = _best_monthly(monthly, direct)

    # IMPORTANTE: estas salidas canónicas no cambian su semántica. En
    # particular cead_annual.parquet sigue proveniendo del espejo comparable,
    # que es el archivo consumido actualmente por Radar Delictual.
    monthly.to_parquet(out / "cead_monthly.parquet", index=False)
    annual.to_parquet(out / "cead_annual.parquet", index=False)
    best_monthly.to_parquet(out / "cead_monthly_best.parquet", index=False)

    bridge_hash = meta.get("content_sha256")
    previous_bridge_hash = ((previous.get("bridge_snapshot") or {}).get("content_sha256"))
    direct_latest = max(direct["period"].astype(str)) if not direct.empty else None
    previous_direct_latest = ((previous.get("direct_current_year") or {}).get("latest_period"))
    changed = bool(bridge_hash != previous_bridge_hash or direct_latest != previous_direct_latest)
    best_latest = max(best_monthly["period"].astype(str)) if len(best_monthly) else None
    freshness = _freshness(best_latest, now)

    canonical_backbone = "mirror_of_primary"
    current_backbone = "primary_direct" if direct_meta.get("usable") else ("primary_direct_cached" if not direct.empty and direct_latest and direct_latest > stats["max_date"][:7] else canonical_backbone)
    manifest = {
        "version": VERSION,
        "generated_at": now.isoformat(),
        "active_backbone": canonical_backbone,
        "current_monthly_backbone": current_backbone,
        "refresh_policy": {
            "cadence": "weekly",
            "cron_utc": WEEKLY_CRON_UTC,
            "manual_dispatch": True,
            "run_event": os.getenv("GITHUB_EVENT_NAME", "local"),
            "rule": "QA before publish; missing_never_zero; partial sources never replace last good comparable CEAD data."
        },
        "source_change": {"changed_vs_previous": changed, "current_bridge_sha256": bridge_hash, "previous_bridge_sha256": previous_bridge_hash, "current_direct_latest_period": direct_latest, "previous_direct_latest_period": previous_direct_latest},
        "freshness": freshness,
        "primary_probe": primary,
        "direct_current_year": direct_meta,
        "catalog_exploitation": {
            "artifact": "data/processed/cead_catalog_coverage.json",
            "canonical_igr_impact": "none",
            "priority_igr": catalog_diag["priority_igr"],
        },
        "bridge_snapshot": {**meta, **stats},
        "official_2026_controls": {
            "available": bool(official_controls),
            "source_id": official_controls.get("source_id"),
            "period": official_controls.get("period"),
            "period_end": official_controls.get("period_end"),
            "published_at": official_controls.get("published_at"),
            "artifact": "data/processed/cead_2026_official_controls.json",
            "use": "validation_control_only"
        },
        "source_registry": {
            "available": bool(source_registry),
            "version": source_registry.get("version"),
            "artifact": "data/processed/source_registry_v03.json"
        },
        "coverage": {**stats, "annual_rows": int(len(annual)), "best_monthly_rows": int(len(best_monthly)), "best_latest_period": best_latest, "direct_monthly_rows": int(len(direct))},
        "rule": "missing_never_zero"
    }

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "direct_probe.json").write_text(json.dumps(primary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "direct_collection.json").write_text(json.dumps(direct_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "cead_catalog_coverage.json").write_text(json.dumps(catalog_diag, ensure_ascii=False, indent=2), encoding="utf-8")
    monthly[["commune_code", "commune_name", "region_code", "region_name"]].drop_duplicates().to_json(out / "communes.json", orient="records", force_ascii=False, indent=2)
    monthly[["crime_category", "crime_category_norm"]].drop_duplicates().to_json(out / "catalog_observed.json", orient="records", force_ascii=False, indent=2)

    evidence_rows = [meta, primary, {"source_id": "cead_direct_collection", **direct_meta, "retrieved_at": now.isoformat()}]
    (ev / "source_evidence.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evidence_rows), encoding="utf-8")

    history_entry = {"version": VERSION, "run_date": now.strftime("%Y-%m-%d"), "generated_at": now.isoformat(), "run_event": os.getenv("GITHUB_EVENT_NAME", "local"), "changed_vs_previous": changed, "bridge_sha256": bridge_hash, "bridge_max_date": stats.get("max_date"), "best_latest_period": best_latest, "freshness": freshness, "primary_probe_ok": bool(primary.get("ok")), "direct_usable": bool(direct_meta.get("usable")), "catalog_exploitation": manifest["catalog_exploitation"], "official_2026_controls": manifest["official_2026_controls"], "coverage": manifest["coverage"]}
    (history / f"{now.strftime('%Y-%m-%d')}.json").write_text(json.dumps(history_entry, ensure_ascii=False, indent=2), encoding="utf-8")

    (pub / "data.json").write_text(json.dumps({"version": VERSION, "generated_at": manifest["generated_at"], "coverage": manifest["coverage"], "freshness": freshness, "official_2026_controls": manifest["official_2026_controls"], "source_change": manifest["source_change"], "catalog_exploitation": manifest["catalog_exploitation"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (pub / "index.html").write_text("<h1>CEAD Data Pipeline v0.3.1-exp</h1><p>Dataset técnico comunal independiente del análisis AML. La explotación ampliada del catálogo se mantiene separada del backbone canónico y no modifica el IGR productivo.</p>", encoding="utf-8")
    return manifest
