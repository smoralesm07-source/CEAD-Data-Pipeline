import json
from pathlib import Path

from cead_pipeline.enrichment import build_enrichment_outputs


def test_enrichment_config_preserves_weekly_cadence():
    cfg = json.loads(Path("config/cead_enrichment_v1.json").read_text(encoding="utf-8"))
    assert cfg["principles"]["core_cadence"] == "weekly"
    assert cfg["principles"]["cron_utc"] == "20 12 * * 1"
    assert cfg["principles"]["missing_never_zero"] is True
    assert cfg["principles"]["partial_never_replaces_last_good"] is True


def test_priority_layers_are_declared():
    cfg = json.loads(Path("config/cead_enrichment_v1.json").read_text(encoding="utf-8"))
    ids = {x["id"] for x in cfg["dimensions"]}
    expected = {
        "casos_policiales_frecuencia",
        "denuncias_frecuencia",
        "detenciones_frecuencia",
        "aprehendidos_frecuencia",
        "tasas_100k",
        "ley_20000_procedimientos",
        "sexo_edad",
        "enusc",
        "historico_pre2020",
    }
    assert expected.issubset(ids)


def test_enrichment_can_publish_without_source_data(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "config" / "cead_enrichment_v1.json").write_text(
        Path("config/cead_enrichment_v1.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = build_enrichment_outputs(str(tmp_path))
    assert result["refresh_policy"]["cron_utc"] == "20 12 * * 1"
    assert result["dimensions_total"] >= 9
    assert (tmp_path / "data" / "processed" / "cead_enrichment_manifest.json").exists()
