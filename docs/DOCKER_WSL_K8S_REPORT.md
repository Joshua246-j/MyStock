# MyStock AI Terminal: Docker, WSL2 & Kubernetes Engineering Report

**Project Title:** MyStock AI — Educational Stock Market Research & RAG Terminal  
**Document Type:** Formal Project Submission & System Engineering Report  
**Date:** October 2026  
**Target Audience:** Project Reviewer, Course Instructor, Academic Evaluation Panel  
**Repository:** `Joshua246-j/MyStock`  

---

## Abstract

This report documents the architectural design, containerization, virtualization, and orchestration implementation for **MyStock AI**, a local-first educational financial research terminal. The system integrates real-time equity market data, probabilistic machine learning forecasting models, financial news aggregation, Retrieval-Augmented Generation (RAG) with hybrid lexical (SQLite FTS5) and dense vector (FAISS CPU) indexing, and local Large Language Model (LLM) inference powered by Ollama.

The deployment infrastructure is designed for cloud-native deployment standards, implementing:
1. **Docker Containerization** with multi-layer build caching, non-root security boundaries (`UID 10001`), automated Alembic database migrations, and container health checking.
2. **WSL2 (Windows Subsystem for Linux 2)** integration with Linux kernel 6.18+ virtualization and POSIX runtime isolation.
3. **Kubernetes (K8s)** declarative microservice orchestration using Kustomize, comprising isolated namespaces, ConfigMaps, Secrets, ClusterIP/NodePort Services, Persistent Volume Claims (PVCs), and Liveness/Readiness probes.
4. **Automated Verification**: End-to-end regression validation passing 116/116 automated test suites and a 7-stage automated deployment verification test.

---

## 1. System Architecture & Component Topology

