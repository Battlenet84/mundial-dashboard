# Mundial 2026

Proyecto Python 100% local para construir una base SQLite del Mundial 2026 y validar conexiones con API-Football. El objetivo de este primer hito es preparar arquitectura, ingesta y chequeos locales. No genera recomendaciones finales de apuestas.

Todo corre localmente. No usa Supabase, cloud, backend remoto, deployment ni autenticacion.

## Regla principal: la API solo se usa con autorizacion explicita

La API tiene presupuesto limitado: 100 requests/dia y 10 requests/minuto por defecto. El proyecto esta diseñado para minimizar uso de API.

- La API nunca se llama automaticamente.
- Dashboard y modelos solo leen SQLite local.
- Los scripts API son dry-run por defecto.
- Las llamadas reales requieren `--execute`.
- Las respuestas raw JSON se guardan localmente.
- El cache evita repetir requests.
- Podemos decidir dataset por dataset que viene de API y que se carga manual.

## Configuracion

Crear entorno virtual:

```bash
python -m venv .venv
.venv\\Scripts\\activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Crear `.env` desde `.env.example`:

```bash
copy .env.example .env
```

Pegar la key real en `API_FOOTBALL_KEY`. Mantener `API_FOOTBALL_PROFILE=default` salvo que uses varias keys. No compartas la key ni la subas al repo.

Validar configuracion sin consumir API:

```bash
python -m scripts.api_budget
```

El comando muestra perfil seleccionado, si hay key configurada, limites y ledger local. Nunca imprime la key.

## Base local

La base SQLite vive en:

```text
data/mundial.db
```

Inicializar tablas:

```bash
python -m scripts.init_db
```

## Sincronizacion

Planificar antes de ejecutar:

```bash
python -m scripts.plan_data_sources
python -m scripts.plan_api_fetch --dataset players
```

Ejecutar ingesta completa en dry-run:

```bash
python -m app.ingestion.sync_all
```

Ejecutar llamadas reales solo despues de autorizacion explicita:

```bash
python -m scripts.fetch_players --execute --max-requests 10
```

Las respuestas originales se guardan como JSON bajo `data/raw/`.

Las cuotas se guardan como snapshots historicos en `odds_snapshots`; no se pisan datos anteriores.

## Health check

```bash
python -m scripts.health_check
```

Muestra conteos, ultimos syncs, proximos partidos, partidos sin cuotas, ultima actualizacion de cuotas y errores o warnings recientes.

## Presupuesto API

```bash
python -m scripts.api_budget
```

Este comando no consume API. Lee `data/api_request_ledger.json`.

## Imports manuales

Fixtures desde CSV local:

```bash
python -m scripts.import_manual_fixture --csv data/manual/fixture.csv
```

Columnas esperadas:

```text
date_utc,round,group_name,home_team_name,away_team_name,venue_name,venue_city
```

Equipos desde CSV local:

```bash
python -m scripts.import_manual_teams --csv data/manual/teams.csv
```

Columnas esperadas:

```text
name,country,code,logo
```

Estos comandos no consumen API y marcan `source_type = "manual"`.

## Flujo recomendado

Este flujo evita traer todo el Mundial de una vez. Primero IDs core, despues squads por fecha, despues stats historicas solo para jugadores seleccionados.

Step 1: plan core fetch

```bash
python -m scripts.plan_core_fetch
```

Step 2: ejecutar core fetch solo con aprobacion

```bash
python -m scripts.fetch_core_data --execute
```

Step 3: planificar matchday

```bash
python -m scripts.plan_matchday_fetch --date 2026-06-11 --max-players 20
```

Step 4: traer squads para equipos de esa fecha

```bash
python -m scripts.fetch_matchday_squads --date 2026-06-11 --execute
```

Step 5: planificar stats historicas

```bash
python -m scripts.plan_player_stats_fetch --date 2026-06-11 --season 2025 --max-players 20
```

Step 6: traer stats seleccionadas solo con aprobacion

```bash
python -m scripts.fetch_player_stats --date 2026-06-11 --season 2025 --max-players 20 --execute
```

Step 7: reconstruir features locales

```bash
python -m scripts.build_roster_features
python -m scripts.build_player_features --season 2025
```

Step 8: revisar estado

```bash
python -m scripts.health_check
```

No traemos todos los jugadores del Mundial de una vez. No traemos odds, injuries ni head-to-head en este hito.

## Perfiles de API

Se puede seleccionar un perfil explicito con `API_PROFILE`. No hay rotacion automatica de keys. Cada perfil usa su propio ledger local. Nunca se imprimen API keys.

## Fuentes externas gratuitas/manuales

API-Football free no alcanza para la temporada actual. Para datos actuales podemos usar CSVs descargados manualmente desde Kaggle, GitHub, datasets derivados de FBref, Transfermarkt, FPL u otras fuentes similares.

No se descarga ni scrapea nada automaticamente. No se consumen requests de API.

Flujo recomendado:

1. Poner CSV local en `data/external/`, por ejemplo:

```text
data/external/fbref/players_2025_2026.csv
```

2. Inspeccionar columnas:

```bash
python -m scripts.inspect_external_csv --csv data/external/fbref/players_2025_2026.csv --source fbref
```

3. Importar con mapping:

```bash
python -m scripts.import_external_player_stats --csv data/external/fbref/players_2025_2026.csv --source fbref --season 2025-2026
```

4. Construir features:

```bash
python -m scripts.build_external_player_features
```

5. Revisar estado:

```bash
python -m scripts.external_data_status
python -m scripts.health_check
```

Los mappings viven en `data/mappings/`. Campos faltantes quedan en `NULL`; no se inventan valores.

## Evaluacion StatsHub

StatsHub parece util para props y estadisticas actuales, pero no esta configurado como API ni fuente productiva. No se bypassea autenticacion, bot protection, proxies ni limites. En este hito solo usamos archivos guardados manualmente.

Inspeccionar HTML guardado:

```bash
python -m scripts.inspect_saved_statshub_html --html data/raw/statshub/page.html
```

Importar CSV copiado/exportado manualmente:

```bash
python -m scripts.import_statshub_table_csv --csv data/external/statshub/props.csv --market shots --competition mundial --season 2025-2026
```

Ver estado:

```bash
python -m scripts.statshub_status
```

## StatsHub como descarga puntual

StatsHub no es un API oficial del proyecto. Solo se permite evaluar descargas puntuales y controladas en modo snapshot. Todo se guarda raw y despues SQLite/modelos trabajan offline.

Reglas:

- No bulk fetch.
- No cookies, auth headers, sesiones ni tokens.
- No proxies ni bypass.
- No Playwright/Selenium.
- No live calls desde dashboard/modelos.
- Primero probar un endpoint liviano.

Mantener deshabilitado por defecto:

```text
STATSHUB_ENABLED=false
```

Planificar sin requests:

```bash
python -m scripts.plan_statshub_snapshot --date 2026-06-11
```

Si se aprueba una prueba puntual, habilitar `STATSHUB_ENABLED=true` en `.env` y ejecutar un solo endpoint:

```bash
python -m scripts.download_statshub_snapshot --snapshot-name test_001 --endpoint-name world_cup_kickoff --url "https://www.statshub.com/api/world-cup/kickoff" --execute
```

Inspeccionar e importar offline:

```bash
python -m scripts.inspect_statshub_snapshot --file PATH
python -m scripts.import_statshub_snapshot --file PATH --endpoint-name world_cup_kickoff --snapshot-name test_001
python -m scripts.statshub_snapshot_status
python -m scripts.health_check
```

## StatsHub raw data only

Por ahora solo descargamos y guardamos raw football data. No usamos PropHunter, Prop Screener, player trends, player odds, hit rates, valor de pagina ni picks.

Reglas:

- Raw JSON siempre se preserva.
- Solo se extraen IDs/nombres livianos para indexar.
- El modelo analizara despues usando SQLite/local files.
- Dashboard no llama StatsHub.

Flujo:

1. Snapshot existente:

```text
data/raw/statshub/snapshots/test_001/event_by_date_2026_06_11_20260611T204715Z.json
```

2. Extraer IDs:

```bash
python -m scripts.statshub_extract_ids --file "PATH" --endpoint-name event_by_date --csv
```

3. Importar raw snapshot:

```bash
python -m scripts.import_statshub_raw_snapshot --file "PATH" --endpoint-name event_by_date --snapshot-name test_001
```

4. Construir plan raw:

```bash
python -m scripts.build_statshub_raw_download_plan --plan-name raw_2026_06_11_stage1 --snapshot-name test_001 --from-event-file "PATH" --date 2026-06-11 --max-requests 30
```

5. Revisar plan:

```bash
python -m scripts.statshub_plan_status --plan-name raw_2026_06_11_stage1
```

6. Ejecutar solo con aprobacion y StatsHub habilitado:

```bash
python -m scripts.run_statshub_raw_download_plan --plan-name raw_2026_06_11_stage1 --max-requests 30 --execute
```

7. Chequear:

```bash
python -m scripts.statshub_raw_db_status
python -m scripts.health_check
```

Flujo simplificado World Cup como seed:

```bash
python -m scripts.build_statshub_worldcup_seed --snapshot-name test_001
python -m scripts.statshub_worldcup_data_status
python -m scripts.build_statshub_worldcup_player_season_plan --plan-name wc_player_tournaments_stage1 --snapshot-name test_001 --max-players 25 --max-requests 25
python -m scripts.statshub_plan_status --plan-name wc_player_tournaments_stage1
python -m scripts.build_statshub_worldcup_performance_plan --plan-name wc_player_performance_stage1 --snapshot-name test_001 --max-players 25 --max-requests 50
python -m scripts.statshub_plan_status --plan-name wc_player_performance_stage1
```

World Cup solo define equipos/jugadores semilla. Los datos de temporada/performance se guardan raw across all available competitions.

## Dashboard local

```bash
streamlit run app/dashboard/streamlit_app.py
```

El dashboard muestra KPIs generales, proximos partidos y cuotas disponibles. No muestra recomendaciones de apuestas.

## Tests

```bash
pytest
```
