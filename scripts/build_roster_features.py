from __future__ import annotations

from statistics import mean

from app.db.connection import get_connection, init_db
from app.db.queries import upsert_team_roster_features


def avg(values):
    values = [v for v in values if v is not None]
    return mean(values) if values else None


def main() -> None:
    init_db()
    count = 0
    with get_connection() as conn:
        teams = conn.execute("SELECT DISTINCT provider, provider_team_id, team_name FROM players WHERE provider_team_id IS NOT NULL").fetchall()
        for team in teams:
            players = conn.execute("SELECT age, position FROM players WHERE provider = ? AND provider_team_id = ?", (team["provider"], team["provider_team_id"])).fetchall()
            ages = [row["age"] for row in players if row["age"] is not None]
            def pos_count(*names):
                return sum(1 for row in players if (row["position"] or "").upper() in names)
            def pos_age(*names):
                return avg([row["age"] for row in players if (row["position"] or "").upper() in names])
            known = {"GOALKEEPER", "DEFENDER", "MIDFIELDER", "ATTACKER", "FORWARD"}
            upsert_team_roster_features(conn, {
                "provider": team["provider"],
                "provider_team_id": team["provider_team_id"],
                "team_name": team["team_name"],
                "squad_size": len(players),
                "avg_age": avg(ages),
                "min_age": min(ages) if ages else None,
                "max_age": max(ages) if ages else None,
                "goalkeepers_count": pos_count("GOALKEEPER"),
                "defenders_count": pos_count("DEFENDER"),
                "midfielders_count": pos_count("MIDFIELDER"),
                "attackers_count": pos_count("ATTACKER", "FORWARD"),
                "unknown_position_count": sum(1 for row in players if (row["position"] or "").upper() not in known),
                "avg_age_goalkeepers": pos_age("GOALKEEPER"),
                "avg_age_defenders": pos_age("DEFENDER"),
                "avg_age_midfielders": pos_age("MIDFIELDER"),
                "avg_age_attackers": pos_age("ATTACKER", "FORWARD"),
            })
            count += 1
    print(f"Roster features recalculadas: {count}. Este comando no consume API.")


if __name__ == "__main__":
    main()

