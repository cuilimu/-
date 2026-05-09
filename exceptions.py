"""
Typed exception hierarchy for the engine.
All modules raise subtypes of EngineError — never bare exceptions.
"""


class EngineError(Exception):
    """Base for all engine errors."""


class DataError(EngineError):
    """Raised by data layer (fetch failures, missing tickers, cache corruption)."""


class PortfolioError(EngineError):
    """Raised by portfolio engine (insufficient cash, position not found, etc.)."""


class BacktestError(EngineError):
    """Raised by backtest runner (bad date range, strategy misconfiguration, etc.)."""


class AnalyticsError(EngineError):
    """Raised by analytics layer (insufficient data, computation failures)."""


class VisualizationError(EngineError):
    """Raised by viz layer (unsupported chart type, empty data, etc.)."""
