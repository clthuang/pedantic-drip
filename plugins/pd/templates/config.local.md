---
# Project — paths and integration
# Root directory for features, brainstorms, and projects
artifacts_root: docs
# Merge target branch. "auto" detects from remote HEAD, falls back to "main"
base_branch: auto
# Path to release script, run after merge in /finish-feature. Empty to skip
release_script:
# Comma-separated documentation tiers: user-guide, dev-guide, technical
doc_tiers: user-guide,dev-guide,technical

# Workflow — automation and review
# Fully autonomous mode — auto-selects at prompts, chains phases end-to-end
yolo_mode: false
# Max AskUserQuestion blocks YOLO guard will auto-answer before stopping
yolo_max_stop_blocks: 50
# API usage limit ($). 0 = unlimited. Pauses YOLO when reached
yolo_usage_limit: 0
# Wait for cooldown when usage limit hit (true) or stop permanently (false)
yolo_usage_wait: true
# Cooldown in seconds before resuming after usage limit hit
yolo_usage_cooldown: 18000
# Require plan-reviewer gate before exiting plan mode
plan_mode_review: true
# Max parallel Task (subagent) dispatches per batch
max_concurrent_agents: 5
# Cron expression for scheduled doctor runs (desktop tier only). Empty to disable. Example: '0 */4 * * *' runs every 4 hours.
doctor_schedule:

# UI Server — Kanban board
# Auto-start UI server on session start
ui_server_enabled: true
# Port for the UI server
ui_server_port: 8718
---
