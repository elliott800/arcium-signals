"""Bars for the test unit: the installed canned demo bars, the Data Hub warehouse (hub.py), or a CSV of
time,open,high,low,close[,volume]."""
from __future__ import annotations

import os
import pickle

import pandas as pd

from arcium_signals import VENDOR

DEMO = os.path.join(VENDOR, 'demo', 'portfolio_data.pkl')


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'time' in df.columns:
        # tz-naive UTC, as the engine's bars are (the De Prado helpers reject tz-aware indexes)
        df.index = pd.to_datetime(df['time'], utc=True).dt.tz_localize(None)
        df = df.drop(columns=['time'])
    df.index.name = 'time'
    if 'volume' not in df.columns:
        df['volume'] = 0.0
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df[~df.index.duplicated(keep='last')].sort_index()


def demo_instruments() -> list[str]:
    if not os.path.isfile(DEMO):
        return []
    with open(DEMO, 'rb') as f:
        return sorted(pickle.load(f)['data'].keys())


def load(source: str = 'demo', instrument: str = 'EUR_USD', rate: str = 'M1', start=None, end=None) -> dict[str, pd.DataFrame]:
    """{instrument: bars} — every instrument available, so cross-instrument features can see the others.
    source 'hub' (OANDA) or 'hub:<source>' (hub.SOURCES) reads that instrument's `rate` bars from the warehouse."""
    if source == 'hub' or source.startswith('hub:'):
        from arcium_signals import hub
        return {instrument: _tidy(hub.bars(instrument, rate, source.partition(':')[2] or 'oanda', start, end).reset_index())}
    if source == 'demo':
        if not os.path.isfile(DEMO):
            raise SystemExit('no demo bars: run python install.py first')
        with open(DEMO, 'rb') as f:
            data = pickle.load(f)['data']
        if instrument not in data:
            raise SystemExit(f'{instrument} not in the demo bars: {sorted(data)}')
        return {k: _tidy(v) for k, v in data.items()}
    return {instrument: _tidy(pd.read_csv(source))}
