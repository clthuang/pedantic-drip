---
# Project — paths and integration
# Root directory for features, brainstorms, projects, knowledge-bank
artifacts_root: docs
# Merge target branch. "auto" detects from remote HEAD, falls back to "main"
base_branch: auto
# Path to release script, run after merge in /finish-feature. Empty to skip
release_script: scripts/release.sh --ci
# Comma-separated dirs to scan for knowledge bank backfill. Empty to skip
backfill_scan_dirs:
# Comma-separated documentation tiers: user-guide, dev-guide, technical
doc_tiers: user-guide,dev-guide,technical

# Workflow — automation and review
# Fully autonomous mode — auto-selects at prompts, chains phases end-to-end
yolo_mode: true
# Max AskUserQuestion blocks YOLO guard will auto-answer before stopping
yolo_max_stop_blocks: 50
# API usage limit ($). 0 = unlimited. Pauses YOLO when reached
yolo_usage_limit: 0
# Wait for cooldown when usage limit hit (true) or stop permanently (false)
yolo_usage_wait: true
# Cooldown in seconds before resuming after usage limit hit
yolo_usage_cooldown: 18000
# Secretary activation mode: manual | aware | yolo
activation_mode: manual
# Require plan-reviewer gate before exiting plan mode
plan_mode_review: true
# Max parallel Task (subagent) dispatches per batch
max_concurrent_agents: 5

# Memory — cross-session learning injection
# Inject memory entries into session context at start
memory_injection_enabled: true
# Max memory entries injected per session
memory_injection_limit: 20
# Enable semantic (vector + keyword) search for memory retrieval
memory_semantic_enabled: true
# Weights for memory ranking (must sum to 1.0)
memory_vector_weight: 0.5
memory_keyword_weight: 0.2
memory_prominence_weight: 0.3
# Minimum relevance score for memory injection (0.0-1.0)
memory_relevance_threshold: 0.3
# Embedding provider for semantic search: gemini
memory_embedding_provider: gemini
# Model ID for embedding generation
memory_embedding_model: gemini-embedding-001
# How model-initiated memory captures are handled: ask-first | silent | disabled
memory_model_capture_mode: ask-first
# Max silent captures per session (only applies when capture mode is "silent")
memory_silent_capture_budget: 5
# Cosine similarity threshold for near-duplicate detection (0.0-1.0)
memory_dedup_threshold: 0.90
# Minimum observation count a KB entry must have to qualify for /pd:promote-pattern.
# Raise if enumeration floods (>20 entries); lower if no entries qualify (0 entries).
memory_promote_min_observations: 3
# Feature 101 FR-4: use-gate threshold for low→medium confidence upgrade
# (influence_count + recall_count >= K_USE, with influence_count >= 1 floor).
# K_OBS_HIGH and K_USE_HIGH are auto-derived as K_OBS*2 and K_USE*2 respectively.
memory_promote_use_signal: 5
# cosine similarity threshold for influence matching; lower = more permissive; range [0.0, 1.0] clamped
memory_influence_threshold: 0.55
# contribution of influence to ranking prominence; coefficient in _prominence formula; NOT auto-renormalized — raise only by subtracting from other weights so sum stays ≤1.0
memory_influence_weight: 0.05
# emit per-dispatch hit-rate diagnostics to ~/.claude/pd/memory/influence-debug.log
memory_influence_debug: true
# inject memory digest into complete_phase responses so orchestrator sees fresh
# entries at phase boundaries; disable to revert to session-start-only memory
memory_refresh_enabled: true
# max memory entries in per-phase refresh digest; clamped to [1, 20]; each
# entry description capped at 240 chars
memory_refresh_limit: 5
# enable tiered confidence decay on session-start; set to true to opt in
memory_decay_enabled: false
# days without recall before high → medium; clamped to [1, 365]
memory_decay_high_threshold_days: 30
# days without recall before medium → low; clamped to [1, 365]; SHOULD be ≥ memory_decay_high_threshold_days, otherwise medium decays faster than high (allowed but warned)
memory_decay_medium_threshold_days: 60
# days after created_at before a never-recalled entry becomes eligible; clamped to [0, 365]
memory_decay_grace_period_days: 14
# when true, report what would be demoted without modifying the DB; useful for measuring impact before enabling
memory_decay_dry_run: false
# Feature 102 FR-2: per-Stop-tick cap on candidates emitted by capture-on-stop.sh; overflow logged + discarded
memory_capture_session_cap: 5
---
