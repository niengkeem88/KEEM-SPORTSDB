package com.soccer.tracker.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Matches GET /api/v1/leagues → LeagueResponse.
 *
 * Field names use @SerialName to map snake_case backend JSON
 * to idiomatic Kotlin camelCase.
 */
@Serializable
data class LeagueDto(
    @SerialName("id") val id: Long,
    @SerialName("name") val name: String,
    @SerialName("country") val country: String,
    @SerialName("logo_url") val logoUrl: String? = null,
    @SerialName("type") val type: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

/** Wrapper for list responses that return ``{ "data": [...], "total": N }``. */
@Serializable
data class LeagueListResponseDto(
    @SerialName("data") val data: List<LeagueDto>,
    @SerialName("total") val total: Int,
)
