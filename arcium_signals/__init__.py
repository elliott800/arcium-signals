"""arcium-signals test unit: analyse one Arcium seed component at a time on a slim engine."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, 'vendor')

# The seed components import their siblings as top-level packages (features.momentum,
# super_classes.feature_base), exactly as inside a silo.
for _p in (os.path.join(VENDOR, 'seed'), VENDOR):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
