package com.soccer.tracker.presentation.di

import com.soccer.tracker.data.repository.MatchRepositoryImpl
import com.soccer.tracker.domain.repository.MatchRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Hilt module that binds the [MatchRepository] interface to its
 * [MatchRepositoryImpl] implementation.
 *
 * Because [MatchRepositoryImpl] is annotated with [javax.inject.Singleton],
 * a single instance is shared across the entire application.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class AppModule {

    @Binds
    @Singleton
    abstract fun bindMatchRepository(
        impl: MatchRepositoryImpl,
    ): MatchRepository
}
