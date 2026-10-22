# MyStock AI Terminal — Docker & Kubernetes Deployment Guide

This guide provides reproducible instructions for containerizing and deploying the **MyStock AI Terminal** using **Docker**, **Docker Compose**, and **Kubernetes** (Minikube / Docker Desktop / Kind).

---

## 1. Architecture & Service Topology

```
+-----------------------------------------------------------------------------------+
| Kubernetes Cluster (Namespace: stockrag) / Docker Compose Network                 |
|                                                                                   |
|  +-----------------------------------+     +-----------------------------------+  |
|  |       Stock Terminal API Pod      |     |             Ollama Pod            |  |
|  |  (FastAPI Backend + HTML/JS/CSS)  |     |   (Local LLM + Embeddings Engine) |  |
|  |                                   |     |                                   |  |
|  |  Port: 8000                       |     |  Port: 11434                      |  |
|  |  Probes: /api/health              |     |  Probes: /                        |  |
|  +-----------------+-----------------+     +-----------------+-----------------+  |
|                    |                                         |                    |
|                    +-----> (OLLAMA_BASE_URL) --------------->+                    |
|                    |       http://ollama:11434                                    |
|                    |                                                              |
|        +-----------+-----------+                     +-------+-------+            |
|        |                       |                     |               |            |
|        v                       v                     v               v            |
|  +-----------+           +-----------+         +---------------------------+      |
|  | Data PVC  |           |Uploads PVC|         |     Ollama Models PVC     |      |
|  | (SQLite + |           | (Raw User |         | (qwen2.5:1.5b,            |      |
|  |  FAISS)   |           | Documents)|         |  nomic-embed-text)        |      |
|  +-----------+           +-----------+         +---------------------------+      |
+-----------------------------------------------------------------------------------+
```

### Critical Architectural Decisions

1. **Self-Contained Frontend**:
   - The user interface is a Vanilla JavaScript and CSS terminal shell served directly by FastAPI from `static/` at `/` and `/static`. No separate Node.js build process is required inside the production container.
2. **Single Replica Policy for API**:
   - The application utilizes SQLite (`data/stock_terminal.db`) with Write-Ahead Logging (WAL) and local FAISS vector indices (`data/faiss/`). Because both backends require single-writer filesystem locking, the API deployment is configured with `replicas: 1`.
   - **Horizontal Scaling Path**: To scale beyond 1 replica, the persistence layer must be migrated to client-server backends (e.g., PostgreSQL for relational data and pgvector/Qdrant for semantic search).
3. **Dedicated Persistent Volumes**:
   - State (`data/` and `uploads/`) is isolated into dedicated PersistentVolumeClaims (PVCs) or Docker named volumes. Application code updates and image rollouts do not destroy persistent databases, vector stores, or uploaded files.
4. **Non-Root Execution**:
   - The application image runs strictly as unprivileged user `appuser` (UID: 10001, GID: 10001) for security compliance.

---

## 2. Environment Variables & Configuration

Configuration is separated into **non-sensitive configuration** (ConfigMap / environment variables) and **sensitive secrets** (Kubernetes Secrets / `.env`).

| Variable | Default Value | Description | Sensitivity |
| :--- | :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Bind IP inside container | Non-sensitive |
| `PORT` | `8000` | Application listen port | Non-sensitive |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | Non-sensitive |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Internal service discovery address for Ollama | Non-sensitive |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Default LLM for chat & financial synthesis | Non-sensitive |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Vector embedding model for RAG retrieval | Non-sensitive |
| `FAISS_PATH` | `/app/data/faiss` | Path to persistent FAISS vector index directory | Non-sensitive |
| `DB_PATH` | `sqlite:////app/data/stock_terminal.db` | SQLAlchemy SQLite database connection string | Non-sensitive |
| `UPLOAD_DIR` | `/app/uploads` | Path to uploaded document files | Non-sensitive |
| `AUTH_ENABLED` | `false` | Enable HTTP Basic Authentication | Non-sensitive |
| `AUTH_USERNAME` | `admin` | Basic authentication username | Sensitive |
| `AUTH_PASSWORD` | `change-me-in-production` | Basic authentication password | Sensitive |
| `UPSTOX_ACCESS_TOKEN` | `""` | Upstox API token for live market data (optional) | Sensitive |
| `FINNHUB_API_KEY` | `""` | Finnhub API key for market data fallback (optional) | Sensitive |

---

## 3. Docker Containerization

### 3.1 Build Application Image

```bash
# Build the Docker image with reproducible tagging
docker build -t stockrag-api:1.0 -t stockrag-api:latest .
```

### 3.2 Inspect Image Security & Structure

```bash
# Verify non-root user and layer size
docker image history stockrag-api:1.0
```

---

## 4. Local Multi-Service Deployment with Docker Compose

`docker-compose.yml` configures the FastAPI application, internal Ollama inference engine, persistent named volumes, and mutual healthchecks.

### 4.1 Launch Services

```bash
# Start all core services in detached mode
docker compose up -d

# Check status of running containers
docker compose ps
```

### 4.2 Initialize AI Models (First-Time Only)

The application requires Ollama models (`qwen2.5:1.5b` and `nomic-embed-text`). You can download them via the included init profile or directly into the running Ollama container:

```bash
# Option A: Using the compose profile
docker compose --profile init up ollama-init

# Option B: Directly executing in the running Ollama container
docker compose exec ollama ollama pull qwen2.5:1.5b
docker compose exec ollama ollama pull nomic-embed-text
```

### 4.3 View Service Logs

```bash
# Stream API logs
docker compose logs -f api

# Stream Ollama logs
docker compose logs -f ollama
```

