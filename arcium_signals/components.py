"""
Find the installed seed components and turn any one of them into a -1..+1 signal.

kind       what it is                                       how it becomes a signal
feature    FeatureBase subclass: transform() -> a value/bar  rolling z-score / 2, clipped to +-1 (or its sign)
alpha      Signal subclass: algorithm() -> -1/0/+1          as is
sampler    *Sampler class: picks event bars                 at each event take the side of the last
                                                             side_window bars' move (momentum) or its
                                                             opposite (reversal), hold for `hold` bars
indicator  functions in indicators/                         listed with the reason when they can't run

Every signal is causal: the value at bar t uses bars up to t only. The engine trades it from t+1.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import numpy as np
import pandas as pd

import arcium_signals  # noqa: F401  (puts vendor/ on sys.path)
from arcium_signals.signal_shim import Signal, _Instrument

KINDS = ('feature', 'alpha', 'sampler', 'indicator')
_PKG = {'feature': 'features', 'alpha': 'alpha_models', 'sampler': 'event_samplers', 'indicator': 'indicators'}


def _modules(kind: str):
    """(module, error) for each module of a component package; error is set when it doesn't import."""
    try:
        pkg = importlib.import_module(_PKG[kind])
    except Exception as exc:
        return [(None, f'{_PKG[kind]}: {type(exc).__name__}: {exc}')]
    out = []
    for m in pkgutil.iter_modules(pkg.__path__):
        try:
            out.append((importlib.import_module(f'{_PKG[kind]}.{m.name}'), None))
        except Exception as exc:
            out.append((None, f'{_PKG[kind]}.{m.name}: {type(exc).__name__}: {exc}'))
    return out


def discover() -> dict[str, dict[str, object]]:
    """{kind: {name: class or 'unavailable: reason'}}."""
    from super_classes.feature_base import FeatureBase
    found: dict[str, dict[str, object]] = {k: {} for k in KINDS}
    for kind in KINDS:
        for mod, err in _modules(kind):
            if err:
                found[kind][err.split(':')[0].split('.')[-1]] = 'unavailable: ' + err.split(': ', 1)[1]
                continue
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if obj.__module__ != mod.__name__:
                    continue
                if kind == 'feature' and issubclass(obj, FeatureBase) and obj is not FeatureBase:
                    # a feature named in __init__ (cross_instrument) still has the base's default name
                    own = obj.__dict__.get('name')
                    found[kind][own if isinstance(own, str) else mod.__name__.split('.')[-1]] = obj
                elif kind == 'alpha' and issubclass(obj, Signal) and obj is not Signal:
                    found[kind][name] = obj
                elif kind == 'sampler' and name.endswith('Sampler'):
                    found[kind][name[:-len('Sampler')].lower()] = obj
            if kind == 'indicator':
                found[kind][mod.__name__.split('.')[-1]] = 'unavailable: indicator functions take legacy asset ' \
                                                           'objects; no signal adapter yet'
    return found


def _zsignal(x: pd.Series, window: int, mapping: str) -> pd.Series:
    if mapping == 'sign':
        return np.sign(x).fillna(0.0)
    mu = x.rolling(window, min_periods=window // 2).mean()
    sd = x.rolling(window, min_periods=window // 2).std()
    return ((x - mu) / sd.replace(0, np.nan) / 2).clip(-1, 1).fillna(0.0)


def run_component(kind: str, name: str, bars: dict[str, pd.DataFrame], instrument: str,
                  params: dict | None = None, init: dict | None = None, opts: dict | None = None):
    """-> (signal, raw output, details). raw is the component's own output where it has one (for IC)."""
    params, init, opts = params or {}, init or {}, opts or {}
    comps = discover()[kind]
    if name not in comps:
        raise SystemExit(f'no {kind} named {name!r}; have: {", ".join(sorted(comps))}')
    cls = comps[name]
    if isinstance(cls, str):
        raise SystemExit(f'{kind} {name} is {cls}')
    levels = bars[instrument]
    close = levels['close']

    if kind == 'feature':
        comp = cls(**init)
        cluster = {'levels': levels.reset_index(), '_levels': levels.reset_index(), **{k: v['close'] for k, v in bars.items()}}
        merged = {**getattr(comp, 'default_params', {}), **params}
        raw = comp(cluster, merged, close)
        if not isinstance(raw, pd.Series):
            raw = pd.Series(np.asarray(raw, dtype=float), index=close.index[-len(raw):])
        elif not isinstance(raw.index, pd.DatetimeIndex) and len(raw) == len(close):
            raw = pd.Series(raw.to_numpy(dtype=float), index=close.index)   # bar features index by position
        raw = raw.reindex(close.index).astype(float)
        if opts.get('invert'):
            raw = -raw
        sig = _zsignal(raw, int(opts.get('z_window', 100)), opts.get('map', 'z'))
        return sig, raw, {'params': merged, 'init': init, 'map': opts.get('map', 'z')}

    if kind == 'alpha':
        comp = cls(_Instrument(instrument, levels.reset_index()))
        comp.params = {**comp.default_params(), **params}
        sig = comp.produce_signal()
        sig.index = close.index[sig.index]
        sig = sig.reindex(close.index).fillna(0.0).clip(-1, 1)
        if opts.get('invert'):
            sig = -sig
        return sig, None, {'params': comp.params, 'space': comp.space}

    # sampler
    if not init and name == 'cusum':
        init = {'threshold': float(np.log(close).diff().std() * 3)}
    if not init and name == 'bar':
        init = {'ga_counter': 10}   # its own default (1) keeps every bar: no sampling to analyse
    comp = cls(**init)
    work = levels.reset_index()
    work['_pos'] = np.arange(len(work))
    if hasattr(comp, 'sample') and name == 'cusum':
        events = close.index.get_indexer(comp.sample(close))
    else:
        out = comp.transform(work)
        if '_pos' in out.columns:
            events = out['_pos'].to_numpy()
        elif 'time' in out.columns:
            events = close.index.get_indexer(pd.to_datetime(out['time']))
        else:
            raise SystemExit(f'sampler {name}: cannot map its output back to bars')
        if name == 'tstat' and len(events) == len(work):
            events = np.array([], dtype=int)   # tstat falls back to every bar when nothing passes
    events = np.unique(events[events >= 0])
    w, hold = int(opts.get('side_window', 5)), int(opts.get('hold', 10))
    move = np.log(close).diff(w).to_numpy()
    side = -1.0 if opts.get('side', 'momentum') == 'reversal' else 1.0
    sig = np.zeros(len(close))
    for e in events:
        if np.isfinite(move[e]) and move[e] != 0:
            sig[e:e + hold] = side * np.sign(move[e])
    mask = pd.Series(0.0, index=close.index)
    mask.iloc[events] = 1.0
    return pd.Series(sig, index=close.index), mask, {'init': init, 'events': int(len(events)),
                                                     'side': opts.get('side', 'momentum'), 'hold': hold,
                                                     'side_window': w}
