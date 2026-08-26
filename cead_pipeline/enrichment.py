from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def build_enrichment_outputs(root: str = ".") -> dict:
    root_path = Path(root)
    processed = root_path / "data" / "processed"
    public = root_path / "public"
    processed.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)

    config = _load_json(root_path / "config" / "cead_enrichment_v1.json", {})
    core_manifest = _load_json(processed / "manifest.json", {})
    dimensions = config.get("dimensions") or []

    monthly_path = processed / "cead_monthly_best.parquet"
    monthly = pd.read_parquet(monthly_path) if monthly_path.exists() else pd.DataFrame()

    canonical_cols = [
        "period", "year", "month", "territory_id", "commune_code",
        "commune_name", "region_code", "region_name", "crime_category",
        "crime_category_norm", "event_type", "measure", "metric", "value",
        "unit", "source_id", "ultimate_source_id", "source_tier",
        "quality_status", "score_eligible"
    ]

    if not monthly.empty:
        enriched_core = monthly.copy()
        enriched_core["event_type"] = "casos_policiales"
        enriched_core["measure"] = "frecuencia"
        enriched_core["unit"] = "count"
        enriched_core["score_eligible"] = True
        for col in canonical_cols:
            if col not in enriched_core.columns:
                enriched_core[col] = None
        enriched_core = enriched_core[canonical_cols]
        enriched_core.to_parquet(processed / "cead_enriched_core.parquet", index=False)
    else:
        enriched_core = pd.DataFrame(columns=canonical_cols)

    rows = []
    for d in dimensions:
        did = d.get("id")
        observed = 0
        if did == "casos_policiales_frecuencia":
            observed = int(len(enriched_core))
        rows.append({
            "dimension_id": did,
            "label": d.get("label"),
            "layer": d.get("layer"),
            "priority": d.get("priority"),
            "configured_status": d.get("status"),
            "refresh": d.get("refresh"),
            "score_eligible": bool(d.get("score_eligible")),
            "observed_rows": observed,
            "operational_status": "active" if observed > 0 else d.get("status"),
        })

    coverage = pd.DataFrame(rows)
    coverage.to_json(processed / "cead_enrichment_coverage.json", orient="records", force_ascii=False, indent=2)

    now = datetime.now(timezone.utc).isoformat()
    active = int((coverage["operational_status"] == "active").sum()) if not coverage.empty else 0
    total = int(len(coverage))
    priority1 = coverage[coverage["priority"] == 1] if not coverage.empty else coverage
    p1_active = int((priority1["operational_status"] == "active").sum()) if not priority1.empty else 0

    manifest = {
        "version": config.get("version", "1.0"),
        "generated_at": now,
        "refresh_policy": config.get("principles", {}),
        "core_manifest_version": core_manifest.get("version"),
        "core_latest_period": ((core_manifest.get("freshness") or {}).get("latest_period")),
        "canonical_schema": canonical_cols,
        "dimensions_total": total,
        "dimensions_active": active,
        "priority1_total": int(len(priority1)),
        "priority1_active": p1_active,
        "core_rows": int(len(enriched_core)),
        "quality_rule": "Cada capa se publica de forma independiente. Ausencia, bloqueo o lote parcial nunca equivale a cero ni reemplaza el último dato comparable bueno.",
        "layers": rows,
    }
    (processed / "cead_enrichment_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    public_payload = {
        "generated_at": now,
        "refresh_policy": manifest["refresh_policy"],
        "dimensions_total": total,
        "dimensions_active": active,
        "priority1": {"total": int(len(priority1)), "active": p1_active},
        "core_latest_period": manifest["core_latest_period"],
        "layers": rows,
    }
    (public / "enrichment.json").write_text(json.dumps(public_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
