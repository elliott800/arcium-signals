"""
The test unit's slim trade engine: one instrument, one signal, fixed size, no risk management.

The position held over bar t -> t+1 is the signal at bar t (already causal). P&L is position x
return, minus spread_bps on every change of position. Fixed notional (no compounding), so the
equity curve shows the component itself, not a sizing scheme.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def backtest(close: pd.Series, signal: pd.Series, spread_bps: float = 1.0) -> pd.DataFrame:
    pos = signal.reindex(close.index).fillna(0.0).clip(-1, 1)
    fwd = close.pct_change().shift(-1).fillna(0.0)
    cost = pos.diff().abs().fillna(pos.abs()) * spread_bps / 1e4
    gross = pos * fwd
    pnl = gross - cost
    return pd.DataFrame({'close': close, 'position': pos, 'gross': gross, 'cost': cost, 'pnl': pnl,
                         'equity': 1.0 + pnl.cumsum()})


def trades(bt: pd.DataFrame) -> pd.DataFrame:
    """One row per run of same-sign non-zero position: entry, exit, side, bars, pnl."""
    side = np.sign(bt['position'].to_numpy())
    rows, start = [], None
    for i in range(len(side) + 1):
        s = side[i] if i < len(side) else 0
        if start is not None and s != side[start]:
            seg = bt.iloc[start:i]
            rows.append({'entry': seg.index[0], 'exit': seg.index[-1], 'side': int(side[start]),
                         'bars': len(seg), 'pnl': float(seg['pnl'].sum())})
            start = None
        if start is None and s != 0:
            start = i
    return pd.DataFrame(rows, columns=['entry', 'exit', 'side', 'bars', 'pnl'])
