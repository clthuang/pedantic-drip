"""Test stub for semantic_memory.writer (feature 104 FR-5 / design I-6).

Captures the candidate JSON to $STUB_CAPTURE_DIR/call-N.json and exits 0.
Exits 1 if STUB_CAPTURE_DIR is unset.

The hook (capture-on-stop.sh) invokes the writer as:
    python -m semantic_memory.writer --action upsert --entry-json '{...}'

So the stub parses argv for --entry-json. Falls back to stdin if no
--entry-json arg present (for direct-invocation tests).

Used by `test-capture-on-stop.sh` to verify capture-on-stop.sh constructs
the correct candidate JSON and dispatches it the expected number of times,
without exercising the real semantic_memory DB.
"""
import os
import sys


def main() -> int:
    capture_dir = os.environ.get("STUB_CAPTURE_DIR")
    if not capture_dir:
        sys.exit(1)
    os.makedirs(capture_dir, exist_ok=True)
    n = len([f for f in os.listdir(capture_dir) if f.startswith("call-")]) + 1

    # Look for --entry-json in argv (the hook's invocation mode).
    payload = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--entry-json" and i + 1 < len(args):
            payload = args[i + 1]
            break
    if payload is None:
        # Fallback: read stdin (direct-invocation test mode).
        payload = sys.stdin.read()

    with open(os.path.join(capture_dir, f"call-{n}.json"), "w") as f:
        f.write(payload)
    sys.exit(0)


if __name__ == "__main__":
    main()
