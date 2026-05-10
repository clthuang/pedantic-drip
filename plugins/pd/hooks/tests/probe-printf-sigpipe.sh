#!/usr/bin/env bash
# Verifies the Verified Bash Behavior matrix in design.md (feature 107).
# Each subshell writes >64KB to ensure pipe-close is detected past kernel
# pipe buffer. Outer pipeline rc reflects head's exit (0); inner subshell
# behavior shown via stderr "BAD" message or completion via "FINISHED OK".

report() { echo "=== $1 ==="; }

report "no trap, no '|| true' (subshell SIGPIPE-killed silently)"
( for i in $(seq 1 1500); do printf '%0100d\n' $i 2>/dev/null || { echo "BAD: printf failed at i=$i" >&2; exit 1; }; done; echo "FINISHED OK" >&2 ) | head -c 1 >/dev/null
echo "outer rc=$?"

report "trap '' PIPE, no '|| true' (printf returns 1, '||' fires)"
( trap '' PIPE; for i in $(seq 1 1500); do printf '%0100d\n' $i 2>/dev/null || { echo "BAD: printf failed at i=$i" >&2; exit 1; }; done; echo "FINISHED OK" >&2 ) | head -c 1 >/dev/null
echo "outer rc=$?"

report "set -e, no trap, with '|| true' (subshell still SIGPIPE-killed)"
( set -e; for i in $(seq 1 1500); do { printf '%0100d\n' $i 2>/dev/null; } || true; done; echo "FINISHED OK" >&2 ) | head -c 1 >/dev/null
echo "outer rc=$?"

report "set -e + trap '' PIPE + '|| true' (the safe pattern, FINISHED OK)"
( set -e; trap '' PIPE; for i in $(seq 1 1500); do { printf '%0100d\n' $i 2>/dev/null; } || true; done; echo "FINISHED OK" >&2 ) | head -c 1 >/dev/null
echo "outer rc=$?"
