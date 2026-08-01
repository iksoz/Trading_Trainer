from __future__ import annotations

from dataclasses import asdict, dataclass


TRENDLYNE_SUPERSTAR_SOURCE_URL = "https://us.trendlyne.com/us/portfolio/superstar-shareholders/index/"


@dataclass(frozen=True)
class SuperstarHolding:
    symbol: str
    name: str
    value_millions: float


@dataclass(frozen=True)
class SuperstarPortfolio:
    key: str
    name: str
    portfolio_value_millions: float
    monthly_change_pct: float
    stock_count: int
    sector_preferences: tuple[str, ...]
    holdings: tuple[SuperstarHolding, ...]
    source_url: str = TRENDLYNE_SUPERSTAR_SOURCE_URL

    def symbols(self) -> tuple[str, ...]:
        return tuple(holding.symbol for holding in self.holdings)

    def payload(self) -> dict[str, object]:
        return {
            **asdict(self),
            "symbols": list(self.symbols()),
            "source_label": "Trendlyne US Superstar Portfolios",
        }


SUPERSTAR_PORTFOLIOS: tuple[SuperstarPortfolio, ...] = (
    SuperstarPortfolio(
        key="warren_buffett",
        name="Warren Buffett",
        portfolio_value_millions=299_849.58,
        monthly_change_pct=4.27,
        stock_count=32,
        sector_preferences=(
            "Banking & Finance",
            "Telecom Equipment",
            "Food, Beverages & Tobacco",
        ),
        holdings=(
            SuperstarHolding("AAPL", "Apple", 72_072.17),
            SuperstarHolding("AXP", "American Express", 52_566.46),
            SuperstarHolding("KO", "Coca-Cola", 33_052.0),
        ),
    ),
    SuperstarPortfolio(
        key="ken_fisher",
        name="Ken Fisher",
        portfolio_value_millions=292_572.67,
        monthly_change_pct=1.91,
        stock_count=817,
        sector_preferences=(
            "Banking & Finance",
            "Software & Services",
            "Hardware Technology & Equipment",
        ),
        holdings=(
            SuperstarHolding("NVDA", "NVIDIA", 17_958.11),
            SuperstarHolding("AAPL", "Apple", 17_844.4),
            SuperstarHolding("GOOGL", "Alphabet (Class A)", 14_014.86),
        ),
    ),
    SuperstarPortfolio(
        key="bill_gates",
        name="Bill Gates",
        portfolio_value_millions=35_142.34,
        monthly_change_pct=0.36,
        stock_count=28,
        sector_preferences=(
            "Banking & Finance",
            "Automobiles & Auto Parts Manufacturers",
            "Transportation",
        ),
        holdings=(
            SuperstarHolding("BRK.B", "Berkshire Hathaway", 8_446.58),
            SuperstarHolding("CNI", "Canadian National Railway", 6_444.14),
            SuperstarHolding("WM", "Waste Management", 6_403.9),
        ),
    ),
    SuperstarPortfolio(
        key="ray_dalio",
        name="Ray Dalio",
        portfolio_value_millions=21_820.57,
        monthly_change_pct=-1.42,
        stock_count=1014,
        sector_preferences=(
            "Hardware Technology & Equipment",
            "Software & Services",
            "Banking & Finance",
        ),
        holdings=(
            SuperstarHolding("MU", "Micron Technology", 1_463.37),
            SuperstarHolding("AMZN", "Amazon", 1_084.19),
            SuperstarHolding("NVDA", "NVIDIA", 951.65),
        ),
    ),
    SuperstarPortfolio(
        key="catherine_wood",
        name="Catherine Wood",
        portfolio_value_millions=15_972.2,
        monthly_change_pct=3.23,
        stock_count=185,
        sector_preferences=(
            "Software & Services",
            "Pharma & Biotech",
            "Hardware Technology & Equipment",
        ),
        holdings=(
            SuperstarHolding("AMD", "AMD", 1_483.17),
            SuperstarHolding("TSLA", "Tesla", 1_151.08),
            SuperstarHolding("HOOD", "Robinhood Markets", 691.01),
        ),
    ),
    SuperstarPortfolio(
        key="bill_ackman",
        name="Bill Ackman",
        portfolio_value_millions=14_744.32,
        monthly_change_pct=2.26,
        stock_count=11,
        sector_preferences=(
            "Software & Services",
            "Banking & Finance",
            "Transportation",
        ),
        holdings=(
            SuperstarHolding("AMZN", "Amazon", 2_829.1),
            SuperstarHolding("BN", "Brookfield Corp", 2_572.35),
            SuperstarHolding("UBER", "Uber", 2_227.43),
        ),
    ),
)


def superstar_portfolios_payload() -> list[dict[str, object]]:
    return [portfolio.payload() for portfolio in SUPERSTAR_PORTFOLIOS]


def get_superstar_portfolio(key: str) -> SuperstarPortfolio:
    for portfolio in SUPERSTAR_PORTFOLIOS:
        if portfolio.key == key:
            return portfolio
    return SUPERSTAR_PORTFOLIOS[0]


def superstar_portfolio_keys() -> tuple[str, ...]:
    return tuple(portfolio.key for portfolio in SUPERSTAR_PORTFOLIOS)
