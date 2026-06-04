package com.soccer.tracker.data.remote.dto.live

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonContentPolymorphicSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

// ---------------------------------------------------------------------------
// Shared sub-types
// ---------------------------------------------------------------------------

@Serializable
data class TimeDto(
    @SerialName("elapsed") val elapsed: Int,
    @SerialName("extra") val extra: Int? = null,
)

@Serializable
data class PlayerRefDto(
    @SerialName("id") val id: Long? = null,
    @SerialName("name") val name: String? = null,
)

@Serializable
data class TeamRefDto(
    @SerialName("id") val id: Long? = null,
    @SerialName("name") val name: String? = null,
    @SerialName("logo") val logo: String? = null,
)

// ---------------------------------------------------------------------------
// Polymorphic event hierarchy
// ---------------------------------------------------------------------------

/**
 * Base type for every element in the ``live_events_cache.events[]`` array.
 *
 * The API uses a ``type`` discriminator string ("Goal", "Card", "subst", etc.).
 * We use a custom serializer because the discriminator values don't map 1:1
 * to class names.
 */
@Serializable(with = LiveEventPayloadDtoSerializer::class)
sealed interface LiveEventPayloadDto {
    val time: TimeDto
    val team: TeamRefDto
    val player: PlayerRefDto?
    val type: String
    val detail: String?
    val comments: String?
}

@Serializable
data class GoalEventDto(
    @SerialName("time") override val time: TimeDto,
    @SerialName("team") override val team: TeamRefDto,
    @SerialName("player") override val player: PlayerRefDto? = null,
    @SerialName("assist") val assist: PlayerRefDto? = null,
    @SerialName("type") override val type: String,
    @SerialName("detail") override val detail: String? = null,
    @SerialName("comments") override val comments: String? = null,
    // Score at the time of the goal (injected by the backend in "detail" or parsed from "score")
) : LiveEventPayloadDto

@Serializable
data class CardEventDto(
    @SerialName("time") override val time: TimeDto,
    @SerialName("team") override val team: TeamRefDto,
    @SerialName("player") override val player: PlayerRefDto? = null,
    @SerialName("type") override val type: String,
    @SerialName("detail") override val detail: String? = null,   // "Yellow Card" | "Red Card" | "Second Yellow Card"
    @SerialName("comments") override val comments: String? = null,
) : LiveEventPayloadDto

@Serializable
data class SubstitutionEventDto(
    @SerialName("time") override val time: TimeDto,
    @SerialName("team") override val team: TeamRefDto,
    @SerialName("player") override val player: PlayerRefDto? = null,   // player ON
    @SerialName("assist") val playerOff: PlayerRefDto? = null,         // player OFF
    @SerialName("type") override val type: String,
    @SerialName("detail") override val detail: String? = null,
    @SerialName("comments") override val comments: String? = null,
) : LiveEventPayloadDto

@Serializable
data class VarEventDto(
    @SerialName("time") override val time: TimeDto,
    @SerialName("team") override val team: TeamRefDto,
    @SerialName("player") override val player: PlayerRefDto? = null,
    @SerialName("type") override val type: String,
    @SerialName("detail") override val detail: String? = null,   // "Goal cancelled" | "Penalty confirmed" etc.
    @SerialName("comments") override val comments: String? = null,
) : LiveEventPayloadDto

/** Fallback for unrecognised event types — preserves raw data. */
@Serializable
data class UnknownEventDto(
    @SerialName("time") override val time: TimeDto,
    @SerialName("team") override val team: TeamRefDto,
    @SerialName("player") override val player: PlayerRefDto? = null,
    @SerialName("type") override val type: String,
    @SerialName("detail") override val detail: String? = null,
    @SerialName("comments") override val comments: String? = null,
) : LiveEventPayloadDto

// ---------------------------------------------------------------------------
// Custom polymorphic serializer — dispatches on the "type" field
// ---------------------------------------------------------------------------

object LiveEventPayloadDtoSerializer :
    JsonContentPolymorphicSerializer<LiveEventPayloadDto>(LiveEventPayloadDto::class) {

    override fun selectDeserializer(element: JsonElement) = when {
        element.jsonObject["type"]?.jsonPrimitive?.content == "Goal" -> GoalEventDto.serializer()
        element.jsonObject["type"]?.jsonPrimitive?.content == "Card" -> CardEventDto.serializer()
        element.jsonObject["type"]?.jsonPrimitive?.content == "subst" -> SubstitutionEventDto.serializer()
        element.jsonObject["type"]?.jsonPrimitive?.content == "Var" -> VarEventDto.serializer()
        else -> UnknownEventDto.serializer()
    }
}
