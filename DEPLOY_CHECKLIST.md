# Release checklist: arcium-signals (test unit)

Not deployed to a server: people install it with `install.py`. Tick every box before tagging or sharing.

## Before
- [ ] On `main`, nothing uncommitted, everything pushed. No force-push
- [ ] `vendor/` is not committed (`git ls-files vendor` prints nothing)
- [ ] The `install.py` allowlist reviewed: only seed components and the slim engine. No production engine, GA, classifier pipeline, mixers or risk code (patent-safe)
- [ ] `python install.py` into a clean folder, then `python -m pytest tests -q` passes
- [ ] README examples run as written

## After
- [ ] A fresh clone plus `install.py` works on another machine
