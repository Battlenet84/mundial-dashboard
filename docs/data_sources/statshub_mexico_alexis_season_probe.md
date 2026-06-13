# StatsHub Mexico + Alexis Vega Probe

Snapshot: `mexico_alexis_season_probe`

Purpose: find, download, store, and validate raw StatsHub data for Mexico `team_id=4781` and Alexis Vega `player_id=815637`. No dashboard or final export was built.

## A. Mexico Results

| endpoint_name | status | rows | raw file | useful fields found | actual team performance metrics |
|---|---:|---:|---|---|---|
| `team_4781_tournaments` | cache_hit | 8 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_tournaments_20260611T221522Z.json` | tournament IDs, season IDs, competition names | no |
| `team_4781_events_finished` | cache_hit | 50 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_events_finished_20260611T221523Z.json` | event IDs, tournaments, home/away teams, venues | partial metadata only |
| `team_4781_performance` | ok | 10 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_performance_20260611T221648Z.json` | ballPossession, expectedGoals, totalShotsOnGoal, fouls, passes, totalTackle, yellowCards, redCards, accuratePasses | yes |
| `team_4781_performance_t16` | ok | 112 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_performance_t16_20260611T221615Z.json` | player rows with totalPass, accuratePass, goals, totalTackle, minutesPlayed, expectedGoals, keyPass, expectedAssists, fouls, cards, shots | player performance within Mexico context, not team totals |
| `team_4781_performance_t3328` | ok | 23 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_performance_t3328_20260611T221625Z.json` | same player-performance fields | player performance within Mexico context |
| `team_4781_performance_t3954` | cache_hit | 37 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_performance_t3954_20260611T221626Z.json` | same player-performance fields | player performance within Mexico context |
| `team_4781_statistics_t16` | error 500 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_statistics_t16_20260611T221636Z.json` | none | no |
| `event_15186710_extra_stats` | error 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/event_15186710_extra_stats_20260611T221659Z.json` | none | no |
| `event_15186490_extra_stats` | error 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/event_15186490_extra_stats_20260611T221711Z.json` | none | no |
| `event_15186710_team_4781_lineup` | ok | 11 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/event_15186710_team_4781_lineup_20260611T221721Z.json` | playerId, name, position, minutesPlayed, substitution fields | lineup only |

## B. Alexis Vega Results

| endpoint_name | status | rows | raw file | useful fields found | individual performance | player_id appears |
|---|---:|---:|---|---|---|---|
| `player_815637_profile` | cache_hit | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_profile_20260611T221524Z.json` | current team metadata, lastEvent, nextEvent, primaryUniqueTournamentId | profile only | yes |
| `player_815637_tournaments` | cache_hit | 8 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_tournaments_20260611T221721Z.json` | tournament IDs, season IDs, competition names | no | no |
| `player_815637_performance` | ok | 10 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_performance_20260611T221743Z.json` | totalPass, accuratePass, goalAssist, goals, totalTackle, wasFouled, minutesPlayed, expectedGoals, keyPass, expectedAssists, fouls, cards, shots | yes | yes |
| `player_815637_statistics` | not_json 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_statistics_20260611T221732Z.txt` | none | no | no |
| `player_815637_events` | not_json 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_events_20260611T221755Z.txt` | none | no | no |
| `player_815637_matches` | not_json 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_matches_20260611T221806Z.txt` | none | no | no |
| `team_1931_events_finished` | ok | 50 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_1931_events_finished_20260611T221817Z.json` | events, tournaments, teams, venues | context only | no |
| `team_1931_tournaments` | ok | 7 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_1931_tournaments_20260611T221827Z.json` | tournament IDs, season IDs, competition names | no | no |
| `team_1931_performance_t16753` | ok | 56 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_1931_performance_t16753_20260611T221838Z.json` | player rows with passing, goals, tackles, minutes, xG, xA, fouls, cards, shots | yes if filtered to Alexis row | yes |
| `team_1931_performance_t3328` | error 404 | 0 | `data/raw/statshub/snapshots/mexico_alexis_season_probe/team_1931_performance_t3328_20260611T221849Z.json` | none | no | no |

## C. Key Findings

- Mexico performance found: yes.
- Best Mexico team-level performance file: `team_4781_performance_20260611T221648Z.json`.
- Mexico player-performance context also exists for tournaments `16`, `3328`, and `3954`.
- Alexis Vega performance found: yes.
- Best Alexis individual performance file: `player_815637_performance_20260611T221743Z.json`.
- Alexis also appears in `team_1931_performance_t16753_20260611T221838Z.json`, but that file must be filtered to the Alexis row before use.
- Missing data: direct `/player/815637/statistics`, `/events`, and `/matches` paths returned 404 HTML; event extra-stats returned 404 JSON.
- Useful fields available include minutes, goals, assists, shots, fouls, was fouled, yellow/red cards, expected goals, expected assists, key passes, passes, tackles, possession/team statistics, and lineups.

## D. Next Step Recommendation

Next step: normalize only the confirmed useful raw files into a wide, season-style intermediate table. Keep Mexico team performance and Alexis individual performance separate.

Do not infer Alexis metrics from Mexico team totals. Use only `player_815637_performance` or rows explicitly containing `player_id=815637` / Alexis Vega.
