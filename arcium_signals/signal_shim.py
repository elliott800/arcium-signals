"""
Minimal stand-in for the engine's Signal base, so alpha models run without the engine.

An alpha model defines setup() (self.space: {param: [min, max, step]}) and algorithm(), which
reads self.data['levels'] up to the current bar and returns -1, 0 or +1. produce_signal() reveals
the bars one at a time, exactly as a live engine would, so the series has no lookahead.
"""
from __future__ import annotations

import pandas as pd


class _Instrument:
    def __init__(self, name: str, levels: pd.DataFrame):
        self.name = name
        self.data = {'levels': levels}


class Signal:
    def __init__(self, instrument, fitness='sr', drop_window=0):
        self.instrument = instrument
        self.data = instrument.data
        self.space: dict = {}
        self.params: dict = {}
        self.setup()

    def setup(self):
        pass

    def algorithm(self):
        return 0

    def default_params(self) -> dict:
        """Middle of each parameter's range, on its step grid."""
        out = {}
        for k, (lo, hi, step) in self.space.items():
            v = lo + round(((hi - lo) / 2) / step) * step
            out[k] = int(v) if float(v).is_integer() and isinstance(step, int) else float(v)
        return out

    def warmup(self) -> int:
        ints = [v for v in self.params.values() if isinstance(v, int)]
        return max(ints) if ints else 0

    def produce_signal(self) -> pd.Series:
        """One value per bar from bar warmup()+1 on, indexed like the levels."""
        if not self.params:
            self.params = self.default_params()
        levels = self.data['levels']
        dw = self.warmup()
        out = []
        try:
            for i in range(dw + 1, len(levels) + 1):
                self.data['levels'] = levels.iloc[:i]
                try:
                    sig = self.algorithm()
                except Exception:
                    sig = 0.0
                out.append(float(sig) if sig is not None else 0.0)
        finally:
            self.data['levels'] = levels
        return pd.Series(out, index=levels.index[dw:], dtype=float)
