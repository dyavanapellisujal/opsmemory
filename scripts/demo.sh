#!/usr/bin/env bash
# End-to-end OpsMemory demo (PRD Demo Flow).
# Prerequisites: `make db-up && make migrate && make api` running in another
# terminal, and (optionally) OPSMEMORY_GEMINI_API_KEY / OPSMEMORY_GROQ_API_KEY set.
set -euo pipefail
cd "$(dirname "$0")/.."

run() { echo; echo "\$ $*"; uv run "$@"; }

echo "=== Phase 1: platform status ==="
run opsmemory health
run opsmemory stats

echo "=== Phase 2: knowledge ingestion ==="
run opsmemory ingest ./samples/docs --name sample-docs

echo "=== Phase 3: knowledge exploration ==="
run opsmemory search "redis recovery"
run opsmemory ask "How do we recover redis for payments-api?"

echo "=== Phase 4: operational investigation ==="
run opsmemory ask "Why is payments-api failing with CrashLoopBackOff?"

echo "=== Phase 5: continuous learning ==="
run opsmemory teach "The payments-api deployment failed because the ConfigMap contained an invalid REDIS_HOST value. We fixed it by correcting the ConfigMap key and restarting the deployment. Lesson: validate ConfigMap values before rollout."

echo "=== Phase 6: improved answers ==="
run opsmemory ask "Have we seen payments-api deployment failures before?"
run opsmemory stats
