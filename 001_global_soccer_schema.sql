-- =============================================================================
-- Global Soccer Tracking Database — Production Schema Migration
-- =============================================================================
-- Description: Core relational structures for a high-throughput multi-league
--              soccer data platform. Designed for strict referential integrity,
--              cascade-safe deletions, and high-frequency read optimisation.
-- Target:     PostgreSQL 15+
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. LEAGUES
-- ---------------------------------------------------------------------------
-- Canonical list of leagues/cups sourced from the external API provider.
-- The primary key is the upstream API provider's own identifier rather than
-- a synthetic serial, ensuring direct idempotent upserts from API payloads.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leagues (
    id          BIGINT       NOT NULL PRIMARY KEY,   -- External API provider PK
    name        VARCHAR(120) NOT NULL,                -- Full league name (e.g. "Premier League")
    country     VARCHAR(80)  NOT NULL,                -- Country or region name
    logo_url    TEXT,                                 -- Fully-qualified URL to league logo
    type        VARCHAR(10)  NOT NULL CHECK (type IN ('League', 'Cup')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE  leagues    IS 'Leagues and cups sourced from the external API provider.';
COMMENT ON COLUMN leagues.id IS 'Natural key — matches the external API provider league identifier.';

-- ---------------------------------------------------------------------------
-- 2. SEASONS
-- ---------------------------------------------------------------------------
-- Each league publishes a season (or edition) every year.  The `is_current`
-- flag allows the application to quickly resolve "this season" for any league
-- without filtering by date ranges on every query.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    id          BIGINT       NOT NULL PRIMARY KEY,   -- External API provider PK
    league_id   BIGINT       NOT NULL,
    year        SMALLINT     NOT NULL CHECK (year >= 1900 AND year <= 2200),
    start_date  DATE         NOT NULL,
    end_date    DATE         NOT NULL,
    is_current  BOOLEAN      NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_seasons_league
        FOREIGN KEY (league_id)
        REFERENCES leagues (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- A league cannot have more than one "current" season at the same time.
    CONSTRAINT uq_seasons_league_current
        UNIQUE NULLS NOT DISTINCT (league_id) WHERE is_current = true,

    CONSTRAINT chk_seasons_dates CHECK (end_date >= start_date)
);

COMMENT ON TABLE  seasons IS 'Seasonal editions per league.';
COMMENT ON COLUMN seasons.is_current IS 'Only one season per league can be current at any time (enforced via partial unique constraint).';

CREATE INDEX idx_seasons_league_year
    ON seasons (league_id, year DESC);

-- ---------------------------------------------------------------------------
-- 3. TEAMS
-- ---------------------------------------------------------------------------
-- Global team registry.  A single team (e.g. "FC Barcelona") participates in
-- many leagues and seasons.  The primary key is the upstream API provider id,
-- which simplifies synchronisation when the same team appears across multiple
-- league payloads.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id          BIGINT       NOT NULL PRIMARY KEY,   -- External API provider PK
    name        VARCHAR(120) NOT NULL,                -- Full club name
    short_code  VARCHAR(10),                          -- Abbreviation (e.g. "BAR", "MCI")
    logo_url    TEXT,                                 -- Fully-qualified URL to team logo
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE  teams    IS 'Global club/national-team registry keyed by external API provider id.';
COMMENT ON COLUMN teams.short_code IS 'Short alphanumeric abbreviation (e.g. BAR, MCI, LIV).';

-- ---------------------------------------------------------------------------
-- 4. FIXTURES
-- ---------------------------------------------------------------------------
-- Each fixture represents a single match between two teams within a league
-- season.  The `live_events_cache` column holds the entire live-update JSON
-- payload (goals, cards, substitutions, timestamps, etc.) so that the API
-- layer can serve real-time timeline data without additional joins.
--
-- Score columns are nullable because a fixture in state "NS" (not started)
-- does not yet have scores.  Non-nullable CHECK constraints guarantee that
-- once a score exists it is non-negative.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixtures (
    id                BIGINT       NOT NULL PRIMARY KEY,  -- External API provider PK
    league_id         BIGINT       NOT NULL,
    season_id         BIGINT       NOT NULL,
    home_team_id      BIGINT       NOT NULL,
    away_team_id      BIGINT       NOT NULL,
    match_status      VARCHAR(6)   NOT NULL DEFAULT 'NS'
                                    CHECK (match_status IN (
                                        'NS',   -- Not Started
                                        '1H',   -- First Half
                                        'HT',   -- Half Time
                                        '2H',   -- Second Half
                                        'ET',   -- Extra Time
                                        'P',    -- Penalties
                                        'FT',   -- Full Time
                                        'AET',  -- After Extra Time
                                        'AP',   -- After Penalties
                                        'INT',  -- Interrupted
                                        'ABD',  -- Abandoned
                                        'CANC', -- Cancelled
                                        'SUSP', -- Suspended
                                        'AWD',  -- Awarded
                                        'WO'    -- Walkover
                                    )),
    start_time        TIMESTAMPTZ  NOT NULL,
    home_score        SMALLINT     CHECK (home_score IS NULL OR home_score >= 0),
    away_score        SMALLINT     CHECK (away_score IS NULL OR away_score >= 0),
    live_events_cache JSONB,                            -- Complete live match timeline
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_fixtures_league
        FOREIGN KEY (league_id)
        REFERENCES leagues (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_fixtures_season
        FOREIGN KEY (season_id)
        REFERENCES seasons (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_fixtures_home_team
        FOREIGN KEY (home_team_id)
        REFERENCES teams (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_fixtures_away_team
        FOREIGN KEY (away_team_id)
        REFERENCES teams (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Prevent a team from playing itself
    CONSTRAINT chk_fixtures_distinct_teams CHECK (home_team_id <> away_team_id),

    -- If match_status indicates the match is finished, scores must be present
    CONSTRAINT chk_fixtures_complete_scores CHECK (
        (match_status IN ('FT', 'AET', 'AP', 'AWD', 'WO') AND home_score IS NOT NULL AND away_score IS NOT NULL)
        OR
        (match_status NOT IN ('FT', 'AET', 'AP', 'AWD', 'WO'))
    )
);

COMMENT ON TABLE  fixtures                 IS 'Individual matches (fixtures) with real-time event cache.';
COMMENT ON COLUMN fixtures.match_status    IS 'Match status code — NS=Not Started, 1H/2H=Halves, HT=Half Time, FT=Full Time, etc.';
COMMENT ON COLUMN fixtures.home_score      IS 'Nullable; set only once the match progresses beyond NS.';
COMMENT ON COLUMN fixtures.away_score      IS 'Nullable; set only once the match progresses beyond NS.';
COMMENT ON COLUMN fixtures.live_events_cache IS 'Denormalised JSONB containing the full live match timeline (goals, cards, subs, stats) as received from the API provider.';

-- ---------------------------------------------------------------------------
-- 5. STANDINGS
-- ---------------------------------------------------------------------------
-- Season-long league table for each team.  A unique constraint on
-- (season_id, rank) ensures no two teams share the same rank within a
-- season, while (season_id, team_id) prevents duplicate entries.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS standings (
    id            BIGSERIAL    NOT NULL PRIMARY KEY,
    season_id     BIGINT       NOT NULL,
    team_id       BIGINT       NOT NULL,
    rank          SMALLINT     NOT NULL CHECK (rank >= 1),
    points        SMALLINT     NOT NULL DEFAULT 0 CHECK (points >= 0),
    played        SMALLINT     NOT NULL DEFAULT 0 CHECK (played >= 0),
    won           SMALLINT     NOT NULL DEFAULT 0 CHECK (won >= 0),
    drawn         SMALLINT     NOT NULL DEFAULT 0 CHECK (drawn >= 0),
    lost          SMALLINT     NOT NULL DEFAULT 0 CHECK (lost >= 0),
    goals_for     SMALLINT     NOT NULL DEFAULT 0 CHECK (goals_for >= 0),
    goals_against SMALLINT     NOT NULL DEFAULT 0 CHECK (goals_against >= 0),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_standings_season
        FOREIGN KEY (season_id)
        REFERENCES seasons (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_standings_team
        FOREIGN KEY (team_id)
        REFERENCES teams (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- One entry per team per season
    CONSTRAINT uq_standings_season_team UNIQUE (season_id, team_id),

    -- No duplicate ranks within a season
    CONSTRAINT uq_standings_season_rank UNIQUE (season_id, rank)
);

COMMENT ON TABLE standings IS 'League standings per season — one row per team.';

-- ===========================================================================
-- INDEXES — Optimised for high-frequency read workloads
-- ===========================================================================
-- ---------------------------------------------------------------------------
-- FIXTURES
-- ---------------------------------------------------------------------------

-- B-Tree:  Fast retrieval of currently-live matches ordered by kick-off.
--          Typical query:  WHERE match_status IN ('1H','2H','HT','ET','P')
--          ORDER BY start_time  LIMIT 50;
CREATE INDEX idx_fixtures_live
    ON fixtures (match_status, start_time DESC)
    WHERE match_status IN ('1H', '2H', 'HT', 'ET', 'P');

-- B-Tree:  Lookup all fixtures for a league within a specific season.
--          Typical query:  WHERE league_id = 123 AND season_id = 456
--          ORDER BY start_time;
CREATE INDEX idx_fixtures_league_season
    ON fixtures (league_id, season_id, start_time DESC);

-- B-Tree:  Lookup fixtures for a given team (home or away) efficiently.
CREATE INDEX idx_fixtures_home_team
    ON fixtures (home_team_id, start_time DESC);

CREATE INDEX idx_fixtures_away_team
    ON fixtures (away_team_id, start_time DESC);

-- B-Tree:  Upcoming / recent fixtures sorted by start time (global dashboard).
CREATE INDEX idx_fixtures_start_time
    ON fixtures (start_time DESC);

-- ---------------------------------------------------------------------------
-- GIN: JSONB index on live_events_cache for ad-hoc queries against the
--      live match timeline payload.  Uses the default `jsonb_path_ops`
--      operator class which produces a smaller, faster index for path-based
--      lookups (e.g. @> '{"events": [{"type": "goal"}]}').
-- ---------------------------------------------------------------------------
CREATE INDEX idx_fixtures_live_events_gin
    ON fixtures USING GIN (live_events_cache jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- STANDINGS
-- ---------------------------------------------------------------------------

-- B-Tree:  Typical leaderboard query — fetch all standings for a season
--          ordered by rank.
CREATE INDEX idx_standings_season_rank
    ON standings (season_id, rank ASC);

-- B-Tree:  Lookup a specific team's standing across seasons (historical).
CREATE INDEX idx_standings_team
    ON standings (team_id, season_id DESC);

-- ===========================================================================
-- TRIGGER: auto-update `updated_at` on row modification
-- ===========================================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leagues_updated_at
    BEFORE UPDATE ON leagues
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_seasons_updated_at
    BEFORE UPDATE ON seasons
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_fixtures_updated_at
    BEFORE UPDATE ON fixtures
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_standings_updated_at
    BEFORE UPDATE ON standings
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ===========================================================================
-- End of migration 001_global_soccer_schema.sql
-- ===========================================================================
