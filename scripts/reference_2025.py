from __future__ import annotations

from pathlib import Path
import json
import pandas as pd

SOURCE = Path("data/processed/cead_monthly.parquet")
OUT = Path("data/processed/cead_reference_2025.json")


def main() -> None:
    df = pd.read_parquet(SOURCE)
    d = df[df["year"] == 2025].copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d[d["value"].notna()].copy()

    category = (
        d.groupby("crime_category", dropna=False)["value"]
        .sum(min_count=1)
        .sort_values(ascending=False)
    )
    commune = (
        d.groupby(["commune_code", "commune_name", "region_name"], dropna=False)["value"]
        .sum(min_count=1)
        .reset_index()
        .sort_values(["commune_code"])
    )

    payload = {
        "year": 2025,
        "source": "data/processed/cead_monthly.parquet",
        "rows": int(len(d)),
        "communes": int(d["commune_code"].nunique()),
        "categories": int(d["crime_category"].nunique()),
        "national_total": float(d["value"].sum()),
        "category_totals": {str(k): float(v) for k, v in category.items()},
        "commune_totals": [
            {
                "commune_code": str(r.commune_code),
                "commune_name": str(r.commune_name),
                "region_name": str(r.region_name),
                "value": float(r.value),
            }
            for r in commune.itertuples(index=False)
        ],
        "note": "Referencia independiente calculada desde el backbone CEAD validado del pipeline; usada para QA de mirrors candidatos 2026.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["year", "rows", "communes", "categories", "national_total"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
