# Evaluacion de StatsHub

## Que parece proveer

StatsHub parece ofrecer datos actuales orientados a apuestas y props: estadisticas de jugadores, tiros, tiros al arco, faltas, tackles, tarjetas, xG, xA, pases, tendencias, lineas, hit rates y promedios recientes.

## Datos que necesitamos

- Jugador, equipo, rival, competicion y temporada.
- Mercado o tipo de prop.
- Linea, odds, hit rate, promedio y ventana de partidos.
- Estadisticas base como shots, shots on target, fouls, tackles, cards, xG, xA y passes.
- Filas crudas preservadas para trazabilidad local.

## API o export oficial

Todavia no confirmamos un API publico, documentado o una exportacion oficial estable. Hasta confirmar eso, StatsHub no debe tratarse como fuente productiva automatizada.

## Riesgos de scraping

- Puede violar terminos de uso.
- Puede depender de HTML o endpoints internos inestables.
- Puede activar protecciones anti-bot.
- Puede romperse sin aviso.
- Puede mezclar datos cargados dinamicamente que no aparecen en HTML guardado.

## Principios seguros

- No bypassear autenticacion.
- No bypassear proteccion anti-bot.
- No usar proxies ni rotacion de IP.
- No bulk-download.
- No scraping agresivo.
- No llamadas automaticas en este hito.
- Usar solo HTML o CSV guardados manualmente por el usuario.

## Decision

StatsHub puede evaluarse como fuente potencial, pero no queda configurado como fuente productiva. Por ahora el proyecto solo soporta inspeccion local de HTML guardado e importacion manual de CSV.
