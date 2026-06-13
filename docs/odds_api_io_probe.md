# Odds-API.io probe

Probe minimo para confirmar acceso a Odds-API.io, listar deportes/bookmakers, bajar eventos de futbol y guardar odds de Bet365 para inspeccion manual.

## API key

En PowerShell, desde la raiz del repo:

```powershell
$env:ODDS_API_IO_KEY="PASTE_KEY_HERE"
```

La clave se lee solo desde `ODDS_API_IO_KEY`. No se imprime ni se guarda en snapshots.

## Comandos

Listar deportes:

```powershell
python -m scripts.probe_odds_api_io --action sports
```

Listar bookmakers:

```powershell
python -m scripts.probe_odds_api_io --action bookmakers
```

Eventos de futbol:

```powershell
python -m scripts.probe_odds_api_io --action events --sport football --limit 20
```

Eventos de futbol con filtro Bet365:

```powershell
python -m scripts.probe_odds_api_io --action events --sport football --bookmaker Bet365 --limit 20
```

Odds Bet365 para un evento:

```powershell
python -m scripts.probe_odds_api_io --action odds --event-id EVENT_ID --bookmakers Bet365
```

## Archivos generados

Raw JSON:

```text
data/raw/odds_api_io/probes/
```

CSV simple para odds reconocidas:

```text
data/processed/odds_api_io/latest_bet365_odds.csv
```

Si la estructura de odds no coincide con lo esperado, el script conserva el raw y omite la normalizacion.

## Nota Bet365

Bet365 devuelto por la API puede no equivaler necesariamente a Bet365 Argentina / `bet365.bet.ar`. Esa equivalencia se valida despues de forma manual.
