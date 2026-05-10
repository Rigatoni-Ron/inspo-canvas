#!/usr/bin/env bash
# Thin wrapper around ingest.py so the existing entry point keeps working.
exec python3 "$(dirname "$0")/ingest.py" "$@"
