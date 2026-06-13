from __future__ import annotations

from dataclasses import dataclass
import unicodedata


MARKET_CONTRACT_VERSION = "strict_market_taxonomy_v6"

STATUS_OK = "OK"
STATUS_REVIEW = "REVIEW"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_BLOCKED_UNVERIFIED = "BLOCKED_UNVERIFIED_MARKET"
STATUS_BLOCKED_VARIANT = "BLOCKED_MARKET_VARIANT"


@dataclass(frozen=True)
class MarketDefinition:
    market_type: str
    allowed_raw_market_names: tuple[str, ...]
    blocked_raw_market_name_patterns: tuple[str, ...]
    scope: str
    statshub_field_used: str | None
    model_status: str
    requires_player_id: bool
    requires_team_id: bool
    requires_home_and_away_team_data: bool
    supports_side: str
    notes: str


def canonical_market_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").replace("/", " ").split())


MARKET_TAXONOMY: dict[str, MarketDefinition] = {
    "player_total_shots": MarketDefinition(
        market_type="player_total_shots",
        allowed_raw_market_names=("Player Shots",),
        blocked_raw_market_name_patterns=("On Target", "Headers", "Outside Box", "Inside Box", "Free Kicks"),
        scope="player",
        statshub_field_used="total_shots",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Exact total player shots only.",
    ),
    "player_shots_on_target": MarketDefinition(
        market_type="player_shots_on_target",
        allowed_raw_market_names=("Player Shots on Target", "Player Shots On Target"),
        blocked_raw_market_name_patterns=("Outside Box", "Inside Box", "Header", "First Half"),
        scope="player",
        statshub_field_used="shots_on_target",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Exact player shots on target only.",
    ),
    "player_shots_on_target_outside_box": MarketDefinition(
        market_type="player_shots_on_target_outside_box",
        allowed_raw_market_names=("Player Shots on Target Outside Box",),
        blocked_raw_market_name_patterns=(),
        scope="player",
        statshub_field_used=None,
        model_status=STATUS_UNSUPPORTED,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Do not map into regular SOT.",
    ),
    "team_corners": MarketDefinition(
        market_type="team_corners",
        allowed_raw_market_names=("Team Corners", "Team Corners Over/Under"),
        blocked_raw_market_name_patterns=("Total Corners", "Race", "First Half"),
        scope="team",
        statshub_field_used="corners",
        model_status=STATUS_OK,
        requires_player_id=False,
        requires_team_id=True,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Team corner total only.",
    ),
    "total_corners": MarketDefinition(
        market_type="total_corners",
        allowed_raw_market_names=("Total Corners", "Alternative Corners"),
        blocked_raw_market_name_patterns=("Team Corners", "Race", "First Half"),
        scope="match",
        statshub_field_used="corners",
        model_status=STATUS_REVIEW,
        requires_player_id=False,
        requires_team_id=False,
        requires_home_and_away_team_data=True,
        supports_side="over_under",
        notes="Alternative Corners allowed only when verified as total match corners.",
    ),
    "over_under_goals": MarketDefinition(
        market_type="over_under_goals",
        allowed_raw_market_names=("Total Goals", "Goals Over/Under", "Alternative Total Goals", "Alternative Goal Line"),
        blocked_raw_market_name_patterns=("First Half", "Team Goals", "Player Goals", "Race To Goals"),
        scope="match",
        statshub_field_used="goals_for+goals_against",
        model_status=STATUS_OK,
        requires_player_id=False,
        requires_team_id=False,
        requires_home_and_away_team_data=True,
        supports_side="over_under",
        notes="Full-match total goals only.",
    ),
    "player_cards": MarketDefinition(
        market_type="player_cards",
        allowed_raw_market_names=("Player Cards", "Player To Be Booked", "Player to be Booked"),
        blocked_raw_market_name_patterns=("Card Points",),
        scope="player",
        statshub_field_used="cards",
        model_status=STATUS_REVIEW,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Yellow/red/card-points definition must be confirmed.",
    ),
    "team_cards": MarketDefinition(
        market_type="team_cards",
        allowed_raw_market_names=("Team Cards",),
        blocked_raw_market_name_patterns=("Card Points", "Booking Points"),
        scope="team",
        statshub_field_used="cards",
        model_status=STATUS_REVIEW,
        requires_player_id=False,
        requires_team_id=True,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Card counting method must be confirmed.",
    ),
    "total_cards": MarketDefinition(
        market_type="total_cards",
        allowed_raw_market_names=("Total Cards", "Match Cards"),
        blocked_raw_market_name_patterns=("Card Points", "Booking Points", "Team Cards"),
        scope="match",
        statshub_field_used="cards",
        model_status=STATUS_REVIEW,
        requires_player_id=False,
        requires_team_id=False,
        requires_home_and_away_team_data=True,
        supports_side="over_under",
        notes="Card counting method must be confirmed.",
    ),
    "player_fouls_committed": MarketDefinition(
        market_type="player_fouls_committed",
        allowed_raw_market_names=("Player Fouls Committed",),
        blocked_raw_market_name_patterns=("Fouled", "Drawn", "First Half"),
        scope="player",
        statshub_field_used="fouls",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Fouls committed BY the player only. Do NOT conflate with fouls drawn (player_fouled).",
    ),
    "player_fouled": MarketDefinition(
        market_type="player_fouled",
        allowed_raw_market_names=("Player To Be Fouled",),
        blocked_raw_market_name_patterns=("Committed", "First Half"),
        scope="player",
        statshub_field_used="was_fouled",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Fouls drawn/suffered BY the player only. Do NOT conflate with fouls committed (player_fouls_committed).",
    ),
    "player_passes": MarketDefinition(
        market_type="player_passes",
        allowed_raw_market_names=("Player Passes",),
        blocked_raw_market_name_patterns=("Key Passes", "Assists", "First Half"),
        scope="player",
        statshub_field_used="passes",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Total player passes only. Sparsity-checked at normalization (min 3 DB rows). Do NOT mix with key passes or assists.",
    ),
    "player_tackles": MarketDefinition(
        market_type="player_tackles",
        allowed_raw_market_names=("Player Tackles",),
        blocked_raw_market_name_patterns=("Team Tackles", "Match Tackles", "First Half"),
        scope="player",
        statshub_field_used="tackles",
        model_status=STATUS_OK,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="Individual player tackles only. Sparsity-checked at normalization. Do NOT mix with team_tackles or total_tackles.",
    ),
    "goalkeeper_saves": MarketDefinition(
        market_type="goalkeeper_saves",
        allowed_raw_market_names=("Goalkeeper Saves",),
        blocked_raw_market_name_patterns=("First Half",),
        scope="player",
        statshub_field_used="goalkeeper_saves",
        model_status=STATUS_REVIEW,
        requires_player_id=True,
        requires_team_id=False,
        requires_home_and_away_team_data=False,
        supports_side="over_under",
        notes="REVIEW: current pipeline uses team-level goalkeeper_saves as proxy. Per-GK historical breakdown not yet validated.",
    ),
}