```
+---------------------------------------------------------------------------------------------------------+
|                                    KUBERNETES CLUSTER (Namespace: stockrag)                             |
|                                       DOCKER COMPOSE BRIDGE NETWORK                                     |
|                                                                                                         |
|   CLIENT BROWSER                                                                                        |
|   (User / Instructor)                                                                                   |
|           |                                                                                             |
|           | HTTP Port 8000 / NodePort 30080                                                             |
|           v                                                                                             |
|   +-----------------------------------------------+       +-----------------------------------------+   |
|   |         Stock Terminal API Pod / Container    |       |        Ollama Inference Pod / Container |   |
|   |                                               |       |                                         |   |
|   |  - FastAPI (Python 3.12-slim ASGI Server)     |       |  - Ollama Engine (Go / C++ Runtime)     |   |
|   |  - Static Assets (Vanilla HTML5 / CSS3 / JS)  |       |  - Quantized Model: qwen2.5:1.5b        |   |
|   |  - Market Providers (YFinance, Stooq, etc.)   |  RPC  |  - Embeddings: nomic-embed-text         |   |
|   |  - Probabilistic ML Forecasting Engine        |------>|  - Port 11434 (Internal ClusterIP)      |   |
|   |  - Hybrid RAG (FTS5 + FAISS CPU Singleton)    |       |                                         |   |
|   |  - Non-Root Execution: UID 10001 / GID 10001  |       |                                         |   |
|   |  - Probes: Liveness & Readiness (/api/health) |       |  - Probes: Liveness & Readiness (/)     |   |
|   +-----------------------+-----------------------+       +--------------------+--------------------+   |
|                           |                                                    |                        |
|                           | Persistent Mounts                                  | Persistent Mounts      |
|             +-------------+-------------+                                      |                        |
|             v                           v                                      v                        |
|   +-------------------+       +--------------------+                 +--------------------+             |
|   | Persistent Volume |       | Persistent Volume  |                 | Persistent Volume  |             |
|   | stockrag-data-pvc |       | stockrag-uploads   |                 | ollama-models-pvc  |             |
|   |                   |       |                    |                 |                    |             |
|   | - SQLite Database |       | - Raw User Uploads |                 | - Downloaded Model |             |
|   |   (WAL Mode)      |       |   (PDF, CSV, XLSX, |                 |   Weights (Persist |             |
|   | - FAISS Index     |       |    DOCX, TXT)      |                 |   across restarts) |             |
|   +-------------------+       +--------------------+                 +--------------------+             |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Technical Component Deep-Dive

### 2.1 Docker Containerization (`Dockerfile`)

The containerization strategy adheres to Open Container Initiative (OCI) and production hardening standards:

1. **Base Image Selection**:
   - Uses `python:3.12-slim-bookworm` to minimize surface vulnerabilities and footprint while providing standard glibc runtime necessary for native C-extensions (NumPy, Scikit-learn, FAISS).
2. **Principle of Least Privilege (Non-Root Execution)**:
   - System user and group `appuser:appgroup` are provisioned with fixed UID/GID `10001`:
     ```dockerfile
     RUN groupadd -r appgroup --gid 10001 && \
         useradd -r -g appgroup --uid 10001 --create-home --home-dir /home/appuser appuser
     ```
   - Execution strictly drops privileges using `USER appuser`. In the event of an application exploit, the attacker has no host root escalation path.
3. **Optimized Layer Caching**:
   - `requirements.txt` is copied and installed in an isolated layer prior to copying source code. Source code changes re-trigger only fast final copy layers, skipping 5+ minutes of Python dependency wheel building.
4. **Deterministic Bootstrapping (`entrypoint.sh`)**:
   - Implements automated schema migrations before Uvicorn starts:
     ```sh
     #!/bin/sh
     set -e
     python -m alembic upgrade head
     exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
     ```
   - All files formatted with Unix `LF` line endings to prevent Windows `CRLF` shell execution failure.
5. **Built-in Healthcheck**:
   - Native Docker health checking queries the FastAPI endpoint:
     ```dockerfile
     HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
         CMD curl -f http://localhost:8000/api/health || exit 1
     ```

### 2.2 Docker Compose Multi-Service Topology (`docker-compose.yml`)

Docker Compose coordinates three tightly coupled components:
- **`ollama`**: Containerized local LLM engine with restart policies, port forwarding on `11434`, and an internal healthcheck.
- **`api`**: Application web server depending strictly on `ollama` with `condition: service_healthy`.
- **`ollama-init`**: One-shot initialization profile container executing `ollama pull qwen2.5:1.5b && ollama pull nomic-embed-text` on demand.
- **Data Persistence**: Named volumes (`stockrag_data`, `stockrag_uploads`, `ollama_data`) prevent loss of SQLite databases, user files, or model weights during container teardown or rebuilds.

### 2.3 WSL2 Virtualization Layer

The host development and testing runs on **Windows Subsystem for Linux 2 (WSL2)**:
- **Kernel Version**: `6.18.33.2-microsoft-standard-WSL2` (x86_64).
- **Distributions**:
  - `Ubuntu`: General Linux POSIX development environment.
  - `docker-desktop`: Dedicated lightweight Alpine Linux VM hosting the Docker daemon, bridge networking, and container runtimes.
- **Interoperability**: Windows filesystem mount (`/mnt/d/PROGRAMING/Stock-rag`) enables simultaneous Windows IDE editing and native Linux daemon execution.

### 2.4 Kubernetes (K8s) Declarative Orchestration

The Kubernetes configuration is packaged via **Kustomize** (`k8s/kustomization.yaml`):

| Manifest File | Kind | Purpose & Specifications |
| :--- | :--- | :--- |
| `namespace.yaml` | `Namespace` | Creates isolated `stockrag` logical partition |
| `configmap.yaml` | `ConfigMap` | Non-sensitive runtime variables (`HOST`, `PORT`, `OLLAMA_BASE_URL`, `LOG_LEVEL`) |
| `secret.yaml` | `Secret` | Sensitive credentials (Basic Auth credentials, optional API keys) |
| `pvc.yaml` | `PersistentVolumeClaim` | 3 claims: `stockrag-data-pvc` (2Gi), `stockrag-uploads-pvc` (2Gi), `ollama-models-pvc` (10Gi) |
| `ollama-deployment.yaml` | `Deployment` | Manages Ollama Pod with 6Gi memory limit and `/root/.ollama` PVC volume mount |
| `ollama-service.yaml` | `Service` | Internal `ClusterIP` on port 11434 (`ollama.stockrag.svc.cluster.local`) |
| `api-deployment.yaml` | `Deployment` | Enforces `replicas: 1`, non-root `securityContext`, probes, and PVC volume mounts |
| `api-service.yaml` | `Service` | Exposes application externally via `NodePort: 30080` (or Port 8000) |

#### Crucial Architectural Consideration: Why Single-Replica (`replicas: 1`)?
> **Student Defense Note for Instructor:**  
> The API container is intentionally configured with `replicas: 1` and `strategy: Recreate`. The persistence layer uses **SQLite with WAL mode** and **FAISS CPU flat index files**, which rely on single-writer process filesystem locks. Running multiple replicas on the same shared filesystem volume would trigger SQLite database locks or corrupted FAISS memory mappings. To horizontally scale to multiple pods in a production environment, persistence would be migrated to PostgreSQL and pgvector/Qdrant.

---

## 3. Step-by-Step Instructor Demonstration Guide

### Quick-Start: 1-Click Interactive Teacher Demonstration Script

For an interactive, menu-driven evaluation with color-coded verification results, simply execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo_for_teacher.ps1
```

