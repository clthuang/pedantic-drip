---
# Project — paths and integration
# Root directory for features, brainstorms, and projects
artifacts_root: docs
# Merge target branch. "auto" detects from remote HEAD, falls back to "main"
base_branch: auto
# Path to release script, run after merge in /finish-feature. Empty to skip
release_script: scripts/release.sh --ci
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
---
