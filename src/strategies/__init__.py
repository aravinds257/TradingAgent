"""Strategy agent registry — maps names to classes for dynamic loading."""

from src.strategies.base import BaseStrategyAgent
from src.strategies.bollinger_mean_reversion import BollingerMeanReversionAgent
from src.strategies.ma_crossover import MACrossoverAgent
from src.strategies.macd_squeeze import MACDSqueezeAgent
from src.strategies.momentum_breakout import MomentumBreakoutAgent
from src.strategies.pairs_trading import PairsTradingAgent
from src.strategies.rsi_divergence import RSIDivergenceAgent

STRATEGY_REGISTRY: dict[str, type[BaseStrategyAgent]] = {
    "ma_crossover": MACrossoverAgent,
    "rsi_divergence": RSIDivergenceAgent,
    "bollinger_mean_reversion": BollingerMeanReversionAgent,
    "momentum_breakout": MomentumBreakoutAgent,
    "macd_squeeze": MACDSqueezeAgent,
    "pairs_trading": PairsTradingAgent,
}
