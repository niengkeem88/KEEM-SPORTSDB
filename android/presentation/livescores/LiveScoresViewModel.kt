package com.soccer.tracker.presentation.livescores

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.soccer.tracker.domain.repository.MatchRepository
import com.soccer.tracker.domain.util.Resource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for the Live Scores screen.
 *
 * Launches a single coroutine that collects from [MatchRepository.streamLiveFixtures]
 * and maps each [Resource] emission into a [LiveScoresUiState] update.
 *
 * The polling lifecycle is tied to the ViewModel's scope: when the screen is
 * removed from the composition, the ViewModel is cleared and polling stops.
 */
@HiltViewModel
class LiveScoresViewModel @Inject constructor(
    private val matchRepository: MatchRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LiveScoresUiState())
    val uiState: StateFlow<LiveScoresUiState> = _uiState.asStateFlow()

    init {
        observeLiveFixtures()
    }

    private fun observeLiveFixtures() {
        viewModelScope.launch {
            matchRepository.streamLiveFixtures()
                .catch { e ->
                    // Last-resort catch for any unhandled exception in the flow
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = e.localizedMessage ?: "Unknown error",
                        )
                    }
                }
                .collect { resource ->
                    when (resource) {
                        is Resource.Loading -> {
                            _uiState.update { it.copy(isLoading = true) }
                        }
                        is Resource.Success -> {
                            _uiState.update {
                                it.copy(
                                    fixtures = resource.data,
                                    isLoading = false,
                                    errorMessage = null,
                                )
                            }
                        }
                        is Resource.Error -> {
                            _uiState.update {
                                it.copy(
                                    isLoading = false,
                                    errorMessage = resource.message,
                                )
                            }
                        }
                    }
                }
        }
    }

    /**
     * Called when the user manually requests a refresh.
     *
     * Because the polling flow is already running, this simply resets the
     * error state and lets the next poll emission populate the UI.
     * A more advanced version could cancel the ongoing flow and restart it.
     */
    fun onRefresh() {
        _uiState.update { it.copy(errorMessage = null) }
        // The polling flow will naturally emit fresh data within 30 s.
        // For an immediate refresh, we could expose a "force poll" channel.
    }
}
