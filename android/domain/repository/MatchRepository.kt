package com.soccer.tracker.domain.repository

import com.soccer.tracker.domain.model.Fixture
import com.soccer.tracker.domain.util.Resource
import kotlinx.coroutines.flow.Flow

/**
 * Repository contract for match-related data operations.
 *
 * Single source of truth for the presentation layer. All functions return
 * [Flow]s of [Resource] so that callers can react to loading/success/error
 * states declaratively.
 */
interface MatchRepository {

    /**
     * Streams the list of currently live fixtures by polling the backend
     * periodically (every 30 s, matching the server-side cache TTL).
     *
     * Emits:
     * - [Resource.Loading] immediately on collection start.
     * - [Resource.Success] with the fixture list on each successful poll.
     * - [Resource.Error] if the network call fails (continues polling).
     */
    fun streamLiveFixtures(): Flow<Resource<List<Fixture>>>

    /**
     * Fetches full detail for a single fixture, including the live events timeline.
     *
     * This is a single-shot call (no polling) intended for the fixture detail screen.
     */
    fun getFixtureDetail(fixtureId: Long): Flow<Resource<Fixture>>

    /**
     * Fetches all fixtures scheduled for a given date.
     */
    fun getFixturesByDate(date: String): Flow<Resource<List<Fixture>>>
}
