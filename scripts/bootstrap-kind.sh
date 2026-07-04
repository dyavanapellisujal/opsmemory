#!/usr/bin/env bash
# One-command local Kubernetes lab for OpsMemory (PRD `make lab`):
#   creates a Kind cluster, deploys PostgreSQL (pgvector), builds and deploys
#   OpsMemory via Helm (migrations run as a Helm hook), ingests the sample
#   knowledge, and leaves the API reachable on http://localhost:8000.
#
# AI keys: if OPSMEMORY_GEMINI_API_KEY / OPSMEMORY_GROQ_API_KEY are set in
# your shell (or in .env), they are passed into the cluster; otherwise the
# lab runs in keyless mode (hashing embeddings + extractive answers).
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=${CLUSTER:-opsmemory-lab}
IMAGE=opsmemory:0.1.0

for tool in kind kubectl helm docker; do
  command -v "$tool" >/dev/null || { echo "error: $tool is not installed"; exit 1; }
done

# Load .env so API keys configured for local dev reach the lab too.
if [ -f .env ]; then set -a; source .env; set +a; fi

echo "==> [1/6] Creating Kind cluster '${CLUSTER}'"
kind get clusters 2>/dev/null | grep -qx "${CLUSTER}" || kind create cluster --name "${CLUSTER}" --wait 120s
kubectl config use-context "kind-${CLUSTER}" >/dev/null

echo "==> [2/6] Building and loading the OpsMemory image"
docker build -q -t "${IMAGE}" . >/dev/null
kind load docker-image "${IMAGE}" --name "${CLUSTER}"

echo "==> [3/6] Deploying PostgreSQL (pgvector)"
kubectl create namespace opsmemory --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n opsmemory apply -f - >/dev/null <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: postgres }
spec:
  replicas: 1
  selector: { matchLabels: { app: postgres } }
  template:
    metadata: { labels: { app: postgres } }
    spec:
      containers:
        - name: postgres
          image: pgvector/pgvector:pg17
          env:
            - { name: POSTGRES_USER, value: opsmemory }
            - { name: POSTGRES_PASSWORD, value: opsmemory }
            - { name: POSTGRES_DB, value: opsmemory }
          ports: [{ containerPort: 5432 }]
          readinessProbe:
            exec: { command: ["pg_isready", "-U", "opsmemory"] }
            initialDelaySeconds: 3
            periodSeconds: 3
---
apiVersion: v1
kind: Service
metadata: { name: opsmemory-postgres }
spec:
  selector: { app: postgres }
  ports: [{ port: 5432 }]
EOF
kubectl -n opsmemory rollout status deploy/postgres --timeout=180s

echo "==> [4/6] Installing OpsMemory via Helm (migrations run as a hook)"
HELM_ARGS=(
  --set image.repository=opsmemory --set image.tag=0.1.0
  --set api.replicas=1
  --set database.url="postgresql+asyncpg://opsmemory:opsmemory@opsmemory-postgres:5432/opsmemory"
)
[ -n "${OPSMEMORY_GEMINI_API_KEY:-}" ] && HELM_ARGS+=(--set "env.OPSMEMORY_GEMINI_API_KEY=${OPSMEMORY_GEMINI_API_KEY}")
[ -n "${OPSMEMORY_GROQ_API_KEY:-}" ] && HELM_ARGS+=(--set "env.OPSMEMORY_GROQ_API_KEY=${OPSMEMORY_GROQ_API_KEY}")
helm upgrade --install opsmemory deploy/helm/opsmemory -n opsmemory --wait --timeout 5m "${HELM_ARGS[@]}"
# Same tag re-runs: force pods to pick up the freshly loaded image.
kubectl -n opsmemory rollout restart deploy/opsmemory-opsmemory-api >/dev/null
kubectl -n opsmemory rollout status deploy/opsmemory-opsmemory-api --timeout=180s

echo "==> [5/6] Port-forwarding API to http://localhost:8000"
pkill -f "port-forward svc/opsmemory-opsmemory-api" 2>/dev/null || true
kubectl -n opsmemory port-forward svc/opsmemory-opsmemory-api 8000:80 >/dev/null 2>&1 &
for _ in $(seq 1 30); do
  curl -sf http://localhost:8000/ready >/dev/null 2>&1 && break
  sleep 1
done
curl -sf http://localhost:8000/ready >/dev/null || { echo "error: API not ready"; exit 1; }

echo "==> [6/6] Ingesting sample knowledge (baked into the image at /app/samples)"
CONNECTOR_ID=$(curl -sf -X POST http://localhost:8000/api/v1/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"sample-docs","type":"local_files","config":{"path":"/app/samples/docs"}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' \
  || curl -sf http://localhost:8000/api/v1/connectors \
  | python3 -c 'import json,sys; print([c["id"] for c in json.load(sys.stdin) if c["name"]=="sample-docs"][0])')
JOB_ID=$(curl -sf -X POST "http://localhost:8000/api/v1/connectors/${CONNECTOR_ID}/sync" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
for _ in $(seq 1 60); do
  STATUS=$(curl -sf "http://localhost:8000/api/v1/jobs/${JOB_ID}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 1
done
echo "    sample ingestion: ${STATUS}"

echo
echo "✅ OpsMemory lab is running."
echo "   Dashboard : http://localhost:8000"
echo "   OpenAPI   : http://localhost:8000/docs"
echo "   Try       : uv run opsmemory ask 'How do we recover redis?'"
echo "   Teach     : uv run opsmemory teach 'We fixed X by doing Y'"
echo "   Tear down : make lab-down"
echo "   (port-forward runs in the background; re-run:"
echo "    kubectl -n opsmemory port-forward svc/opsmemory-opsmemory-api 8000:80)"
