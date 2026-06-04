package com.soccer.tracker.domain.model

import java.time.LocalDateTime

/**
 * A single event that occurred during a live match.
 *
 * Each variant carries the minute (and optional extra-minute) when it happened,
 * plus the team and player involved.
 */
sealed interface LiveEvent {
    val minute: Int
    val extraMinute: Int?
    val teamId: Long
    val teamName: String
    val playerName: String?
}

data class GoalEvent(
    override val minute: Int,
    override val extraMinute: Int? = null,
    override val teamId: Long,
    override val teamName: String,
    override val playerName: String?,
    val assistPlayerName: String? = null,
    val scoreHome: Int,
    val scoreAway: Int,
) : LiveEvent

data class CardEvent(
    override val minute: Int,
    override val extraMinute: Int? = null,
    override val teamId: Long,
    override val teamName: String,
    override val playerName: String?,
    val cardType: CardType,
) : LiveEvent

enum class CardType { YELLOW, RED, SECOND_YELLOW }

data class SubstitutionEvent(
    override val minute: Int,
    override val extraMinute: Int? = null,
    override val teamId: Long,
    override val teamName: String,
    override val playerName: String?,
    val playerOffName: String?,
) : LiveEvent

data class PenaltyEvent(
    override val minute: Int,
    override val extraMinute: Int? = null,
    override val teamId: Long,
    override val teamName: String,
    override val playerName: String?,
    val scored: Boolean,
) : LiveEvent