> **What this script provides during your demonstration:**
> - **Pre-Flight Health Checks**: Validates Python, Docker, WSL2, and Kubernetes CLI versions in real time.
> - **Test Suite Execution**: Runs the complete 116/116 unit and integration test suite (`pytest -q`).
> - **7-Stage Deployment Verification**: Tests frontend delivery, health probes, models, live market quotes, and persistence.
> - **REST API Audit**: Verifies all 14 endpoints with HTTP status codes and response latencies.
> - **Docker & Kubernetes Controls**: Interactive shortcuts to compile manifests, launch containers, inspect logs, and cleanly tear down.

---

### Phase 1: Environment Readiness & Pre-Flight Checks

Show your teacher that the system prerequisites are active:

```powershell
# 1. Verify Docker version and client/server capability
docker --version
docker compose version

# 2. Check WSL2 Linux kernel status
wsl -l -v

# 3. Check Kubernetes client and Kustomize parser
kubectl version --client
```

---

### Phase 2: Docker Compose Demonstration (Recommended Primary Demo)

This demonstrates complete multi-container orchestration with a single command.

#### Step 2.1: Validate Docker Compose Configuration
Show your teacher that the declarative YAML is structurally sound and environment variables resolve correctly:

```powershell
docker compose config
```

#### Step 2.2: Build & Start Microservices
Launch the application and Ollama services in detached background mode:

```powershell
docker compose up -d --build
```

#### Step 2.3: Verify Running Containers & Health Status
Show your teacher that containers are running and healthy:

```powershell
docker compose ps
```
*Expected Output:*
```text
NAME              IMAGE                 COMMAND                  SERVICE   STATUS                    PORTS
stockrag-api      stockrag-api:latest   "/app/entrypoint.sh"     api       Up (healthy)              0.0.0.0:8000->8000/tcp
stockrag-ollama   ollama/ollama:latest  "/bin/ollama serve"      ollama    Up (healthy)              0.0.0.0:11434->11434/tcp
```

#### Step 2.4: Stream Real-Time Application Logs
Demonstrate the automatic database migration and server startup:

```powershell
docker compose logs -f api
```
*(Press `Ctrl + C` to stop viewing logs)*

#### Step 2.5: Execute Automated Deployment Verification
Run the 7-stage automated validation script to prove to your teacher that all services, routes, quotes, and databases are operational:

```powershell
.\.venv\Scripts\python.exe scripts/verify_deployment.py --url http://localhost:8000
```
*Expected Output:*
```text
=======================================================
VERIFYING DEPLOYMENT AT: http://localhost:8000
=======================================================
[PASS] 1. Root & Terminal Frontend Shell (Status: 200, Length: 214694 bytes)
[PASS] 2. Static CSS Asset Delivery (Status: 200)
[PASS] 3. Health Endpoint (App: running, Ollama: connected, Market: available, Vector: available)
[PASS] 4. AI Models Catalog (Available models verified)
[PASS] 5. Market Data Live Quote (Symbol: AAPL, Price: verified)
[PASS] 6. Chatbot & Ollama LLM Response (Live generation verified)
[PASS] 7. Database & Document Metadata Store (Documents verified)
-------------------------------------------------------
RESULT: DEPLOYMENT VERIFICATION PASSED (All critical checks succeeded)
-------------------------------------------------------
```

#### Step 2.6: Live Web Terminal Walkthrough
Open the browser at `http://localhost:8000` and demonstrate:
1. **Live Market Terminal**: Search `AAPL` or `RELIANCE.NS`. Show Candlestick view, Volume bars, and RSI indicators.
2. **AI Probabilistic Forecast**: Open Forecast tab. Show the AI Smart Ensemble distribution and target cards.
3. **Market News Feed**: Open News tab. Show the cached news feed with verified publishers.
4. **AI Chat & RAG**: Open Chat tab. Demonstrate ChatGPT-style interface with local LLM streaming.

#### Step 2.7: Clean Container Teardown
```powershell
docker compose down
```

---

### Phase 3: Kubernetes (K8s) Cluster Deployment

Use this demonstration path when your teacher specifically requests Kubernetes deployment via Minikube, Docker Desktop K8s, or Kind.

#### Step 3.1: Check Cluster Connection
```powershell
kubectl cluster-info
kubectl get nodes
```