def _contains_any(raw_market_name: str, patterns: tuple[str, ...]) -> str | None:
    raw_c = canonical_market_name(raw_market_name)
    for pattern in patterns:
        if canonical_market_name(pattern) in raw_c:
            return pattern
    return None


def evaluate_market_mapping(market_type: str, raw_market_name: str) -> dict[str, object]:
    definition = MARKET_TAXONOMY.get(market_type)
    if definition is None:
        return {
            "market_mapping_status": STATUS_BLOCKED_UNVERIFIED,
            "market_mapping_reason": "market_type_not_in_strict_taxonomy",
            "exact_market_match": False,
            "canonical_market_type": market_type,
            "statshub_field_used": None,
            "market_contract_version": MARKET_CONTRACT_VERSION,
            "model_uses_proxy": False,
            "field_mapping_status": "MISSING_FIELD",
            "side_line_status": "OK",
        }

    blocked = _contains_any(raw_market_name, definition.blocked_raw_market_name_patterns)
    if blocked:
        return {
            "market_mapping_status": STATUS_BLOCKED_VARIANT,
            "market_mapping_reason": f"blocked_variant:{canonical_market_name(blocked).replace(' ', '_')}",
            "exact_market_match": False,
            "canonical_market_type": definition.market_type,
            "statshub_field_used": definition.statshub_field_used,
            "market_contract_version": MARKET_CONTRACT_VERSION,
            "model_uses_proxy": False,
            "field_mapping_status": "OK" if definition.statshub_field_used else "MISSING_FIELD",
            "side_line_status": "OK",
        }

    raw_c = canonical_market_name(raw_market_name)
    allowed = {canonical_market_name(name) for name in definition.allowed_raw_market_names}
    exact = raw_c in allowed
    if not exact:
        return {
            "market_mapping_status": STATUS_BLOCKED_UNVERIFIED,
            "market_mapping_reason": "raw_market_name_not_allowlisted",
            "exact_market_match": False,
            "canonical_market_type": definition.market_type,
            "statshub_field_used": definition.statshub_field_used,
            "market_contract_version": MARKET_CONTRACT_VERSION,
            "model_uses_proxy": False,
            "field_mapping_status": "OK" if definition.statshub_field_used else "MISSING_FIELD",
            "side_line_status": "OK",
        }

    return {
        "market_mapping_status": definition.model_status,
        "market_mapping_reason": definition.notes,
        "exact_market_match": True,
        "canonical_market_type": definition.market_type,
        "statshub_field_used": definition.statshub_field_used,
        "market_contract_version": MARKET_CONTRACT_VERSION,
        "model_uses_proxy": definition.model_status != STATUS_OK,
        "field_mapping_status": "OK" if definition.statshub_field_used else "MISSING_FIELD",
        "side_line_status": "OK",
    }
