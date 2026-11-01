"""
install.py — install seed components from an Arcium silo into vendor/ for the test unit.

    python install.py                                   default silo: ../arcium_controller/.../silo/mean_reversion
    python install.py --from <silo dir>

Copies ONLY the analysable seed components and the interfaces they import:

    seed/package/features, event_samplers, alpha_models, indicators  -> vendor/seed/
    primary/super_classes/feature_base.py                            -> vendor/super_classes/
    getVol, fracDiff_FFD, ema_diff (+ getWeights_FFD) from deprado_ml -> vendor/primary_classifier_classes/deprado_ml.py
    primary/demo/portfolio_data.pkl (canned bars)                    -> vendor/demo/

The engine, GA, classifier pipeline, mixers and risk management are never copied: Signal
is a small shim written here (arcium_signals/signal_shim.py), and the backtest is this repo's
own slim engine. vendor/ is git-ignored, so no Arcium code is ever committed to this repo.
vendor/INSTALLED.json records the source silo and each file's sha256, to match the foundation seal.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, 'vendor')
DEFAULT_SILO = os.path.join(HERE, '..', 'arcium_controller', 'elliotthamilton800', 'silo', 'mean_reversion')

COMPONENT_DIRS = ('features', 'event_samplers', 'alpha_models', 'indicators')
DEPRADO_FUNCS = ('getVol', 'fracDiff_FFD', 'ema_diff')


def sha(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def extract_functions(src_path: str, wanted: tuple[str, ...]) -> str:
    """The named top-level functions plus the module functions they call, with the module's imports."""
    tree = ast.parse(open(src_path, encoding='utf-8').read())
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    need, todo = set(), list(wanted)
    while todo:
        name = todo.pop()
        if name in need or name not in defs:
            continue
        need.add(name)
        todo += [n.id for n in ast.walk(defs[name]) if isinstance(n, ast.Name) and n.id in defs]
    missing = set(wanted) - need
    if missing:
        raise SystemExit(f'{src_path} lacks {sorted(missing)}')
    imports = [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    body = [ast.get_source_segment(open(src_path, encoding='utf-8').read(), defs[n]) for n in defs if n in need]
    return ('# Extracted by arcium-signals install.py: only the functions the seed features use.\n'
            + '\n'.join(imports) + '\n\n\n' + '\n\n\n'.join(body) + '\n')


def install(silo: str) -> dict:
    silo = os.path.abspath(silo)
    seed = os.path.join(silo, 'seed', 'package')
    primary = os.path.join(silo, 'primary')
    if not os.path.isdir(seed):
        raise SystemExit(f'not a silo (no seed/package): {silo}')
    if os.path.isdir(VENDOR):
        shutil.rmtree(VENDOR)
    files: dict[str, str] = {}

    def put(src: str, rel: str) -> None:
        dst = os.path.join(VENDOR, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        files[rel.replace(os.sep, '/')] = sha(src)

    for d in COMPONENT_DIRS:
        for name in sorted(os.listdir(os.path.join(seed, d))):
            if name.endswith('.py'):
                put(os.path.join(seed, d, name), os.path.join('seed', d, name))

    put(os.path.join(primary, 'super_classes', 'feature_base.py'), os.path.join('super_classes', 'feature_base.py'))
    shim = os.path.join(HERE, 'arcium_signals', 'signal_shim.py')
    with open(os.path.join(VENDOR, 'super_classes', 'signal_base.py'), 'w', encoding='utf-8') as f:
        f.write('from arcium_signals.signal_shim import Signal  # noqa: F401  (test-unit shim, not the engine)\n')
    for pkg in ('super_classes', 'primary_classifier_classes'):
        os.makedirs(os.path.join(VENDOR, pkg), exist_ok=True)
        open(os.path.join(VENDOR, pkg, '__init__.py'), 'w').close()

    dml = os.path.join(primary, 'primary_classifier_classes', 'deprado_ml.py')
    with open(os.path.join(VENDOR, 'primary_classifier_classes', 'deprado_ml.py'), 'w', encoding='utf-8') as f:
        f.write(extract_functions(dml, DEPRADO_FUNCS))
    files['primary_classifier_classes/deprado_ml.py'] = sha(dml) + ' (extract: ' + ', '.join(DEPRADO_FUNCS) + ')'

    demo = os.path.join(primary, 'demo', 'portfolio_data.pkl')
    if os.path.isfile(demo):
        put(demo, os.path.join('demo', 'portfolio_data.pkl'))

    record = {'installed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'silo': silo,
              'shim': sha(shim), 'files': files}
    with open(os.path.join(VENDOR, 'INSTALLED.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=1)
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='silo', default=DEFAULT_SILO, help='silo directory (has seed/package and primary/)')
    rec = install(ap.parse_args().silo)
    print(f"installed {len(rec['files'])} files from {rec['silo']} into vendor/")


if __name__ == '__main__':
    main()
