---
description: Mark a feature abandoned, with the user's reason, and offer branch cleanup
argument-hint: "[--feature=<id>]"
---

# /pd:abandon-feature

Ends a feature outside the phase sequence. The feature is resolved as the `pd:workflow-transitions` skill's phase entry does.

1. **Confirm and ask the reason** through AskUserQuestion. An already `done` or `abandoned` feature is reported, not abandoned again.
2. **Record it:** append a `decision` entry (`Q: abandon <id>?` with the user's answer, verbatim), set `status: abandoned`, overwrite `## Now` with the reason, and commit `abandon: <id>`. A feature listed in a plan's `roadmap:` becomes a `dropped:` item there, with the reason, in the same commit.
3. **Offer branch cleanup** through AskUserQuestion. Switch off the branch, then `git branch -D feature/<id>` and any `pd/<id>/task-*` branches. Abandoned branches are unmerged, so this one place uses `-D`.
