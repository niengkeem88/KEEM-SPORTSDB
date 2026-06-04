package com.soccer.tracker.domain.model

data class Team(
    val id: Long,
    val name: String,
    val shortCode: String?,
    val logoUrl: String?,
)
