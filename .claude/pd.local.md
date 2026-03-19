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
memory_injection_limit: 50
# Enable semantic (vector + keyword) search for memory retrieval
memory_semantic_enabled: true
# Weights for memory ranking (must sum to 1.0)
memory_vector_weight: 0.5
memory_keyword_weight: 0.2
memory_prominence_weight: 0.3
# Embedding provider for semantic search: gemini | openai
memory_embedding_provider: gemini
# Model ID for embedding generation
memory_embedding_model: gemini-embedding-001
# Keyword extraction provider: auto | gemini | openai
memory_keyword_provider: auto
# How model-initiated memory captures are handled: ask-first | silent | disabled
memory_model_capture_mode: ask-first
# Max silent captures per session (only applies when capture mode is "silent")
memory_silent_capture_budget: 5
---
