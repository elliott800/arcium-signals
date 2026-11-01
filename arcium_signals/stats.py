"""Statistics for one component's run: trading results plus the component's own predictive power."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (1, 5, 20)


def bars_per_year(index: pd.DatetimeIndex) -> float:
    step = pd.Series(index).diff().median()
    if pd.isna(step) or step.total_seconds() <= 0:
        return 252.0
    # FX trades ~5 days a week: 260 days x bars per day
    return 260 * 86400 / step.total_seconds()


def information(close: pd.Series, x: pd.Series | None, signal: pd.Series) -> dict:
    """Rank correlation of the component's output (or its signal) with the forward log return."""
    src = x if x is not None else signal
    out = {}
    for h in HORIZONS:
        fwd = np.log(close).shift(-h) - np.log(close)
        pair = pd.concat([src, fwd], axis=1).dropna()
        pair = pair[pair.iloc[:, 0] != 0] if x is None else pair
        out[f'ic_{h}'] = None if len(pair) < 30 else round(float(pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())), 4)
    return out


def summary(bt: pd.DataFrame, tr: pd.DataFrame, close: pd.Series, raw: pd.Series | None, signal: pd.Series) -> dict:
    pnl, eq = bt['pnl'], bt['equity']
    ann = bars_per_year(bt.index)
    pos = bt['position']

    def sharpe(x):
        sd = x.std()
        return None if not sd else round(float(x.mean() / sd * np.sqrt(ann)), 3)

    return {
        'bars': int(len(bt)),
        'total_return': round(float(eq.iloc[-1] - 1.0), 6),
        'sharpe': sharpe(pnl),
        # before costs: the component's own edge, which costs on short bars can hide
        'gross_return': round(float(bt['gross'].sum()), 6),
        'gross_sharpe': sharpe(bt['gross']),
        'cost_paid': round(float(bt['cost'].sum()), 6),
        'max_drawdown': round(float((eq - eq.cummax()).min()), 6),
        'trades': int(len(tr)),
        'hit_rate': None if tr.empty else round(float((tr['pnl'] > 0).mean()), 4),
        'avg_trade_bars': None if tr.empty else round(float(tr['bars'].mean()), 2),
        'exposure': round(float((pos != 0).mean()), 4),
        'turnover': round(float(pos.diff().abs().mean()), 4),
        'long_share': None if tr.empty else round(float((tr['side'] > 0).mean()), 4),
        **information(close, raw, signal),
    }
