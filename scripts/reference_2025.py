from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import unicodedata
import pandas as pd

SOURCE = Path("data/processed/cead_monthly.parquet")
OUT = Path("data/processed/cead_reference_2025.json")

FAMILY_MAP = {
    "Delitos asociados a armas": ["Delitos asociados a armas"],
    "Delitos asociados a drogas": ["Delitos asociados a drogas"],
    "Delitos contra la vida e integridad": [
        "Homicidios", "Femicidios", "Violaciones", "Abusos sexuales", "Acosos sexuales",
        "Otros delitos sexuales", "Lesiones graves o gravísimas", "Lesiones menos graves",
        "Lesiones leves", "Amenazas",
    ],
    "Robos violentos": [
        "Robos con violencia o intimidación", "Robo violento de vehículo motorizado", "Robo por sorpresa",
    ],
    "Violencia intrafamiliar": ["Violencia intrafamiliar"],
    "Delitos contra la propiedad no violentos": [
        "Robo en lugar habitado", "Robo en lugar no habitado", "Robo de vehículo motorizado",
        "Robo de objetos de o desde vehículo", "Otros robos con fuerza en las cosas", "Hurtos", "Receptación",
    ],
    "Incivilidades": [
        "Amenaza falta o riña", "Consumo de alcohol y drogas en la vía pública", "Daños", "Desórdenes públicos",
    ],
    "Otros delitos o faltas": ["Robo frustrado"],
}

FAMILY_REFERENCE_STATUS = {
    "Delitos asociados a armas": "comparable_complete",
    "Delitos asociados a drogas": "comparable_complete",
    "Delitos contra la vida e integridad": "comparable_complete",
    "Robos violentos": "comparable_complete",
    "Violencia intrafamiliar": "comparable_complete",
    "Delitos contra la propiedad no violentos": "comparable_candidate",
    "Incivilidades": "known_incomplete_backbone",
    "Otros delitos o faltas": "known_incomplete_backbone",
}


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def hash_lines(lines: list[str]) -> str:
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def vector_hash(grouped: pd.DataFrame) -> str:
    rows = sorted((norm(r.commune_name), int(round(float(r.value)))) for r in grouped.itertuples(index=False))
    return hash_lines([f"{name}|{value}\n" for name, value in rows])


def main() -> None:
    df = pd.read_parquet(SOURCE)
    d = df[df["year"] == 2025].copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d[d["value"].notna()].copy()

    category = d.groupby("crime_category", dropna=False)["value"].sum(min_count=1).sort_values(ascending=False)
    commune = d.groupby(["commune_code", "commune_name", "region_name"], dropna=False)["value"].sum(min_count=1).reset_index().sort_values(["commune_code"])
    normalized_names = sorted({norm(x) for x in d["commune_name"].dropna().astype(str)})

    family_reference = {}
    for family, categories in FAMILY_MAP.items():
        part = d[d["crime_category"].isin(categories)].copy()
        grouped = part.groupby(["commune_name"], dropna=False)["value"].sum(min_count=1).reset_index()
        family_reference[family] = {
            "reference_status": FAMILY_REFERENCE_STATUS[family],
            "categories_used": categories,
            "communes": int(grouped["commune_name"].nunique()),
            "national_total": float(grouped["value"].sum()),
            "commune_vector_sha256": vector_hash(grouped),
        }

    payload = {
        "year": 2025,
        "source": "data/processed/cead_monthly.parquet",
        "rows": int(len(d)),
        "communes": int(d["commune_code"].nunique()),
        "commune_name_set_sha256": hash_lines([f"{name}\n" for name in normalized_names]),
        "categories": int(d["crime_category"].nunique()),
        "national_total_raw_categories": float(d["value"].sum()),
        "category_totals": {str(k): float(v) for k, v in category.items()},
        "family_reference": family_reference,
        "commune_totals_raw_categories": [
            {"commune_code": str(r.commune_code), "commune_name": str(r.commune_name), "region_name": str(r.region_name), "value": float(r.value)}
            for r in commune.itertuples(index=False)
        ],
        "note": "Referencia independiente calculada desde el backbone CEAD validado. Incivilidades y Otros delitos o faltas están marcados incompletos porque el bridge histórico excluye componentes; no se usan para rechazar un mirror más completo.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"year": 2025, "communes": payload["communes"], "commune_name_set_sha256": payload["commune_name_set_sha256"], "family_reference": family_reference}, ensure_ascii=False))


if __name__ == "__main__":
    main()
