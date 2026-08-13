from pathlib import Path
import json
from .bridge import fetch_snapshot, normalize, annualize
from .primary import probe


def run_pipeline(start_year=2020, root="."):
    root=Path(root); out=root/"data"/"processed"; ev=root/"data"/"evidence"; pub=root/"public"
    out.mkdir(parents=True,exist_ok=True); ev.mkdir(parents=True,exist_ok=True); pub.mkdir(parents=True,exist_ok=True)
    content,meta=fetch_snapshot(); monthly,stats=normalize(content,start_year)
    if stats["communes"]<340 or stats["max_date"]<"2025-12-01": raise ValueError(f"CEAD QA failed: {stats}")
    annual=annualize(monthly); primary=probe()
    monthly.to_parquet(out/"cead_monthly.parquet",index=False); annual.to_parquet(out/"cead_annual.parquet",index=False)
    manifest={"version":"0.1.0","active_backbone":"mirror_of_primary","primary_probe":primary,"bridge_snapshot":{**meta,**stats},"coverage":{**stats,"annual_rows":len(annual)},"rule":"missing_never_zero"}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"direct_probe.json").write_text(json.dumps(primary,ensure_ascii=False,indent=2),encoding="utf-8")
    monthly[["commune_code","commune_name","region_code","region_name"]].drop_duplicates().to_json(out/"communes.json",orient="records",force_ascii=False,indent=2)
    monthly[["crime_category","crime_category_norm"]].drop_duplicates().to_json(out/"catalog_observed.json",orient="records",force_ascii=False,indent=2)
    (ev/"source_evidence.jsonl").write_text(json.dumps(meta,ensure_ascii=False)+"\n",encoding="utf-8")
    (pub/"data.json").write_text(json.dumps(manifest["coverage"],ensure_ascii=False,indent=2),encoding="utf-8")
    (pub/"index.html").write_text("<h1>CEAD Data Pipeline</h1><p>Dataset técnico comunal independiente del análisis AML.</p>",encoding="utf-8")
    return manifest["coverage"]
