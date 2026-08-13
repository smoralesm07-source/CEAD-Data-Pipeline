# CEAD Data Pipeline

Repositorio técnico independiente para adquisición, normalización, control de calidad y publicación de estadísticas CEAD.

## v0.3.0 — reducción del rezago 2026

La v0.3 mantiene intacto el backbone mensual comparable y agrega una capa explícita para reducir el rezago 2026 sin mezclar universos estadísticos.

### Estrategia de fuentes

1. **CEAD directo (`primary_direct`)**: se sondea en cada corrida. Si vuelve a responder desde GitHub y supera QA, tiene precedencia.
2. **Mirror histórico CEAD (`mirror_of_primary`)**: mantiene la serie comunal/mensual estable hasta el último período validado disponible.
3. **Tuwün / CEAD (`candidate_mirror`)**: se registra como candidato para 2026 YTD. No se promueve hasta disponer de un artefacto descargable reproducible y superar validación de solapamiento contra CEAD 2025.
4. **CEAD oficial T1-2026 (`official_secondary_control`)**: controles oficiales agregados del primer trimestre de 2026 publicados para validar nuevas fuentes, sin completar artificialmente filas comunales.
5. **STOP Carabineros (`auxiliary_leading_indicator`)**: señal operacional más fresca, mantenida como fuente separada. Nunca rellena períodos CEAD.

### Programación

El workflow se ejecuta **semanalmente**, los lunes a las 12:20 UTC (`20 12 * * 1`), además de `workflow_dispatch` y validación por `push` a `main`. El aumento de frecuencia permite detectar con rapidez cambios en CEAD o en los mirrors sin multiplicar innecesariamente las solicitudes.

### Productos publicados en la rama `data`

- `data/processed/cead_monthly.parquet`: serie histórica mensual estable.
- `data/processed/cead_annual.parquet`: serie anual estable.
- `data/processed/cead_monthly_best.parquet`: mejor serie mensual disponible con precedencia del CEAD directo cuando sea utilizable.
- `data/processed/cead_direct_monthly.parquet`: caché primaria directa cuando existe.
- `data/processed/cead_direct_annual_ytd.parquet`: agregado YTD directo, separado de años completos.
- `data/processed/cead_2026_official_controls.json`: controles oficiales agregados T1-2026.
- `data/processed/source_registry_v03.json`: jerarquía, rol y reglas de consumo de cada fuente.
- `data/processed/manifest.json`: cobertura, frescura, hashes y estado de adquisición.
- `data/history/`: bitácora de corridas.
- `data/evidence/source_evidence.jsonl`: evidencia técnica y trazabilidad.

### Reglas de calidad

- Ausencia de datos nunca se interpreta como cero.
- Un dato 2026 parcial debe identificarse como YTD y no puede tratarse como año completo.
- Un mirror candidato no entra a la serie principal sin validación de solapamiento y cobertura.
- STOP no se concatena con CEAD.
- Una falla de actualización no elimina el último snapshot bueno.

## Estado 2026

La serie comunal/mensual histórica permanece comparable hasta diciembre de 2025 mientras la adquisición directa siga bloqueada y no exista un artefacto 2026 reproducible validado. La v0.3 incorpora desde ya controles oficiales CEAD del **primer trimestre de 2026** y deja formalizado el camino de promoción de un mirror 2026.

## Separación de responsabilidades

Este repositorio administra **datos, calidad y trazabilidad**. No contiene scoring AML, homologación con el artículo 27 de la Ley 19.913 ni ponderaciones de riesgo. Esa interpretación permanece en Radar Delictual y en los sistemas consumidores.
