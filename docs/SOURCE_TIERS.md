# Contrato de fuentes v0.3

| Capa | `source_tier` | Uso permitido |
|---|---|---|
| CEAD directo | `primary_direct` | Backbone si pasa cobertura y QA |
| Mirror histórico CEAD | `mirror_of_primary` | Histórico estable y reproducible |
| Tuwün validado | `mirror_of_primary_validated` | Señal CEAD 2026 YTD por familia; nunca completar meses faltantes |
| Tuwün candidato | `candidate_mirror` | Solo QA/cuarentena |
| STOP | `auxiliary_leading_indicator` | Señal operacional adelantada separada de CEAD |

## Principios

1. Ausencia de datos ≠ cero.
2. Un año parcial no se compara directamente con años completos sin ajustar el período.
3. No se mezclan universos estadísticos distintos.
4. Toda promoción de una fuente candidata requiere controles reproducibles y evidencia de origen.
5. Un fallo de actualización no destruye el último snapshot bueno.