### 4.4 Verify Deployment

Access the application in your browser:
- Terminal UI: [http://localhost:8000](http://localhost:8000)
- Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

Run the automated verification suite:
```bash
python scripts/verify_deployment.py --url http://localhost:8000
```

### 4.5 Stop Services

```bash
# Stop containers while preserving volume data
docker compose down

# Stop containers AND delete volume data (Destructive - deletes DB & models)
# docker compose down -v
```

---

## 5. Kubernetes Deployment with Minikube

Targeting a local Minikube cluster or Docker Desktop Kubernetes.

### 5.1 Prerequisites & Cluster Startup

```bash
# Start Minikube with sufficient CPU and memory for local LLM inference
minikube start --cpus=4 --memory=8192

# Verify current kubectl context
kubectl config current-context
kubectl get nodes
```

### 5.2 Build or Load Image into Cluster

When using Minikube, make the local Docker image available to the cluster:

```bash
# Option 1: Build image directly inside Minikube's Docker daemon
minikube image build -t stockrag-api:1.0 .

# Option 2: If built on host Docker, load into Minikube cache
minikube image load stockrag-api:1.0
```

### 5.3 Configure Secrets

Ensure `k8s/secret.yaml` exists with your desired credentials:
```bash
# Copy example if not already customized
cp k8s/secret.yaml.example k8s/secret.yaml
```

### 5.4 Apply Manifests

```bash
# Apply using Kustomize (recommended)
kubectl apply -k k8s/

# Or apply manifests individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/ollama-service.yaml
kubectl apply -f k8s/ollama-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/api-deployment.yaml
```

### 5.5 Monitor Rollout

```bash
# Watch pod initialization
kubectl get pods -n stockrag -w

# Check rollout status
kubectl rollout status deployment/ollama -n stockrag
kubectl rollout status deployment/stock-terminal -n stockrag
```

### 5.6 Pull AI Models in Cluster

Once the Ollama pod is running:
```bash
# Execute model pull inside the Ollama pod
kubectl exec -it deployment/ollama -n stockrag -- ollama pull qwen2.5:1.5b
kubectl exec -it deployment/ollama -n stockrag -- ollama pull nomic-embed-text
```

### 5.7 Access the Application

```bash
# Option A: Using Minikube Service command (opens browser automatically)
minikube service stock-terminal -n stockrag

# Option B: Using Port-Forwarding
kubectl port-forward svc/stock-terminal 8000:8000 -n stockrag

# Option C: Direct NodePort access via Minikube IP
# NodePort 30080 is pre-configured
curl http://$(minikube ip):30080/api/health
```

---

## 6. Operations & Maintenance Playbook

### 6.1 Inspect Diagnostics & Pod Logs

```bash
# View recent API container logs
kubectl logs deployment/stock-terminal -n stockrag --tail=100 -f

# View Ollama inference logs
kubectl logs deployment/ollama -n stockrag --tail=100 -f

# Inspect pod lifecycle events and troubleshooting diagnostics
kubectl describe pod -l app=stock-terminal -n stockrag
```

### 6.2 Rolling Restart

```bash
# Restart the API deployment without downtime
kubectl rollout restart deployment/stock-terminal -n stockrag
kubectl rollout status deployment/stock-terminal -n stockrag
```

### 6.3 Update Application Image

```bash
# Build updated image version
docker build -t stockrag-api:1.1 .
minikube image load stockrag-api:1.1

# Update the deployment image
kubectl set image deployment/stock-terminal stock-terminal=stockrag-api:1.1 -n stockrag
kubectl rollout status deployment/stock-terminal -n stockrag
```

### 6.4 Data Persistence Verification

To verify that SQLite data and uploaded documents persist across pod restarts:
```bash
# 1. Check existing documents
curl http://localhost:8000/api/documents

# 2. Delete the active pod (Deployment controller will recreate it)
kubectl delete pod -l app=stock-terminal -n stockrag

# 3. Wait for new pod to reach Ready state
kubectl wait --for=condition=ready pod -l app=stock-terminal -n stockrag --timeout=60s

# 4. Re-query documents to confirm zero data loss
curl http://localhost:8000/api/documents
```

### 6.5 Safe Resource Cleanup

```bash
# Delete all project Kubernetes resources (preserves PVC volumes if retained)
kubectl delete -k k8s/

# Or explicitly delete namespace
kubectl delete namespace stockrag
```

---

## 7. Troubleshooting Guide

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **`ImagePullBackOff` / `ErrImageNeverPull`** | Image not loaded into Minikube cache | Run `minikube image load stockrag-api:1.0` or set `imagePullPolicy: IfNotPresent`. |
| **`CrashLoopBackOff` on API** | Database migration failed or port in use | Run `kubectl logs deployment/stock-terminal -n stockrag` to view alembic errors. |
| **Ollama shows `disconnected` on `/api/health`** | DNS resolution or Ollama not ready | Verify `OLLAMA_BASE_URL` in ConfigMap matches `http://ollama.stockrag.svc.cluster.local:11434`. |
| **Models missing (`model_available: false`)** | Ollama volume is empty on new cluster | Run `kubectl exec -it deployment/ollama -n stockrag -- ollama pull qwen2.5:1.5b`. |
| **Permission denied on `/app/data`** | Volume mounted with root ownership | The deployment securityContext includes `fsGroup: 10001` which grants `appuser` write permissions. |
| **Out of Memory (OOMKilled)** | Minikube or Docker VM has insufficient RAM | Increase Minikube memory to at least 8 GB: `minikube start --memory=8192`. |
