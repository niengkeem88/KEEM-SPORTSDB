package com.soccer.tracker.domain.model

data class League(
    val id: Long,
    val name: String,
    val country: String,
    val logoUrl: String?,
    val type: LeagueType,
)

enum class LeagueType {
    LEAGUE,
    CUP,
}
