# StockAI Terminal — DevOps & Deployment Submission Guide

> **Micro-Project:** StockAI Terminal (Financial RAG & Market Analytics Dashboard)  
> **Repository:** [`Joshua246-j/MyStock`](https://github.com/Joshua246-j/MyStock)  
> **Docker Hub:** [`joshuajomon246/stockterminal`](https://hub.docker.com/r/joshuajomon246/stockterminal)  
> **Target RAM Budget:** 8 GB Laptop (Docker Compose & Minikube separated to prevent memory exhaustion)  

---

## 1. Project Architecture Overview

StockAI Terminal is a containerized micro-service architecture for financial research, real-time market data visualization, and retrieval-augmented generation (RAG):

```
+-----------------------------------------------------------------------------------+
|                                 USER INTERFACE                                    |
|   Responsive Dark Glassmorphism Web App (Vanilla JS, HTML5, Candlestick Charts)   |
+-----------------------------------------------------------------------------------+
                                        |  HTTP / REST
                                        v
+-----------------------------------------------------------------------------------+
|                        STOCK TERMINAL API (FastAPI / Python)                      |
|  - Real-Time Market Data (/api/market, Yahoo Finance API, Historical Bars)        |
|  - Financial News & Sentiment (/api/news)                                         |
|  - RAG Vector Engine (/api/chat, /api/forecast, FAISS Index + SQLite DB)          |
|  - Dual Mode Support: Full Local RAG Stack vs Lean Market-Only Cloud Mode         |
|  - Health Probes (/api/health, /api/health/live, /api/health/ready)               |
+-----------------------------------------------------------------------------------+
             |                                                  |
             v (Internal Cluster Network)                       v
+---------------------------------------+      +------------------------------------+
|         OLLAMA LLM SERVICE            |      |      PERSISTENT VOLUMES            |
|  - Model Inference: qwen2.5:3b        |      |  - sqlite_data (Application DB)    |
|  - Embeddings: nomic-embed-text       |      |  - uploads (Research Documents)    |
|  - Host: http://ollama:11434          |      |  - ollama_models (LLM Weights)     |
+---------------------------------------+      +------------------------------------+
```

### Dual-Mode Architecture

| Feature | Local Stack (Docker / K8s) | Cloud Deployment (Render Free Tier) |
| :--- | :--- | :--- |
| **Mode Flag** | `MARKET_ONLY=false` | `MARKET_ONLY=true` |
| **Market Data & Charts** | Real Yahoo Finance feeds | Real Yahoo Finance feeds |
| **FastAPI Backend** | Full stack (`requirements.txt`) | Lean stack (`requirements-cloud.txt`) |
| **RAM Footprint** | ~3.5 GB (with Ollama & weights) | ~116 MB (fits 512 MB Render Free limit) |
| **Docker Image Size** | 1.77 GB (`stockterminal:latest`) | 142 MB layer (`stockterminal:market`) |
| **Ollama Requirement** | Yes (local inference) | No (cloud fallback messaging) |
| **Readiness Probe** | Requires DB + Ollama models | Requires DB only (instant HTTP 200) |

---

## 2. Core DevOps Concepts Explained (For Teacher / Evaluator)

### A. Docker & Containerization
- **Docker Image:** A read-only template containing the application code, runtime libraries, and system dependencies (e.g. `joshuajomon246/stockterminal:latest`). It ensures consistent behavior across different developer laptops and cloud servers.
- **Docker Container:** A runnable, isolated instance of an image. Multiple containers (e.g., `stockterminal-api` and `stockterminal-ollama`) run independently on the same operating system kernel while sharing resources securely.
- **Docker Compose:** A declarative tool (`docker-compose.yml`) used to define and orchestrate multi-container setups, network communication, volume mounts, and environment variables with a single command.

### B. Kubernetes (K8s) & Minikube
- **Minikube:** A local, single-node Kubernetes cluster that runs inside a lightweight VM or container (using Docker as the driver). Ideal for dev/test verification before multi-node production rollout.
- **Pod:** The smallest deployable unit in Kubernetes. A pod encapsulates one or more co-located containers, shared storage volumes, and a unique network IP.
- **Deployment:** A Kubernetes controller that maintains the desired state of pods (replica count, rolling updates, rollbacks, and health self-healing).
- **Service:** An abstraction that defines a logical set of Pods and a policy to access them. The `NodePort` service (`30080`) exposes the application externally on the host, while `ClusterIP` exposes Ollama only internally within the cluster.
- **PersistentVolumeClaim (PVC):** A storage request that binds to physical storage, ensuring SQLite databases and downloaded models survive pod restarts and rescheduling.

---

## 3. Demonstration A — Local Docker Compose Stack

> **Important (8 GB RAM Safety):** Ensure Minikube is stopped before starting Docker Compose so that memory is not over-allocated.

### Step 1: Verify Configuration
```powershell
docker --version
docker compose config
```
*Expected Output:* Docker version printed (e.g. 29.6+), and validated Compose YAML specification without syntax errors.

### Step 2: Build and Start Stack
```powershell
docker compose up -d --build
```
*Expected Output:* Docker builds or downloads images and reports `Network stock-rag_stock-network Created`, `Volume stock-rag_sqlite_data Created`, `Container stockterminal-ollama Started`, `Container stockterminal-api Started`.

### Step 3: Verify Running Containers & Health
```powershell
docker compose ps
docker compose logs --tail=30
```
*Expected Output:*
- `stockterminal-api` listening on port `8000 -> 8000` (healthy).
- `stockterminal-ollama` listening on port `11434 -> 11434`.

### Step 4: Test API Readiness Endpoint
```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health/ready
```
*Expected Output:*
```json
{
  "ready": true,
  "database": "online",
  "ollama": "connected",
  "model_available": true,
  "embedding_model_available": true
}
```

### Step 5: Test Real-Time Market Data
```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/market/quotes?symbols=AAPL,MSFT,NVDA
```
*Expected Output:* Real market prices, volume, and percentage changes for Apple, Microsoft, and Nvidia.

### Step 6: Clean Shutdown
```powershell
# Stop stack cleanly while PRESERVING volume data (do NOT pass -v)
docker compose down
```

---

## 4. Demonstration B — Local Kubernetes / Minikube

> **Memory Rule:** Run Minikube only after `docker compose down` has freed your laptop's memory.

### Step 1: Start Minikube with D: Drive Cache (Prevents C: Drive Exhaustion)
```powershell
# Set Minikube home to D: drive where ample storage is available
$env:MINIKUBE_HOME = "D:\minikube"

# Start Minikube with 2 GB RAM and 2 CPUs
minikube start --driver=docker --memory=2048 --cpus=2
```
*Expected Output:* `Done! kubectl is now configured to use "minikube" cluster and "default" namespace`.

### Step 2: Verify Cluster Node
```powershell
kubectl get nodes
```
*Expected Output:* Node `minikube` with `STATUS: Ready`.

### Step 3: Deploy Application Manifests
```powershell
kubectl apply -k k8s/
```
*Expected Output:*
```text
namespace/stockrag configured
configmap/stockrag-config configured
secret/stockrag-secret configured
persistentvolumeclaim/stockrag-data-pvc configured
persistentvolumeclaim/stockrag-uploads-pvc configured
persistentvolumeclaim/ollama-models-pvc configured
service/stock-terminal configured
service/ollama configured
deployment.apps/stock-terminal configured
deployment.apps/ollama configured
```

### Step 4: Verify Namespaces, Pods, and Services
```powershell
# Check PVC storage binding
kubectl get pvc -n stockrag

# Check running Pods
kubectl get pods -n stockrag -o wide

# Check Services and Port Mapping
kubectl get services -n stockrag
```
*Expected Output:*
- PVCs report `STATUS: Bound`.
- Service `stock-terminal` type `NodePort` on port `8000:30080/TCP`.
- Service `ollama` type `ClusterIP` on port `11434/TCP`.
- Pod `stock-terminal` reaches `Running` status (resilient init-container ensures immediate startup).

### Step 5: Inspect Pod Logs & Liveness Probe
```powershell
kubectl logs -l app=stock-terminal -n stockrag --tail=50
```

### Step 6: Access Application in Browser
```powershell
# Option A: Minikube Service URL
minikube service stock-terminal -n stockrag --url

# Option B: Direct Port Forward
kubectl port-forward svc/stock-terminal 8000:8000 -n stockrag
```
Open `http://127.0.0.1:8000` in your web browser. Check the Market Dashboard and Candlestick charts.

### Step 7: Teardown Kubernetes Resources
```powershell
kubectl delete -k k8s/
minikube stop
```

---

## 5. Demonstration C — Render Cloud Market-Only Live Demo

Render provides free cloud web services connected directly to the GitHub repository.

### Step 1: Render Setup (Blueprint or Web Service)
1. Sign in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Blueprint**.
3. Connect repository `Joshua246-j/MyStock`.
4. Render automatically parses `render.yaml`:
   - **Runtime:** Python 3.12
   - **Plan:** Free
   - **Build Command:** `pip install -r requirements-cloud.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/api/health/live`

### Step 2: Configure Cloud Environment Variables (Dashboard)
Under the service **Environment** settings in Render:
- `MARKET_ONLY` = `true` (Enables lean market-only mode)
- `ALLOWED_ORIGINS` = `*` (Configures CORS for cross-origin access)
- `AUTH_ENABLED` = `false` (Public demo access without login hurdles)
- *(Optional)* `FINNHUB_API_KEY` = `your_api_key_here` (Yahoo Finance works automatically without any key)

### Step 3: Cloud Verification Commands (Using Live Public URL)
Replace `<RENDER_URL>` with your public Render domain (e.g., `https://mystock-market.onrender.com`):

```powershell
# 1. Automated Health Check (HTTP 200)
Invoke-RestMethod "<RENDER_URL>/api/health/live"

# 2. Market Readiness Probe
Invoke-RestMethod "<RENDER_URL>/api/health/ready"

# 3. Live Quotes for Teacher
Invoke-RestMethod "<RENDER_URL>/api/market/quotes?symbols=AAPL,GOOGL,TSLA"

# 4. Candlestick Historical Chart Data
Invoke-RestMethod "<RENDER_URL>/api/market/candles?symbol=AAPL&timeframe=1d&limit=30"

# 5. Automated Verification Script
python scripts/verify_deployment.py --url "<RENDER_URL>" --market-only
```
*Expected Output:*
```text
=======================================================
[PASS] 1. Root / UI endpoint responded (HTTP 200)
[PASS] 2. Liveness endpoint responded (HTTP 200)
[PASS] 3. Readiness probe passed for market-only mode (HTTP 200)
[PASS] 4. Market quotes returned 3 valid stock tickers
[PASS] 5. Market candlestick chart returned 30 data points
=======================================================
RESULT: CLOUD MARKET-ONLY VERIFICATION PASSED
```

---

## 6. Demonstration D — Docker Hub Verification

Our Docker images are published and publicly accessible on Docker Hub:
- Repository: [`joshuajomon246/stockterminal`](https://hub.docker.com/r/joshuajomon246/stockterminal)

### Published Tags:
1. `joshuajomon246/stockterminal:latest` — Full-stack local image with RAG, FAISS, LangChain, SQLite, and UI (used in Kubernetes and local Docker).
2. `joshuajomon246/stockterminal:1.0.0` — Production release tag of the full local stack.
3. `joshuajomon246/stockterminal:market` — Ultra-lean cloud market-only image (142 MB layer, non-root user `10001`, stripped of GPU/heavy C++ dependencies).

### Pull & Run from Docker Hub:
```powershell
# Pull lean market image
docker pull joshuajomon246/stockterminal:market

# Run isolated container
docker run -d --name stock-demo -p 8000:8000 -e MARKET_ONLY=true joshuajomon246/stockterminal:market

# Verify in browser
Start-Process "http://127.0.0.1:8000"

# Clean up
docker stop stock-demo
docker rm stock-demo
```

---

## 7. Troubleshooting & Student Defense FAQ

### Q1: Why does the Render free tier sleep after 15 minutes?
**Answer:** Render spins down free web services after 15 minutes of inactivity to conserve cloud energy. The first request after a sleep period may take 30–50 seconds to wake up (cold start). Once awake, subsequent requests respond in under 200 ms.

### Q2: Why don't we run Ollama on Render's free tier?
**Answer:** Ollama requires 3 to 4 GB of RAM to hold `qwen2.5:3b` in memory. Render's free tier allocates 512 MB of RAM. Attempting to run local LLMs on Render results in an immediate Out-Of-Memory (`OOMKilled`) termination. Our dual-mode architecture elegantly solves this by decoupling the real-time financial market analytics (which run smoothly on Render in ~116 MB RAM) from the local RAG engine (which runs locally on your laptop).

### Q3: Why do we separate Docker Compose and Minikube on an 8 GB laptop?
**Answer:** Docker Desktop with WSL2 allocates ~2.5 GB RAM. Minikube allocates an additional 2 to 2.5 GB RAM. Running Ollama (`3 GB`), Docker Compose, and Minikube concurrently causes the Windows host to run out of physical memory (`FreePhysicalMemory < 700 MB`), resulting in system thrashing and container timeouts. Stopping Compose before starting Minikube ensures reliable, error-free demonstration.

### Q4: Why is `MINIKUBE_HOME` set to `D:\minikube`?
**Answer:** By default, Minikube caches Kubernetes preloaded images and ISOs in `C:\Users\<user>\.minikube`. On laptops with low space on drive `C:`, this can exhaust all remaining disk space (0 MB free), crashing Docker Desktop and WSL2. Redirecting `MINIKUBE_HOME` to drive `D:\` leverages 180+ GB of free storage.
