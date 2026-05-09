"""
analytics/factor_investing/theory.py — Academic theory for each factor and portfolio construction.

Each entry in FACTOR_THEORY contains:
  name        : display name
  category    : factor category (Momentum / Value / Size / Risk / Liquidity / Quality)
  description : 2-3 paragraph theoretical background
  formula_tex : LaTeX string for the key characteristic formula
  qspread_tex : LaTeX string for the Q-spread (long-short) formula
  references  : key academic papers
  intuition   : one-sentence plain-English summary
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FactorEntry:
    name: str
    category: str
    description: str
    formula_tex: str       # LaTeX for the factor characteristic
    qspread_tex: str       # LaTeX for the Q-spread return
    references: list[str]
    intuition: str


FACTOR_THEORY: dict[str, FactorEntry] = {

    "HL1M": FactorEntry(
        name="HL1M — Short-term Reversal (1-Month)",
        category="Momentum / Reversal",
        description=(
            "Short-term reversal documents that stocks with extreme returns "
            "over the past month tend to revert in the following month. "
            "Jegadeesh (1990) showed that a strategy of buying recent "
            "under-performers and selling recent over-performers earns "
            "significantly positive returns. The primary mechanism is "
            "market microstructure: bid-ask bounce inflates measured "
            "returns in month t, which partially unwinds in t+1. "
            "Liquidity providers also push prices temporarily away from "
            "fundamental value when absorbing order flow, creating "
            "predictable mean-reversion.\n\n"
            "A secondary explanation is short-horizon investor overreaction: "
            "news in month t drives prices beyond fair value, and rational "
            "arbitrageurs correct the overshoot in month t+1. Because the "
            "holding period is short and turnover is high, implementation "
            "costs are large relative to gross alpha, making this more of "
            "a theoretical benchmark than a deployable strategy on its own."
        ),
        formula_tex=r"HL1M_i = R_{i,\,t-1}",
        qspread_tex=(
            r"r_{HL1M,\,t} = "
            r"\frac{1}{|Q5_t|}\sum_{i \in Q5_t} r_{i,t} "
            r"- \frac{1}{|Q1_t|}\sum_{i \in Q1_t} r_{i,t}"
            r"\quad\text{where } Q5_t = \text{top quintile by } R_{i,t-1}"
        ),
        references=[
            "Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. "
            "Journal of Finance, 45(3), 881–898.",
            "Lehmann, B. N. (1990). Fads, martingales, and market efficiency. "
            "Quarterly Journal of Economics, 105(1), 1–28.",
        ],
        intuition="Extreme monthly losers tend to bounce back; extreme winners tend to pull back.",
    ),

    "LTGC": FactorEntry(
        name="LTGC — Long-term Growth Consensus",
        category="Quality / Growth",
        description=(
            "LTGC captures the consensus analyst estimate of long-run "
            "earnings-per-share (EPS) growth, typically a 3-5 year horizon. "
            "La Porta (1996) showed that high-LTGC stocks (growth darlings) "
            "are systematically overpriced: investors extrapolate past earnings "
            "growth too aggressively, bidding up prices beyond what fundamentals "
            "justify. When realized growth disappoints, prices correct downward. "
            "This is closely related to the value premium — stocks with low LTGC "
            "are often value stocks with depressed prices.\n\n"
            "The Q-spread for LTGC is typically negative: high-growth-forecast "
            "stocks (Q5) underperform low-growth-forecast stocks (Q1) prospectively. "
            "This connects to the broader literature on analyst forecast optimism "
            "bias: sell-side forecasts tend to be systematically over-optimistic, "
            "especially for glamour stocks with high historical growth."
        ),
        formula_tex=(
            r"LTGC_i = \mathbb{E}\!\left[\Delta EPS_{i,\,3\text{–}5y}\right]"
            r"\quad\text{(IBES/CapitalIQ consensus)}"
        ),
        qspread_tex=(
            r"r_{LTGC,\,t} = "
            r"\frac{1}{|Q5_t|}\sum_{i \in Q5_t} r_{i,t} "
            r"- \frac{1}{|Q1_t|}\sum_{i \in Q1_t} r_{i,t}"
            r"\quad\text{where } Q5_t = \text{top quintile by } LTGC_i"
        ),
        references=[
            "La Porta, R. (1996). Expectations and the cross-section of stock returns. "
            "Journal of Finance, 51(5), 1715–1742.",
            "Lakonishok, J., Shleifer, A., & Vishny, R. W. (1994). Contrarian investment, "
            "extrapolation, and risk. Journal of Finance, 49(5), 1541–1578.",
        ],
        intuition="Stocks with sky-high growth forecasts are priced to disappoint; low-forecast stocks beat expectations.",
    ),

    "MOM": FactorEntry(
        name="MOM — Price Momentum (12-1)",
        category="Momentum",
        description=(
            "Jegadeesh and Titman (1993) documented that stocks ranked by "
            "their past 12-month return (skipping the most recent month) "
            "continue to exhibit the same direction of return for the next "
            "3–12 months. The '12-1' convention skips month t-1 to avoid "
            "contamination by the short-term reversal effect documented "
            "by Jegadeesh (1990).\n\n"
            "Behavioral explanations include: (1) under-reaction to news — "
            "investors anchor on prior prices and slowly incorporate "
            "fundamental information, (2) gradual diffusion of information "
            "through a network of investors, and (3) positive feedback "
            "trading by trend-following strategies. Risk-based explanations "
            "are less convincing since momentum crashes tend to occur in "
            "bear-market rebounds — exactly when risk premia should be high.\n\n"
            "Momentum is among the most robust factors empirically, holding "
            "across geographies, asset classes, and time periods, but it is "
            "prone to dramatic drawdowns ('momentum crashes') following "
            "market reversals."
        ),
        formula_tex=(
            r"MOM_i = \prod_{k=2}^{12}(1 + R_{i,\,t-k}) - 1"
            r"\quad\text{(cumulative return, months } t-12 \text{ to } t-2\text{)}"
        ),
        qspread_tex=(
            r"r_{MOM,\,t} = "
            r"\frac{1}{|W_t|}\sum_{i \in W_t} r_{i,t} "
            r"- \frac{1}{|L_t|}\sum_{i \in L_t} r_{i,t}"
            r"\quad W_t = \text{Winners (Q5)},\; L_t = \text{Losers (Q1)}"
        ),
        references=[
            "Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers. "
            "Journal of Finance, 48(1), 65–91.",
            "Carhart, M. M. (1997). On persistence in mutual fund performance. "
            "Journal of Finance, 52(1), 57–82.",
            "Daniel, K., & Moskowitz, T. J. (2016). Momentum crashes. "
            "Journal of Financial Economics, 122(2), 221–247.",
        ],
        intuition="Past 12-month winners keep winning for another 3-12 months; past losers keep losing.",
    ),

    "BP": FactorEntry(
        name="BP — Book-to-Price (Value)",
        category="Value",
        description=(
            "Book-to-price (B/P), also known as book-to-market (B/M), is the "
            "archetypal value factor. Fama and French (1992, 1993) showed that "
            "high-B/P stocks (value stocks) earn higher average returns than "
            "low-B/P stocks (growth stocks). Their three-factor model adds "
            "HML (High-Minus-Low) to the CAPM to capture this premium.\n\n"
            "Two competing explanations exist. The risk-based view holds that "
            "value stocks are distressed firms with high systematic risk: "
            "they are especially vulnerable in bad states of the world, and "
            "their high return compensates investors for bearing that risk. "
            "The mispricing view (Lakonishok et al., 1994) argues that "
            "investors naively extrapolate past earnings growth, overpaying "
            "for glamour stocks and underpricing value stocks.\n\n"
            "Empirically, HML has been weakened post-2000 as value "
            "underperformed growth — attributed to the rise of intangible "
            "assets not captured in book value, low interest rates favoring "
            "long-duration growth assets, and potential data-mining."
        ),
        formula_tex=(
            r"BP_i = \frac{BE_{i,\,t-1}}{ME_{i,\,t}}"
            r"\quad BE = \text{book equity},\; ME = \text{market equity}"
        ),
        qspread_tex=(
            r"HML_t = \frac{1}{2}\Bigl(r_{\text{Small/High}} + r_{\text{Big/High}}\Bigr)"
            r"- \frac{1}{2}\Bigl(r_{\text{Small/Low}} + r_{\text{Big/Low}}\Bigr)"
        ),
        references=[
            "Fama, E. F., & French, K. R. (1992). The cross-section of expected stock returns. "
            "Journal of Finance, 47(2), 427–465.",
            "Fama, E. F., & French, K. R. (1993). Common risk factors in returns on stocks and bonds. "
            "Journal of Financial Economics, 33(1), 3–56.",
            "Lakonishok, J., Shleifer, A., & Vishny, R. W. (1994). Contrarian investment. "
            "Journal of Finance, 49(5), 1541–1578.",
        ],
        intuition="Cheap stocks (high book relative to price) outperform glamour stocks over the long run.",
    ),

    "Beta": FactorEntry(
        name="Beta — Market Beta (Low-Beta Anomaly)",
        category="Risk",
        description=(
            "CAPM (Sharpe, 1964; Lintner, 1965) predicts a positive linear "
            "relation between a stock's market beta and its expected return: "
            "higher systematic risk should earn higher compensation. "
            "Empirically, however, this relation is flat or even negative "
            "— a finding known as the 'low-beta anomaly' or 'betting against beta' (BAB).\n\n"
            "Frazzini and Pedersen (2014) attribute the anomaly to leverage "
            "constraints: many investors (mutual funds, pension funds) face "
            "restrictions on borrowing, so they tilt toward high-beta assets "
            "to achieve their return targets, bidding them up and reducing "
            "future returns. Constrained investors accept negative alpha on "
            "high-beta assets because they cannot lever low-beta assets to "
            "match the desired volatility profile.\n\n"
            "An alternative explanation is lottery-preference: high-beta "
            "stocks exhibit skewed, lottery-like return distributions that "
            "are overpriced by investors with preferences for positive skewness "
            "(Barberis and Huang, 2008)."
        ),
        formula_tex=(
            r"\hat{\beta}_i = \frac{\widehat{\text{Cov}}(R_i, R_m)}{\widehat{\text{Var}}(R_m)}"
            r"= \frac{\sum_{t=1}^{T}(R_{i,t}-\bar{R}_i)(R_{m,t}-\bar{R}_m)}"
            r"{\sum_{t=1}^{T}(R_{m,t}-\bar{R}_m)^2}"
        ),
        qspread_tex=(
            r"BAB_t = \frac{1}{\beta^L_t} r^L_t - \frac{1}{\beta^H_t} r^H_t"
            r"\quad\text{(Frazzini-Pedersen levered L/S)}"
        ),
        references=[
            "Sharpe, W. F. (1964). Capital asset prices. Journal of Finance, 19(3), 425–442.",
            "Black, F., Jensen, M. C., & Scholes, M. (1972). The capital asset pricing model. "
            "Studies in the Theory of Capital Markets, 79–121.",
            "Frazzini, A., & Pedersen, L. H. (2014). Betting against beta. "
            "Journal of Financial Economics, 111(1), 1–23.",
        ],
        intuition="Low-beta stocks deliver better risk-adjusted returns than high-beta stocks — the SML is too flat.",
    ),

    "LogMktCap": FactorEntry(
        name="LogMktCap — Size (Small-Cap Premium)",
        category="Size",
        description=(
            "Banz (1981) documented that small-capitalization stocks earn "
            "higher average returns than large-capitalization stocks. "
            "Fama and French (1993) formalize this as the SMB factor "
            "(Small-Minus-Big). The small-cap premium may reflect: "
            "(1) illiquidity risk — small stocks are harder to trade and "
            "command a liquidity premium; (2) greater sensitivity to "
            "aggregate economic conditions (systematic distress risk); "
            "(3) limits to arbitrage — institutional investors avoid small "
            "stocks due to capacity constraints, allowing mispricing to persist.\n\n"
            "The size premium has been weak in recent decades (post-1980 "
            "out-of-sample), partly because the original finding attracted "
            "capital that arbitraged away the anomaly, and partly because "
            "the premium is concentrated in very small (micro-cap) stocks "
            "with high transaction costs. Within S&P 500, the size effect "
            "may reverse: the largest mega-caps benefit from passive-flow "
            "effects and index inclusion premia.\n\n"
            "Note: In our factor definition, Q5 = highest LogMktCap (largest "
            "firms) and Q1 = lowest (smallest). The Q-spread (Q5-Q1) is "
            "therefore a large-minus-small spread, the opposite sign to SMB."
        ),
        formula_tex=(
            r"\text{LogMktCap}_i = \log\!\bigl(P_{i,t}\times N_{i,t}\bigr)"
            r"\quad P = \text{price},\; N = \text{shares outstanding}"
        ),
        qspread_tex=(
            r"SMB_t = \frac{1}{3}\Bigl(r_{\text{S/H}}+r_{\text{S/N}}+r_{\text{S/L}}\Bigr)"
            r"-\frac{1}{3}\Bigl(r_{\text{B/H}}+r_{\text{B/N}}+r_{\text{B/L}}\Bigr)"
            r"\quad\text{(CapitalIQ Q-spread} = -SMB\text{)}"
        ),
        references=[
            "Banz, R. W. (1981). The relationship between return and market value of common stocks. "
            "Journal of Financial Economics, 9(1), 3–18.",
            "Fama, E. F., & French, K. R. (1993). Common risk factors in returns on stocks and bonds. "
            "Journal of Financial Economics, 33(1), 3–56.",
            "Asness, C. S., Frazzini, A., Israel, R., & Moskowitz, T. J. (2018). Size matters, if you control your junk. "
            "Journal of Financial Economics, 129(3), 479–509.",
        ],
        intuition="Smaller stocks earn a return premium, but the effect is largely concentrated in micro-caps.",
    ),

    "AnnVol12M": FactorEntry(
        name="AnnVol12M — Annualized Volatility (Low-Vol Anomaly)",
        category="Risk / Volatility",
        description=(
            "The low-volatility anomaly — that low-risk stocks outperform "
            "high-risk stocks — directly contradicts the risk-return "
            "tradeoff predicted by CAPM. Ang, Hodrick, Xing, and Zhang (2006) "
            "documented a strong negative relation between idiosyncratic "
            "volatility and subsequent returns, a finding that holds across "
            "international markets.\n\n"
            "The leading explanations are: (1) Lottery-preference / "
            "skewness demand — high-volatility stocks tend to have fat right "
            "tails (occasional jackpot outcomes) that attract investors with "
            "cumulative-prospect-theory preferences, bidding them up and "
            "reducing prospective returns. (2) Leverage constraints — as in the "
            "beta anomaly, constrained investors buy high-vol stocks to achieve "
            "desired return targets, overpricing them. (3) Analyst coverage "
            "and attention — high-vol stocks attract more retail attention "
            "and momentum chasers.\n\n"
            "In a quintile sort, Q5 consists of the highest-volatility stocks "
            "and Q1 the lowest. The Q-spread (Q5 - Q1) is typically negative "
            "— high vol underperforms low vol — which is the low-volatility "
            "premium in disguise."
        ),
        formula_tex=(
            r"\hat{\sigma}_{i,\,12M} = \sqrt{252}\cdot"
            r"\sqrt{\frac{1}{T-1}\sum_{d=1}^{T}(r_{i,d}-\bar{r}_i)^2}"
            r"\quad T \approx 252 \text{ trading days}"
        ),
        qspread_tex=(
            r"r_{Vol,\,t} = "
            r"\frac{1}{|Q5_t|}\sum_{i \in Q5_t} r_{i,t} "
            r"- \frac{1}{|Q1_t|}\sum_{i \in Q1_t} r_{i,t}"
            r"\quad\text{Q-spread typically} < 0 \text{ (low-vol wins)}"
        ),
        references=[
            "Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). The cross-section of "
            "volatility and expected returns. Journal of Finance, 61(1), 259–299.",
            "Baker, M., Bradley, B., & Wurgler, J. (2011). Benchmarks as limits to arbitrage: "
            "Understanding the low-volatility anomaly. Financial Analysts Journal, 67(1), 40–54.",
        ],
        intuition="High-volatility stocks consistently underperform — the market over-pays for risk and excitement.",
    ),
}


# ── Portfolio construction methodology ────────────────────────────────────────

PORTFOLIO_CONSTRUCTION = {
    "universe": (
        "S&P 500 constituent stocks, observed at each month-end. "
        "The S&P 500 universe is chosen for its liquidity and data availability; "
        "results may differ for the broader market (as evidenced by the "
        "cross-validation with Fama-French all-stock data)."
    ),

    "sort_formula_tex": (
        r"\text{Quintile}_{i,t} = \text{qcut}\!\left(X_{i,t},\; q=5\right)"
        r"\quad X_{i,t} = \text{winsorized characteristic at } p_{1\%},\,p_{99\%}"
    ),

    "equal_weight_formula_tex": (
        r"w_{i,t}^{Qq} = \frac{\mathbf{1}[i \in Qq_t]}{|Qq_t|}"
        r"\quad q \in \{1,2,3,4,5\}"
    ),

    "qspread_formula_tex": (
        r"r_{Q,t+1} = \sum_{i \in Q5_t} w_{i,t}^{Q5}\,r_{i,t+1}"
        r"- \sum_{i \in Q1_t} w_{i,t}^{Q1}\,r_{i,t+1}"
    ),

    "steps": [
        ("Universe", "S&P 500 stocks at month-end t. Require at least 6 months of "
         "price history and non-missing characteristic value."),
        ("Winsorize", "Clip each characteristic cross-sectionally at the 1st and 99th "
         "percentile to reduce influence of extreme outliers."),
        ("Quintile sort", "Rank stocks by the winsorized characteristic and assign to "
         "5 equal-count buckets (Q1 = bottom 20%, Q5 = top 20%)."),
        ("Equal-weight", "Within each quintile, assign equal weight 1/Nq to each stock."),
        ("Implementation lag", "Use characteristics from month t to form portfolios "
         "held from month t+1 (one-month lag to avoid look-ahead bias)."),
        ("Q-spread", "Long Q5 (high characteristic), short Q1 (low characteristic). "
         "This is the return attributed to the factor."),
        ("Monthly reform", "Repeat every month end. Turnover is 100% per year on average "
         "for momentum; lower for slower-moving factors like BP."),
    ],

    "annualized_sharpe_tex": (
        r"\text{SR} = \frac{\bar{r}_{Q}}{\hat{\sigma}_{Q}} \times \sqrt{12}"
        r"\quad\text{where } \bar{r}_Q = \frac{1}{T}\sum_{t=1}^T r_{Q,t}"
    ),

    "t_stat_tex": (
        r"t = \frac{\bar{r}_Q}{\hat{\sigma}_Q / \sqrt{T}}"
        r"\xrightarrow{H_0:\,\mu=0} t_{T-1}"
    ),
}
