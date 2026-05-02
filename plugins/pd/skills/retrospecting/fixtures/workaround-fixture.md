# Implementation Log (Synthetic Fixture for FR-3 Testing)

## Task T-positive: Validate ISO timestamp parsing

**Decision:** Use `dateutil.parser` instead of `datetime.fromisoformat` for ISO-8601 parsing because the latter rejects `Z` suffix on Python <3.11.

Initial attempt failed: `datetime.fromisoformat('2026-01-01T00:00:00Z')` raised ValueError.
Tried again with regex preprocessing: replace 'Z' with '+00:00'. Still failed because tests on macOS Python 3.10 hit the same path.
Reverted to `dateutil.parser.isoparse` which handles both Z and offset suffixes uniformly.

Files changed: `module_a.py`, `module_b.py`

## Task T-control: Add config field

**Decision:** Add `memory_decay_enabled` boolean to config defaults.

Files changed: `config.py`
