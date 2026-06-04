package com.soccer.tracker.presentation.livescores

import com.soccer.tracker.domain.model.Fixture

/**
 * Single, immutable UI state for the Live Scores screen.
 *
 * The ViewModel exposes a ``StateFlow<LiveScoresUiState>`` that the
 * Compose UI collects via ``collectAsStateWithLifecycle()``.
 */
data class LiveScoresUiState(
    val fixtures: List<Fixture> = emptyList(),
    val isLoading: Boolean = true,
    val errorMessage: String? = null,
) {
    /** True when the screen should display its initial loading indicator. */
    val isInitialLoading: Boolean get() = isLoading && fixtures.isEmpty()

    /** True when a refresh is ongoing but we already have data to show. */
    val isRefreshing: Boolean get() = isLoading && fixtures.isNotEmpty()
}
