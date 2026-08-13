# CEAD Data Pipeline

Repositorio técnico independiente para adquisición, normalización, control de calidad y publicación de estadísticas CEAD.

## v0.2.0

La v0.2 incorpora actualización mensual programada, control de frescura, historial de corridas y preparación de la adquisición primaria directa.

### Programación

El workflow se ejecuta automáticamente el día 5 de cada mes a las 12:20 UTC (`20 12 5 * *`) y también puede ejecutarse manualmente mediante `workflow_dispatch`. Los `push` a `main` siguen ejecutando una validación completa para verificar cambios de código.

### Fuentes y precedencia

1. CEAD directo: se sondea en cada corrida. Si responde, se intenta descargar el año en curso a nivel comunal usando el catálogo técnico versionado.
2. Réplica pública verificada: continúa como backbone histórico mientras el endpoint CEAD directo permanezca bloqueado o no entregue cobertura suficiente.
3. Un lote directo se acepta solo con al menos 300 comunas exitosas. Un lote parcial nunca reemplaza el último dato bueno.

### Productos publicados en la rama `data`

- `data/processed/cead_monthly.parquet`: serie histórica mensual estable proveniente del backbone validado.
- `data/processed/cead_annual.parquet`: serie anual estable consumida por Radar Delictual.
- `data/processed/cead_monthly_best.parquet`: mejor serie mensual disponible, con precedencia del dato directo cuando existe.
- `data/processed/cead_direct_monthly.parquet`: cache primario mensual cuando CEAD directo está disponible.
- `data/processed/cead_direct_annual_ytd.parquet`: agregación primaria anual con indicador `period_completeness` para distinguir YTD de años completos.
- `data/processed/manifest.json`: cobertura, frescura, hashes, cambio respecto de la corrida anterior y estado de cada vía de adquisición.
- `data/history/YYYY-MM.json`: bitácora mensual de actualización.
- `data/evidence/source_evidence.jsonl`: evidencia técnica y trazabilidad.

### Reglas de calidad

La ausencia de datos nunca se interpreta como cero. Se valida esquema, cobertura comunal y fecha mínima antes de publicar. El manifiesto distingue entre una corrida ejecutada, un cambio real de fuente y la antigüedad del último período disponible.

## Separación de responsabilidades

Este repositorio administra **datos y trazabilidad**. No contiene scoring AML, homologación con el artículo 27 de la Ley 19.913 ni ponderaciones de riesgo. Esa interpretación permanece en Radar Delictual y en los sistemas consumidores.
