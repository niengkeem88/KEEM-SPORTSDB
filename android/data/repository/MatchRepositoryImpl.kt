package com.soccer.tracker.data.repository

import com.soccer.tracker.data.remote.api.SoccerApi
import com.soccer.tracker.data.remote.mapper.FixtureMapper.toDomain
import com.soccer.tracker.domain.model.Fixture
import com.soccer.tracker.domain.repository.MatchRepository
import com.soccer.tracker.domain.util.Resource
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Production implementation of [MatchRepository].
 *
 * Uses a polling-based approach for live fixtures because server-sent events
 * or WebSockets are not available from the upstream API-Football provider.
 *
 * The polling interval (30 s) is chosen to match the server-side Redis cache
 * TTL, ensuring clients never hammer the database.
 */
@Singleton
class MatchRepositoryImpl @Inject constructor(
    private val api: SoccerApi,
) : MatchRepository {

    companion object {
        /** Polling interval for live fixtures — matches server cache TTL. */
        private const val POLL_INTERVAL_MS = 30_000L

        /** Maximum consecutive failures before we back off (avoids busy-spinning). */
        private const val MAX_CONSECUTIVE_FAILURES = 3
    }

    // ---------------------------------------------------------------
    // streamLiveFixtures — periodic polling
    // ---------------------------------------------------------------

    override fun streamLiveFixtures(): Flow<Resource<List<Fixture>>> = flow {
        var consecutiveErrors = 0

        // Emit loading immediately
        emit(Resource.Loading)

        while (true) {
            try {
                val response = api.getLiveFixtures()

                if (response.isSuccessful) {
                    val body = response.body()
                    val fixtures = body?.data?.map { it.toDomain() } ?: emptyList()
                    emit(Resource.Success(fixtures))
                    consecutiveErrors = 0
                } else {
                    val errorMsg = "API error ${response.code()}: ${response.message()}"
                    emit(Resource.Error(errorMsg))
                    consecutiveErrors++
                }
            } catch (e: HttpException) {
                consecutiveErrors++
                emit(
                    Resource.Error(
                        message = "Server error (${e.code()})",
                        cause = e,
                    )
                )
            } catch (e: IOException) {
                consecutiveErrors++
                emit(
                    Resource.Error(
                        message = if (consecutiveErrors > MAX_CONSECUTIVE_FAILURES) {
                            "Connection lost — check your network"
                        } else {
                            "Network error — retrying..."
                        },
                        cause = e,
                    )
                )
            } catch (e: Exception) {
                consecutiveErrors++
                emit(
                    Resource.Error(
                        message = "Unexpected error: ${e.localizedMessage ?: "Unknown"}",
                        cause = e,
                    )
                )
            }

            // Wait for the polling interval (or a back-off if errors persist)
            val backOffMs = if (consecutiveErrors > MAX_CONSECUTIVE_FAILURES) {
                POLL_INTERVAL_MS * 2
            } else {
                POLL_INTERVAL_MS
            }
            delay(backOffMs)
        }
    }

    // ---------------------------------------------------------------
    // getFixtureDetail — single shot
    // ---------------------------------------------------------------

    override fun getFixtureDetail(fixtureId: Long): Flow<Resource<Fixture>> = flow {
        emit(Resource.Loading)
        try {
            val response = api.getFixtureDetails(fixtureId)
            if (response.isSuccessful) {
                val dto = response.body()
                if (dto != null) {
                    emit(Resource.Success(dto.toDomain()))
                } else {
                    emit(Resource.Error("Empty response body"))
                }
            } else {
                emit(
                    Resource.Error(
                        "API error ${response.code()}: ${response.message()}"
                    )
                )
            }
        } catch (e: HttpException) {
            emit(Resource.Error("Server error (${e.code()})", cause = e))
        } catch (e: IOException) {
            emit(Resource.Error("Network error — please try again", cause = e))
        } catch (e: Exception) {
            emit(Resource.Error("Unexpected error", cause = e))
        }
    }

    // ---------------------------------------------------------------
    // getFixturesByDate — single shot
    // ---------------------------------------------------------------

    override fun getFixturesByDate(date: String): Flow<Resource<List<Fixture>>> = flow {
        emit(Resource.Loading)
        try {
            val response = api.getFixturesByDate(date)
            if (response.isSuccessful) {
                val body = response.body()
                val fixtures = body?.data?.map { it.toDomain() } ?: emptyList()
                emit(Resource.Success(fixtures))
            } else {
                emit(
                    Resource.Error(
                        "API error ${response.code()}: ${response.message()}"
                    )
                )
            }
        } catch (e: HttpException) {
            emit(Resource.Error("Server error (${e.code()})", cause = e))
        } catch (e: IOException) {
            emit(Resource.Error("Network error — please try again", cause = e))
        } catch (e: Exception) {
            emit(Resource.Error("Unexpected error", cause = e))
        }
    }
}