#### Step 3.2: Preview Compiled Declarative Manifests
Show your teacher how Kustomize compiles all 10 manifests without manual concatenation:

```powershell
kubectl kustomize k8s/
```

#### Step 3.3: Apply the Manifests to Kubernetes
Deploy all resources into the dedicated `stockrag` namespace:

```powershell
kubectl apply -k k8s/
```

#### Step 3.4: Monitor Pod Rollout & PVC Binding
```powershell
kubectl get pods,svc,pvc -n stockrag -w
```
*(Wait until all pods show status `Running` and 1/1 `Ready`)*

#### Step 3.5: Access the Web Terminal
Forward the port to your local machine:

```powershell
kubectl port-forward -n stockrag svc/stock-terminal 8000:8000
```
Visit `http://localhost:8000` in the browser.

#### Step 3.6: Clean Teardown of Kubernetes Resources
```powershell
kubectl delete -k k8s/
```

---

### Phase 4: WSL2 Native Linux Demonstration

If your teacher requests proof of native Linux execution:

```powershell
# 1. Launch Ubuntu WSL2 shell
wsl -d Ubuntu

# 2. Show Linux Kernel & distribution info
uname -a
lsb_release -a

# 3. Change directory to the Windows project mount
cd /mnt/d/PROGRAMING/Stock-rag

# 4. Run the Python test suite natively inside Linux
python3 -m pytest -q

# 5. Exit back to Windows PowerShell
exit
```

---

## 4. Automated Verification & Quality Assurance Evidence

### 4.1 Pytest Automated Test Suite

A comprehensive test suite of **116 unit and integration tests** validates every core layer:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

**Verification Results Table:**

| Test Module | Tests | Status | Scope |
| :--- | :---: | :---: | :--- |
| `test_audit_improvements.py` | 12 | ✅ Passed | Settings schema, persona limits, greeting fast-path, history isolation |
| `test_cache_concurrency.py` | 1 | ✅ Passed | Atomic SQLite upsert and concurrent cache access |
| `test_chat_branching.py` | 3 | ✅ Passed | Conversation branching from message ID and state preservation |
| `test_chat_document_scopes.py` | 1 | ✅ Passed | Document scoping and retrieval isolation |
| `test_chat_streaming.py` | 1 | ✅ Passed | SSE token-by-token streaming |
| `test_crawler_security.py` | 7 | ✅ Passed | SSRF private IP blocking, domain allowlist, robots.txt |
| `test_dataset.py` | 1 | ✅ Passed | CSV profiling and numeric analysis |
| `test_document_loaders.py` | 5 | ✅ Passed | PDF, DOCX, TXT, HTML ingestion and metadata |
| `test_faiss_store.py` | 1 | ✅ Passed | FAISS vector store singleton and index stability |
| `test_forecast_system_improvements.py` | 15 | ✅ Passed | Probabilistic forecasting, ensemble calibration, custom models |
| `test_forecasting_engine.py` | 10 | ✅ Passed | Ridge regression, empirical drift baseline, uncertainty bands |
| `test_market_intelligence.py` | 5 | ✅ Passed | Technical indicators (SMA, EMA, RSI, MACD, ATR) |
| `test_market_storage.py` | 12 | ✅ Passed | OHLCV bar normalization, SQLite storage, freshness labeling |
| `test_memory_and_capabilities.py` | 8 | ✅ Passed | User preference extraction and capability bounds |
| `test_news_feed.py` | 2 | ✅ Passed | RSS news feed parsing and publisher deduplication |
| `test_news_provider.py` | 1 | ✅ Passed | News provider fallback and normalization |
| `test_pdf.py` | 1 | ✅ Passed | PDF extraction and page numbering |
| `test_production_features.py` | 30 | ✅ Passed | Extractive facts, grounding check, Ollama error handling |
| **Total Passed** | **116** | **100% Passed** | **Zero failures / zero regressions (31.59s execution)** |

---

### 4.2 Live REST API Endpoint Verification (`scripts/test_all_endpoints.py`)

All 14 core API endpoints were evaluated against the live running server:

```powershell
.\.venv\Scripts\python.exe scripts/test_all_endpoints.py
```

