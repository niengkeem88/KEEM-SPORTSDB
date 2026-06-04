package com.soccer.tracker.data.remote.api

import com.soccer.tracker.data.remote.dto.FixtureDetailDto
import com.soccer.tracker.data.remote.dto.FixtureListResponseDto
import com.soccer.tracker.data.remote.dto.LeagueListResponseDto
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path

/**
 * Retrofit interface mirroring the FastAPI backend endpoints.
 *
 * All methods are [suspend] functions for use with Kotlin coroutines.
 * The base URL is configured via [Retrofit.Builder.baseUrl] at construction time.
 */
interface SoccerApi {

    /** GET /api/v1/leagues — returns all tracked leagues. */
    @GET("api/v1/leagues")
    suspend fun getLeagues(): Response<LeagueListResponseDto>

    /** GET /api/v1/fixtures/date/{date} — all fixtures for a specific date. */
    @GET("api/v1/fixtures/date/{date}")
    suspend fun getFixturesByDate(
        @Path("date") date: String,
    ): Response<FixtureListResponseDto>

    /** GET /api/v1/fixtures/live — all currently in-play matches. */
    @GET("api/v1/fixtures/live")
    suspend fun getLiveFixtures(): Response<FixtureListResponseDto>

    /** GET /api/v1/fixtures/{id} — full fixture detail including events. */
    @GET("api/v1/fixtures/{id}")
    suspend fun getFixtureDetails(
        @Path("id") id: Long,
    ): Response<FixtureDetailDto>
}
