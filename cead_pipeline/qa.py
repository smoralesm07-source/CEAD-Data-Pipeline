from __future__ import annotations

EXPECTED_COMMUNES = 346
MIN_OBSERVED_COMMUNES = 340
MIN_ACCEPTABLE_DATE = "2025-12-01"


def validate(stats: dict) -> None:
    if int(stats.get("communes") or 0) < MIN_OBSERVED_COMMUNES:
        raise ValueError(f"Cobertura comunal insuficiente: {stats}")
    if not stats.get("max_date") or str(stats["max_date"]) < MIN_ACCEPTABLE_DATE:
        raise ValueError(f"Snapshot CEAD desactualizado: {stats}")


def commune_dictionary(monthly) -> list[dict]:
    return monthly[["commune_code", "commune_name", "region_code", "region_name"]].drop_duplicates().sort_values(["region_code", "commune_code"]).to_dict("records")


def observed_catalog(monthly) -> list[dict]:
    grouped = monthly.groupby(["crime_category", "crime_category_norm"], as_index=False).agg(rows=("value", "size"), min_year=("year", "min"), max_year=("year", "max"))
    return grouped.sort_values("crime_category_norm").to_dict("records")
