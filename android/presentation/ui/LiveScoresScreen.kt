package com.soccer.tracker.presentation.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.soccer.tracker.domain.model.Fixture
import com.soccer.tracker.domain.model.MatchStatus
import com.soccer.tracker.presentation.livescores.LiveScoresUiState
import com.soccer.tracker.presentation.livescores.LiveScoresViewModel

// ---------------------------------------------------------------------------
// Screen composable
// ---------------------------------------------------------------------------

/**
 * Top-level screen for displaying live match scores.
 *
 * Uses [collectAsStateWithLifecycle] to safely observe the ViewModel's
 * [StateFlow] across configuration changes and lifecycle events.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveScoresScreen(
    viewModel: LiveScoresViewModel,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Live Scores") },
            )
        },
    ) { innerPadding ->
        PullToRefreshBox(
            isRefreshing = uiState.isRefreshing,
            onRefresh = { viewModel.onRefresh() },
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
        ) {
            when {
                // ── Initial loading ──────────────────────────────────────
                uiState.isInitialLoading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                }

                // ── Error with no cached data ───────────────────────────
                uiState.errorMessage != null && uiState.fixtures.isEmpty() -> {
                    ErrorState(
                        message = uiState.errorMessage!!,
                        onRetry = { viewModel.onRefresh() },
                    )
                }

                // ── Empty state ──────────────────────────────────────────
                uiState.fixtures.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            text = "No live matches right now",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                // ── Live fixture list ────────────────────────────────────
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            horizontal = 16.dp,
                            vertical = 8.dp,
                        ),
                    ) {
                        items(
                            items = uiState.fixtures,
                            key = { it.id },
                        ) { fixture ->
                            LiveFixtureCard(fixture = fixture)
                        }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

@Composable
private fun LiveFixtureCard(
    fixture: Fixture,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
        ) {
            // ── Match status badge ──────────────────────────────────────
            StatusBadge(status = fixture.matchStatus)

            Spacer(modifier = Modifier.height(12.dp))

            // ── Score row ────────────────────────────────────────────────
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Home team
                TeamColumn(
                    name = fixture.homeTeam.name,
                    shortCode = fixture.homeTeam.shortCode,
                    score = fixture.homeScore,
                    alignment = Alignment.End,
                )

                // Score divider
                Text(
                    text = ":",
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 12.dp),
                )

                // Away team
                TeamColumn(
                    name = fixture.awayTeam.name,
                    shortCode = fixture.awayTeam.shortCode,
                    score = fixture.awayScore,
                    alignment = Alignment.Start,
                )
            }

            // ── Live event summary ──────────────────────────────────────
            if (fixture.liveEvents.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "⚽ ${fixture.liveEvents.size} events",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun TeamColumn(
    name: String,
    shortCode: String?,
    score: Int?,
    alignment: Alignment.Horizontal,
) {
    Column(
        horizontalAlignment = alignment,
    ) {
        Text(
            text = shortCode ?: name.take(3).uppercase(),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            textAlign = when (alignment) {
                Alignment.End -> TextAlign.End
                else -> TextAlign.Start
            },
        )
        Text(
            text = name,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
        )
        Text(
            text = score?.toString() ?: "-",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun StatusBadge(status: MatchStatus) {
    val (backgroundColor, text) = when (status) {
        MatchStatus.FIRST_HALF,
        MatchStatus.SECOND_HALF,
        MatchStatus.EXTRA_TIME,
        MatchStatus.PENALTIES,
        -> Color(0xFF4CAF50) to status.code   // Green = live
        MatchStatus.HALF_TIME -> Color(0xFFFFA000) to "HT"
        MatchStatus.FULL_TIME,
        MatchStatus.AFTER_EXTRA_TIME,
        MatchStatus.AFTER_PENALTIES,
        -> Color(0xFF757575) to status.code   // Grey = finished
        else -> Color(0xFF757575) to status.code
    }

    Text(
        text = text,
        color = Color.White,
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(backgroundColor)
            .padding(horizontal = 8.dp, vertical = 2.dp),
    )
}

@Composable
private fun ErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = "Something went wrong",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.error,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 32.dp),
                textAlign = TextAlign.Center,
            )
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = onRetry) {
                Text("Retry")
            }
        }
    }
}
