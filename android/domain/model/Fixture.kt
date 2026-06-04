package com.soccer.tracker.domain.model

import java.time.LocalDateTime

/**
 * Domain model representing a single match fixture.
 */
data class Fixture(
    val id: Long,
    val leagueId: Long,
    val seasonId: Long,
    val homeTeam: Team,
    val awayTeam: Team,
    val matchStatus: MatchStatus,
    val startTime: LocalDateTime,
    val homeScore: Int?,
    val awayScore: Int?,
    val liveEvents: List<LiveEvent> = emptyList(),
    val formationHome: String? = null,
    val formationAway: String? = null,
)

/**
 * Canonical match statuses — mirrors the PostgreSQL CHECK constraint.
 */
enum class MatchStatus(val code: String) {
    NOT_STARTED("NS"),
    FIRST_HALF("1H"),
    HALF_TIME("HT"),
    SECOND_HALF("2H"),
    EXTRA_TIME("ET"),
    PENALTIES("P"),
    FULL_TIME("FT"),
    AFTER_EXTRA_TIME("AET"),
    AFTER_PENALTIES("AP"),
    INTERRUPTED("INT"),
    ABANDONED("ABD"),
    CANCELLED("CANC"),
    SUSPENDED("SUSP"),
    AWARDED("AWD"),
    WALKOVER("WO");

    companion object {
        /** Set of statuses that indicate a match is currently in progress. */
        val LIVE_STATUSES = setOf(FIRST_HALF, HALF_TIME, SECOND_HALF, EXTRA_TIME, PENALTIES)

        /** Set of statuses that indicate a match has finished. */
        val FINISHED_STATUSES = setOf(FULL_TIME, AFTER_EXTRA_TIME, AFTER_PENALTIES, AWARDED, WALKOVER)

        fun fromCode(code: String): MatchStatus =
            entries.firstOrNull { it.code == code } ?: NOT_STARTED
    }

    val isLive: Boolean get() = this in LIVE_STATUSES
    val isFinished: Boolean get() = this in FINISHED_STATUSES
}
