package com.soccer.tracker.data.remote.mapper

import com.soccer.tracker.data.remote.dto.FixtureDetailDto
import com.soccer.tracker.data.remote.dto.live.CardEventDto
import com.soccer.tracker.data.remote.dto.live.GoalEventDto
import com.soccer.tracker.data.remote.dto.live.LiveEventPayloadDto
import com.soccer.tracker.data.remote.dto.live.SubstitutionEventDto
import com.soccer.tracker.data.remote.dto.live.VarEventDto
import com.soccer.tracker.domain.model.CardEvent
import com.soccer.tracker.domain.model.CardType
import com.soccer.tracker.domain.model.Fixture
import com.soccer.tracker.domain.model.GoalEvent
import com.soccer.tracker.domain.model.LiveEvent
import com.soccer.tracker.domain.model.MatchStatus
import com.soccer.tracker.domain.model.SubstitutionEvent
import com.soccer.tracker.domain.model.Team
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Maps backend DTOs to domain models.
 *
 * Extracted as a dedicated mapper so the mapping logic is testable in isolation
 * and doesn't pollute the DTO or domain classes.
 */
object FixtureMapper {

    private val dateTimeFormatter: DateTimeFormatter = DateTimeFormatter.ISO_OFFSET_DATE_TIME

    fun FixtureDetailDto.toDomain(): Fixture {
        val cache = this.liveEventsCache

        // Extract teams from the cache if available, otherwise use IDs only
        val homeTeam = Team(
            id = homeTeamId,
            name = cache?.teams?.home?.name ?: "Home Team ($homeTeamId)",
            shortCode = null,
            logoUrl = cache?.teams?.home?.logo,
        )
        val awayTeam = Team(
            id = awayTeamId,
            name = cache?.teams?.away?.name ?: "Away Team ($awayTeamId)",
            shortCode = null,
            logoUrl = cache?.teams?.away?.logo,
        )

        // Parse formations from lineups
        val formationHome = cache?.lineups
            ?.firstOrNull { it.team?.id == homeTeamId }
            ?.formation
        val formationAway = cache?.lineups
            ?.firstOrNull { it.team?.id == awayTeamId }
            ?.formation

        // Map live events
        val liveEvents = cache?.events?.mapNotNull { it.toDomain() } ?: emptyList()

        return Fixture(
            id = id,
            leagueId = leagueId,
            seasonId = seasonId,
            homeTeam = homeTeam,
            awayTeam = awayTeam,
            matchStatus = MatchStatus.fromCode(matchStatus),
            startTime = parseDateTime(startTime),
            homeScore = homeScore,
            awayScore = awayScore,
            liveEvents = liveEvents,
            formationHome = formationHome,
            formationAway = formationAway,
        )
    }

    // ---------------------------------------------------------------
    // Private helpers
    // ---------------------------------------------------------------

    private fun parseDateTime(raw: String): LocalDateTime =
        try {
            LocalDateTime.parse(raw, dateTimeFormatter)
        } catch (_: Exception) {
            // Fallback: try parsing without zone offset
            try {
                LocalDateTime.parse(raw, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
            } catch (_: Exception) {
                LocalDateTime.now()
            }
        }

    private fun LiveEventPayloadDto.toDomain(): LiveEvent? = when (this) {
        is GoalEventDto -> GoalEvent(
            minute = time.elapsed,
            extraMinute = time.extra,
            teamId = team.id ?: 0,
            teamName = team.name ?: "",
            playerName = player?.name,
            assistPlayerName = assist?.name,
            scoreHome = 0,  // would need event-order calculation; simplified
            scoreAway = 0,
        )
        is CardEventDto -> CardEvent(
            minute = time.elapsed,
            extraMinute = time.extra,
            teamId = team.id ?: 0,
            teamName = team.name ?: "",
            playerName = player?.name,
            cardType = mapCardType(detail),
        )
        is SubstitutionEventDto -> SubstitutionEvent(
            minute = time.elapsed,
            extraMinute = time.extra,
            teamId = team.id ?: 0,
            teamName = team.name ?: "",
            playerName = player?.name,   // Player ON
            playerOffName = playerOff?.name,
        )
        is VarEventDto -> null   // VAR decisions are informational; skip
        is com.soccer.tracker.data.remote.dto.live.UnknownEventDto -> null
    }

    private fun mapCardType(detail: String?): CardType = when {
        detail?.contains("Second", ignoreCase = true) == true -> CardType.SECOND_YELLOW
        detail?.contains("Red", ignoreCase = true) == true -> CardType.RED
        else -> CardType.YELLOW
    }
}