| HTTP Method | Route | HTTP Status | Response Time / Payload |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/health` | **200 OK** | App running, vector available, document count |
| `GET` | `/api/models` | **200 OK** | Installed models catalog |
| `GET` | `/api/settings` | **200 OK** | User configuration dictionary |
| `GET` | `/api/symbols/popular` | **200 OK** | Predefined US & Indian ticker list |
| `GET` | `/api/symbols/resolve?symbol=AAPL` | **200 OK** | Symbol resolution metadata |
| `GET` | `/api/stocks/AAPL` | **200 OK** | Company summary & sector profile |
| `GET` | `/api/stocks/AAPL/quote` | **200 OK** | Real-time / delayed price quote |
| `GET` | `/api/stocks/AAPL/history?period=1mo` | **200 OK** | Validated OHLCV historical bars (NaN-sanitized) |
| `GET` | `/api/stocks/AAPL/news` | **200 OK** | Attributed company news headlines |
| `GET` | `/api/stocks/AAPL/technical` | **200 OK** | SMA, EMA, RSI, MACD calculations |
| `GET` | `/api/stocks/AAPL/financials` | **200 OK** | Valuation multiples (PE, PB, Dividend Yield) |
| `GET` | `/api/news?limit=10` | **200 OK** | Aggregated, cached financial news feed |
| `GET` | `/api/documents` | **200 OK** | Ingested RAG document library |
| `GET` | `/api/chat/sessions?limit=10` | **200 OK** | Persisted chat history sessions |
| **Summary** | **14 / 14 Endpoints** | **100% Passed** | **Zero errors / 100% success rate** |

---

## 5. Oral Defense & Instructor Q&A Preparation

Prepare for these technical questions during your project presentation:

### Q1: Why did you choose Python 3.12-slim over Alpine Linux for the Docker image?
> **Answer:**  
> "While Alpine produces smaller images (~50 MB), it relies on `musl libc` instead of `glibc`. Our stack depends on high-performance mathematical and vector search libraries—specifically **NumPy**, **Scikit-learn**, and **FAISS-CPU**—which distribute pre-compiled C-extension binary wheels optimized exclusively for `glibc`. Compiling these from scratch on Alpine increases build times by over 25 minutes and introduces memory fragmentation risks. `python:3.12-slim-bookworm` provides full `glibc` binary wheel compatibility while maintaining a lean production footprint under 200 MB."

### Q2: Why is the Kubernetes deployment set to `replicas: 1` instead of scaling horizontally to 3 or 5 pods?
> **Answer:**  
> "The terminal utilizes **SQLite** with Write-Ahead Logging (WAL) and a process-local **FAISS CPU flat index** for zero-network local latency and low footprint. Both SQLite and FAISS rely on local filesystem write locks. If multiple Kubernetes pods mounted the same read-write volume simultaneously, concurrent writes would cause database locking exceptions and corrupted index memory maps. To horizontally scale to multiple replicas, we would transition SQLite to PostgreSQL and FAISS to a distributed vector engine such as Qdrant or pgvector."

### Q3: How do you prevent sensitive API keys or credentials from leaking into the container image?
> **Answer:**  
> "We strictly follow the 12-Factor App configuration methodology. No passwords, tokens, or private keys are hardcoded in the `Dockerfile` or committed to git (`.dockerignore` and `.gitignore` exclude `.env` files). In Docker Compose, secrets are injected via environment variable interpolation (`${UPSTOX_ACCESS_TOKEN}`). In Kubernetes, sensitive values are isolated into a `Secret` resource (`k8s/secret.yaml`) and injected into the container via `envFrom: secretRef`."

### Q4: How is database migration handled when rolling out container updates?
> **Answer:**  
> "We implemented an automated startup migration hook inside `entrypoint.sh`. Before the Uvicorn web server starts listening on port 8000, `entrypoint.sh` runs `python -m alembic upgrade head`. If a new container image contains new database tables or column modifications, Alembic automatically migrates the persistent SQLite database on the PVC before the web server serves incoming traffic."

---

## 6. Summary Command Cheat Sheet

```powershell
# -------------------------------------------------------------
# QUICK COMMAND CHEAT SHEET FOR TEACHER DEMONSTRATION
# -------------------------------------------------------------

# 1. Show Docker Compose configuration
docker compose config

# 2. Start all containers (API + Ollama)
docker compose up -d --build

# 3. Check container health status
docker compose ps

# 4. View live startup logs
docker compose logs -f api

# 5. Run automated verification test
.\.venv\Scripts\python.exe scripts/verify_deployment.py --url http://localhost:8000

# 6. Run all unit tests
.\.venv\Scripts\python.exe -m pytest -q

# 7. Stop containers after demo
docker compose down

# -------------------------------------------------------------
# KUBERNETES COMMANDS (If requested by teacher)
# -------------------------------------------------------------
kubectl kustomize k8s/
kubectl apply -k k8s/
kubectl get pods,svc,pvc -n stockrag
kubectl port-forward -n stockrag svc/stock-terminal 8000:8000
kubectl delete -k k8s/
```
