# MyStock AI Terminal: Official Docker Hub Publication & Push Guide

**Target Repository:** [`https://hub.docker.com/repository/docker/joshuajomon246/stockterminal/general`](https://hub.docker.com/repository/docker/joshuajomon246/stockterminal/general)  
**Docker Hub Namespace:** `joshuajomon246`  
**Image Repository:** `stockterminal`  
**Recommended Tags:** `latest`, `1.0.0` (Semantic Versioning)

---

## 1. Quick Start: 1-Click Automated Push

You can execute the automated push script in PowerShell or Bash:

### Windows PowerShell (Recommended)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1
```

> **Available Flags:**
> - Specify custom version tag:
>   ```powershell
>   powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1 -Version 1.0.0
>   ```
> - Build and push multi-architecture (`linux/amd64` + `linux/arm64`) using Docker Buildx:
>   ```powershell
>   powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1 -MultiArch
>   ```

### Linux / WSL / macOS Bash
```bash
chmod +x scripts/push_dockerhub.sh
./scripts/push_dockerhub.sh joshuajomon246 stockterminal 1.0.0
```

### Interactive Teacher Demo Menu
In the evaluation menu:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo_for_teacher.ps1
```
Press **`[D]`** to build, tag, and push directly to Docker Hub.

---

## 2. Prerequisites Check

Before building or pushing:

1. **Start Docker Desktop**:
   - Launch **Docker Desktop** from your Windows Start Menu or Desktop.
   - Wait until the whale icon in the Windows taskbar turns **solid green** (Docker Engine running).
   - Test connectivity in PowerShell:
     ```powershell
     docker info
     ```

2. **Authenticate with Docker Hub**:
   - In terminal, log in to your `joshuajomon246` account:
     ```powershell
     docker login -u joshuajomon246
     ```
   - Enter your Docker Hub password or [Personal Access Token (PAT)](https://hub.docker.com/settings/security).

---

## 3. Manual Step-by-Step Commands

### Method A: Standard Docker CLI Build & Push

```powershell
# 1. Build the production image with both tags
docker build -t joshuajomon246/stockterminal:latest -t joshuajomon246/stockterminal:1.0.0 -f Dockerfile .

# 2. Push the 'latest' tag
docker push joshuajomon246/stockterminal:latest

# 3. Push the release version tag
docker push joshuajomon246/stockterminal:1.0.0
```

---

### Method B: Multi-Architecture Build & Push (Intel/AMD64 + ARM64/Apple Silicon)

If you want the Docker image to run natively on cloud servers (`x86_64`) and Mac M-series / ARM servers (`arm64`):

```powershell
# 1. Ensure Buildx builder instance is created
docker buildx create --name stockbuilder --use --bootstrap

# 2. Build and push both platforms in one command
docker buildx build `
  --platform linux/amd64,linux/arm64 `
  -t joshuajomon246/stockterminal:latest `
  -t joshuajomon246/stockterminal:1.0.0 `
  -f Dockerfile `
  --push `
  .
```

---

### Method C: Docker Compose Push

Since [`docker-compose.yml`](file:///d:/PROGRAMING/Stock-rag/docker-compose.yml) is now configured with `image: joshuajomon246/stockterminal:latest`, you can build and push using Docker Compose:

```powershell
# Build the service image
docker compose build api

# Push the built image directly to Docker Hub
docker compose push api
```

---

## 4. How Users & Evaluators Can Pull & Run

Anyone across the internet can now run the terminal with a single command without having to build from source:

### Standalone Container Run
```bash
# Pull the latest image
docker pull joshuajomon246/stockterminal:latest

# Run the container
docker run -d \
  --name mystock \
  -p 8000:8000 \
  -v stockrag_data:/app/data \
  -v stockrag_uploads:/app/uploads \
  joshuajomon246/stockterminal:latest
```
Visit **`http://localhost:8000`** in your browser.

---

### Kubernetes Deployment
[`k8s/api-deployment.yaml`](file:///d:/PROGRAMING/Stock-rag/k8s/api-deployment.yaml) has been updated to reference `joshuajomon246/stockterminal:latest`:

```powershell
# Deploy the full cluster in namespace 'stockrag'
kubectl apply -k k8s/

# Verify rollout status
kubectl rollout status deployment/stock-terminal -n stockrag

# Forward port to test
kubectl port-forward -n stockrag svc/stock-terminal 8000:8000
```

---

## 5. Security & Verification Checklist

- [x] **Non-Root Execution**: Container runs strictly as `appuser` (UID `10001`).
- [x] **Secret Isolation**: `.dockerignore` excludes all `.env`, `.pem`, `.key`, and credential files.
- [x] **Clean Volumes**: Database files (`*.db*`) and raw uploads are excluded from image layers; storage is handled via persistent volume mounts.
- [x] **Health Check**: Native Docker healthcheck validates `http://localhost:8000/api/health`.
- [x] **Database Auto-Migration**: `entrypoint.sh` executes `python -m alembic upgrade head` prior to ASGI boot.
