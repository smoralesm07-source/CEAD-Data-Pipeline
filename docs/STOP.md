# STOP como señal adelantada

STOP de Carabineros se incorpora en v0.3 únicamente como **fuente auxiliar**. El pipeline sondea la interfaz pública para identificar disponibilidad y la semana más reciente visible.

No se concatena con CEAD porque CEAD consolida un universo policial distinto (Carabineros + PDI, según la publicación estadística CEAD), mientras STOP corresponde a registros operacionales de Carabineros. Cualquier dataset futuro derivado de STOP deberá conservar `source_id=stop_carabineros` y un contrato de granularidad propio.

El código del probe usa navegador porque la interfaz es dinámica. La lógica se inspira en evidencia pública previa de automatización de `https://stop.carabineros.cl/`, pero evita depender de XPaths rígidos salvo como referencia de compatibilidad.
