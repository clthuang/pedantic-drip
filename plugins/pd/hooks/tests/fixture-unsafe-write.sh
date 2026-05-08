#!/usr/bin/env bash
# Intentionally unsafe — fixture for FR8 positive control. Do not source.
# This file MUST contain a line-leading `cat <<EOF` that the
# check-no-unsafe-writes.sh guard catches.
cat <<EOF
{"unsafe": "fixture"}
EOF
