package com.soccer.tracker.data.remote.dto

import com.soccer.tracker.data.remote.dto.live.LiveEventPayloadDto
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Compact fixture returned by list endpoints (no events timeline).
 *
 * Backend: ``FixtureSummary`` / ``FixtureDetail`` without ``live_events_cache``.
 */
@Serializable
data class FixtureDto(
    @SerialName("id") val id: Long,
    @SerialName("league_id") val leagueId: Long,
    @SerialName("season_id") val seasonId: Long,
    @SerialName("home_team_id") val homeTeamId: Long,
    @SerialName("away_team_id") val awayTeamId: Long,
    @SerialName("match_status") val matchStatus: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("home_score") val homeScore: Int? = null,
    @SerialName("away_score") val awayScore: Int? = null,
)

/**
 * Full fixture detail including the ``live_events_cache`` JSONB payload.
 *
 * Backend: ``FixtureDetail`` (returned by ``GET /fixtures/live``,
 * ``GET /fixtures/{id}``, and ``GET /fixtures/date/{date}`` with full payload).
 */
@Serializable
data class FixtureDetailDto(
    @SerialName("id") val id: Long,
    @SerialName("league_id") val leagueId: Long,
    @SerialName("season_id") val seasonId: Long,
    @SerialName("home_team_id") val homeTeamId: Long,
    @SerialName("away_team_id") val awayTeamId: Long,
    @SerialName("match_status") val matchStatus: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("home_score") val homeScore: Int? = null,
    @SerialName("away_score") val awayScore: Int? = null,
    @SerialName("live_events_cache") val liveEventsCache: LiveEventsCacheDto? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

/**
 * The ``live_events_cache`` JSONB document stored in PostgreSQL.
 */
@Serializable
data class LiveEventsCacheDto(
    @SerialName("events") val events: List<LiveEventPayloadDto> = emptyList(),
    @SerialName("statistics") val statistics: List<TeamStatisticsDto> = emptyList(),
    @SerialName("lineups") val lineups: List<LineupDto> = emptyList(),
    @SerialName("score") val score: ScoreDetailDto? = null,
    @SerialName("fixture") val fixture: FixtureMetaDto? = null,
    @SerialName("teams") val teams: TeamsCacheDto? = null,
    @SerialName("goals") val goals: GoalsCacheDto? = null,
)

@Serializable
data class TeamStatisticsDto(
    @SerialName("team") val team: TeamRefDto,
    @SerialName("statistics") val statistics: List<StatisticValueDto>,
)

@Serializable
data class TeamRefDto(
    @SerialName("id") val id: Long? = null,
    @SerialName("name") val name: String? = null,
    @SerialName("logo") val logo: String? = null,
)

@Serializable
data class StatisticValueDto(
    @SerialName("type") val type: String? = null,
    @SerialName("value") val value: kotlinx.serialization.json.JsonElement? = null,
)

@Serializable
data class LineupDto(
    @SerialName("team") val team: TeamRefDto? = null,
    @SerialName("formation") val formation: String? = null,
    @SerialName("startXI") val startXI: List<LineupPlayerDto> = emptyList(),
    @SerialName("substitutes") val substitutes: List<LineupPlayerDto> = emptyList(),
)

@Serializable
data class LineupPlayerDto(
    @SerialName("player") val player: PlayerRefDto? = null,
)

@Serializable
data class PlayerRefDto(
    @SerialName("id") val id: Long? = null,
    @SerialName("name") val name: String? = null,
    @SerialName("number") val number: Int? = null,
    @SerialName("pos") val pos: String? = null,
)

@Serializable
data class ScoreDetailDto(
    @SerialName("halftime") val halftime: ScorePairDto? = null,
    @SerialName("fulltime") val fulltime: ScorePairDto? = null,
    @SerialName("extratime") val extratime: ScorePairDto? = null,
    @SerialName("penalty") val penalty: ScorePairDto? = null,
)

@Serializable
data class ScorePairDto(
    @SerialName("home") val home: Int? = null,
    @SerialName("away") val away: Int? = null,
)

@Serializable
data class FixtureMetaDto(
    @SerialName("id") val id: Long? = null,
    @SerialName("date") val date: String? = null,
    @SerialName("status") val status: StatusDto? = null,
)

@Serializable
data class StatusDto(
    @SerialName("short") val short: String? = null,
    @SerialName("long") val long: String? = null,
    @SerialName("elapsed") val elapsed: Int? = null,
)

@Serializable
data class TeamsCacheDto(
    @SerialName("home") val home: TeamRefDto? = null,
    @SerialName("away") val away: TeamRefDto? = null,
)

@Serializable
data class GoalsCacheDto(
    @SerialName("home") val home: Int? = null,
    @SerialName("away") val away: Int? = null,
)

/** Wrapper for list responses returning ``{ "data": [...], "total": N }``. */
@Serializable
data class FixtureListResponseDto(
    @SerialName("data") val data: List<FixtureDetailDto>,
    @SerialName("total") val total: Int,
)
