package com.soccer.tracker.domain.util

/**
 * Wrapper for data-layer results that expresses [Loading], [Success], or [Error] states.
 *
 * This is consumed by the presentation layer to drive UI state without exposing
 * raw exceptions or network details.
 */
sealed interface Resource<out T> {
    data object Loading : Resource<Nothing>
    data class Success<T>(val data: T) : Resource<T>
    data class Error(val message: String, val cause: Throwable? = null) : Resource<Nothing>
}
