from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cead_pipeline.core import _catalog_coverage_diagnostic, _catalog_labels, _freshness
from cead_pipeline.primary import full_catalog_payload, load_catalog, parse_cead_html, probe_payload


def test_probe_payload():
    payload = probe_payload(2025, "01101")
    assert ("anio[]", "2025") in payload
    assert ("comuna[]", "1101") in payload
    assert ("grupo[]", "401") in payload


def test_full_catalog_payload_is_neutral_and_complete():
    payload = full_catalog_payload(2026, "01101")
    assert ("familia[]", "4") in payload
    assert ("grupo[]", "401") in payload
    assert ("subgrupo[]", "40101") in payload
    assert ("subgrupo[]", "60501") in payload


def test_catalog_labels_include_igr_priorities():
    labels = _catalog_labels(load_catalog())
    for category in (
        "Tráfico de sustancias",
        "Microtráfico de sustancias",
        "Elaboración o producción de sustancias",
        "Porte / posesión de armas o explosivos",
        "Comercio ilegal",
        "Abigeato",
    ):
        assert category in labels


def test_catalog_coverage_diagnostic_does_not_treat_missing_as_zero():
    monthly = pd.DataFrame({"crime_category": ["Receptación", "Delitos asociados a drogas"]})
    diag = _catalog_coverage_diagnostic(monthly, load_catalog())
    priority = {row["category"]: row for row in diag["priority_igr"]}
    assert priority["Tráfico de sustancias"]["observed_in_canonical_bridge"] is False
    assert priority["Tráfico de sustancias"]["eligible_for_direct_probe"] is True
    assert "missing_never_zero" in diag["rule"]


def test_parser_reads_months():
    html = '<table><tr><th>Delito</th><th>Enero</th><th>Febrero</th><th>Marzo</th></tr><tr><td>Receptación</td><td>10</td><td>12</td><td>9</td></tr></table>'
    rows = parse_cead_html(html, 2026, "01101")
    assert len(rows) == 3
    assert rows[0]["period"] == "2026-01"
    assert rows[1]["value"] == 12
    assert rows[0]["source_tier"] == "primary_direct"


def test_freshness_status():
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    assert _freshness("2026-07", now)["status"] == "current"
    assert _freshness("2026-03", now)["status"] == "lagging"
    assert _freshness("2025-12", now)["status"] == "stale"


def test_workflow_is_weekly():
    text = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    assert "20 12 * * 1" in text
    assert "20 12 5 * *" not in text
