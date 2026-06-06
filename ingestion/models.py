"""SQLAlchemy 2.0 ORM models mirroring the production PostgreSQL schema (001_global_soccer_schema.sql)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    BigInteger,
    SmallInteger,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# LEAGUES
# ---------------------------------------------------------------------------
class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(
        String(10), CheckConstraint("type IN ('League', 'Cup')"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    seasons = relationship("Season", back_populates="league", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<League id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# SEASONS
# ---------------------------------------------------------------------------
class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        CheckConstraint("year >= 1900 AND year <= 2200"),
        CheckConstraint("end_date >= start_date"),
        UniqueConstraint("league_id", name="uq_seasons_league_current"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("leagues.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    league = relationship("League", back_populates="seasons")
    standings = relationship("Standing", back_populates="season", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<Season id={self.id} league={self.league_id} year={self.year}>"


# ---------------------------------------------------------------------------
# TEAMS
# ---------------------------------------------------------------------------
class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    short_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------
class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id"),
        CheckConstraint(
            "(match_status IN ('FT','AET','AP','AWD','WO') AND home_score IS NOT NULL AND away_score IS NOT NULL)"
            " OR (match_status NOT IN ('FT','AET','AP','AWD','WO'))",
            name="chk_fixtures_complete_scores",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("leagues.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("seasons.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    home_team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    away_team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    match_status: Mapped[str] = mapped_column(
        String(6),
        CheckConstraint(
            "match_status IN ('NS','1H','HT','2H','ET','P','FT','AET','AP','INT','ABD','CANC','SUSP','AWD','WO')"
        ),
        nullable=False,
        default="NS",
    )
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    home_score: Mapped[Optional[int]] = mapped_column(
        SmallInteger, CheckConstraint("home_score IS NULL OR home_score >= 0"), nullable=True
    )
    away_score: Mapped[Optional[int]] = mapped_column(
        SmallInteger, CheckConstraint("away_score IS NULL OR away_score >= 0"), nullable=True
    )
    live_events_cache: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Fixture id={self.id} {self.home_team_id}-{self.away_team_id} "
            f"status={self.match_status}>"
        )


# ---------------------------------------------------------------------------
# STANDINGS
# ---------------------------------------------------------------------------
class Standing(Base):
    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint("season_id", "team_id", name="uq_standings_season_team"),
        UniqueConstraint("season_id", "rank", name="uq_standings_season_rank"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # BIGSERIAL
    season_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("seasons.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("rank >= 1"), nullable=False)
    points: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("points >= 0"), nullable=False, default=0)
    played: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("played >= 0"), nullable=False, default=0)
    won: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("won >= 0"), nullable=False, default=0)
    drawn: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("drawn >= 0"), nullable=False, default=0)
    lost: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("lost >= 0"), nullable=False, default=0)
    goals_for: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("goals_for >= 0"), nullable=False, default=0)
    goals_against: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("goals_against >= 0"), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    season = relationship("Season", back_populates="standings")
    team = relationship("Team")

    def __repr__(self) -> str:
        return f"<Standing season={self.season_id} team={self.team_id} rank={self.rank}>"
