package com.soccer.tracker.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TeamDto(
    @SerialName("id") val id: Long,
    @SerialName("name") val name: String,
    @SerialName("short_code") val shortCode: String? = null,
    @SerialName("logo_url") val logoUrl: String? = null,
)
