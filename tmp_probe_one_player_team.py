import json
from pathlib import Path

PLAYER_ID = "815637"
PLAYER_NAME_HINT = "alexis"
TEAM_ID = "4781"

base = Path("data/raw/statshub/snapshots/test_001")

def load_latest(pattern):
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"No encontré archivos para: {pattern}")
        return None, None
    p = files[0]
    with p.open("r", encoding="utf-8") as f:
        return p, json.load(f)

def walk(obj, path="$"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")

def scalar(v):
    return isinstance(v, (str, int, float, bool)) or v is None

print("\n=== 1) PLAYER TOURNAMENTS / SEASONS ===")
player_file, player_json = load_latest(f"player_{PLAYER_ID}_tournaments_*.json")

if player_json is not None:
    print("Archivo:", player_file)
    print("Tipo root:", type(player_json).__name__)

    if isinstance(player_json, dict):
        print("Top-level keys/tournament candidates:", list(player_json.keys())[:30])
        print("\nPrimeros torneos/temporadas detectados:")
        for tid, value in list(player_json.items())[:15]:
            print(f"\nTournament key: {tid}")
            if isinstance(value, list):
                print("  Lista len:", len(value))
                print("  Sample:", value[:3])
            elif isinstance(value, dict):
                print("  Dict keys:", list(value.keys())[:20])
                print("  Sample:", {k: value[k] for k in list(value.keys())[:5]})
            else:
                print("  Value:", value)

print("\n=== 2) TEAM PERFORMANCE RAW ===")
team_file, team_json = load_latest(f"team_{TEAM_ID}_performance_*.json")

stat_keywords = [
    "shot", "foul", "card", "tackle", "interception", "pass", "cross",
    "goal", "assist", "duel", "aerial", "offside", "save", "xg", "xa",
    "scoring", "attempt", "accurate", "won", "lost"
]

if team_json is not None:
    print("Archivo:", team_file)
    print("Tipo root:", type(team_json).__name__)
    if isinstance(team_json, dict):
        print("Top-level keys:", list(team_json.keys()))

    all_stat_keys = set()
    matches = []

    for path, d in walk(team_json):
        for k in d.keys():
            kl = str(k).lower()
            if any(w in kl for w in stat_keywords):
                all_stat_keys.add(str(k))

        ids = {
            str(d.get("id", "")),
            str(d.get("playerId", "")),
            str(d.get("player_id", "")),
            str(d.get("player_id_statshub", "")),
        }

        names = " ".join(
            str(d.get(k, ""))
            for k in ["name", "playerName", "player_name", "shortname", "shortName"]
        ).lower()

        if PLAYER_ID in ids or PLAYER_NAME_HINT in names:
            matches.append((path, d))

    print("\nCampos estadísticos encontrados en TODO el JSON:")
    for k in sorted(all_stat_keys):
        print("-", k)

    print(f"\nMatches para player_id={PLAYER_ID} / nombre contiene '{PLAYER_NAME_HINT}':", len(matches))

    for path, d in matches[:10]:
        print("\n--- MATCH ---")
        print("Path:", path)
        print("Keys:", sorted(d.keys()))

        print("Valores relevantes:")
        for k, v in d.items():
            kl = str(k).lower()
            if (
                k in ["id", "playerId", "player_id", "name", "playerName", "player_name", "shortname", "teamName", "teamId", "teamid"]
                or any(w in kl for w in stat_keywords)
            ):
                if scalar(v):
                    print(f"  {k}: {v}")
                else:
                    print(f"  {k}: {type(v).__name__}")

    if not matches:
        print("\nNo encontré al jugador dentro del performance JSON.")
        print("Esto puede significar que el endpoint trae la estructura en otra rama, que el playerId no está en ese torneo, o que necesitamos otro endpoint player-specific.")
