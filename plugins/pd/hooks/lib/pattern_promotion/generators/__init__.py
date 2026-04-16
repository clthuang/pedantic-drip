"""Per-target generators for pattern promotion.

Each module in this package exposes `generate(entry, target_meta) -> DiffPlan`
plus a validator (`validate_feasibility` for hook; `validate_target_meta` for
skill/agent/command). Validators are invoked by the `generate` CLI subcommand
at entry; on schema failure the CLI returns `status="need-input"` per the
Subprocess Serialization Contract (design TD-3 / I-8).

Every generated artifact carries a TD-8 marker comment naming the KB entry it
was promoted from. Phase 3 Stage 1 pre-flight scans for these markers to
detect prior partial-run collisions.
"""
