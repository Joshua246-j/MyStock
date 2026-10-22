# ==============================================================================
# MyStock AI - Teacher Demonstration & Evaluation Automation Script
# ==============================================================================
# Usage: powershell -ExecutionPolicy Bypass -File scripts/demo_for_teacher.ps1
# ==============================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "MyStock AI - Teacher Demonstration Terminal"

function Show-Header {
    Clear-Host
    Write-Host "==============================================================================" -ForegroundColor Cyan
    Write-Host "      MyStock AI: Docker, WSL2 & Kubernetes Demonstration Suite               " -ForegroundColor Yellow -NoNewline
    Write-Host " [Academic]" -ForegroundColor Green
    Write-Host "==============================================================================" -ForegroundColor Cyan
    Write-Host " System Architecture: FastAPI + SQLite WAL + FAISS + Ollama (qwen2.5:1.5b)" -ForegroundColor Gray
    Write-Host " Security: Non-Root UID 10001 | SSRF Guardrails | 12-Factor Secret Isolation" -ForegroundColor Gray
    Write-Host "==============================================================================`n" -ForegroundColor Cyan
}

function Run-PreFlight {
    Write-Host "`n>>> [1/5] Checking System Prerequisites & Virtualization Layers..." -ForegroundColor Cyan
    
    # Python Environment
    if (Test-Path ".\.venv\Scripts\python.exe") {
        $pyVer = & .\.venv\Scripts\python.exe --version
        Write-Host "  [OK] Python Virtualenv: $pyVer" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Virtual environment .venv not found in root." -ForegroundColor Yellow
    }

    # Docker CLI
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
        $dVer = & docker --version
        Write-Host "  [OK] Docker CLI: $dVer" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Docker CLI not found in PATH." -ForegroundColor Yellow
    }

    # WSL Status
    $wslCmd = Get-Command wsl -ErrorAction SilentlyContinue
    if ($wslCmd) {
        Write-Host "  [OK] WSL2 Virtualization Subsystem detected." -ForegroundColor Green
    }

    # Kubernetes CLI
    $k8sCmd = Get-Command kubectl -ErrorAction SilentlyContinue
    if ($k8sCmd) {
        $kVer = & kubectl version --client -o yaml 2>$null | Select-String "gitVersion" | Select-Object -First 1
        Write-Host "  [OK] Kubernetes CLI: $kVer" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] kubectl not found in PATH (Install via Docker Desktop K8s or choco)." -ForegroundColor Gray
    }
}

function Run-Pytest {
    Write-Host "`n>>> [2/5] Executing 116 Regression & Security Unit Tests (pytest)..." -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n  [SUCCESS] All 116 Unit Tests Passed (100% Green, 0 Regressions)." -ForegroundColor Green
    } else {
        Write-Host "`n  [FAIL] Test suite reported failures." -ForegroundColor Red
    }
}

function Run-DeploymentVerification {
    param([string]$targetUrl = "http://localhost:8000")
    Write-Host "`n>>> [3/5] Executing 7-Stage Live Deployment Verification against $targetUrl..." -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe scripts/verify_deployment.py --url $targetUrl
}

function Run-EndpointVerification {
    Write-Host "`n>>> [4/5] Executing Complete 14-Route REST API Verification..." -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe scripts/test_all_endpoints.py
}

function Show-DockerComposeWorkflow {
    Write-Host "`n>>> [DOCKER COMPOSE ORCHESTRATION]" -ForegroundColor Cyan
    Write-Host "  1. docker compose config            (Validate YAML & env variable interpolation)" -ForegroundColor Yellow
    Write-Host "  2. docker compose up -d --build     (Build API image & start Ollama microservices)" -ForegroundColor Yellow
    Write-Host "  3. docker compose ps                (Inspect container status & healthchecks)" -ForegroundColor Yellow
    Write-Host "  4. docker compose logs -f api       (Stream live server logs & DB migration)" -ForegroundColor Yellow
    Write-Host "  5. docker compose down              (Gracefully stop and preserve volumes)" -ForegroundColor Yellow
}

function Show-KubernetesWorkflow {
    Write-Host "`n>>> [KUBERNETES DECLARATIVE ORCHESTRATION]" -ForegroundColor Cyan
    Write-Host "  1. kubectl kustomize k8s/           (Compile 10 declarative manifests via Kustomize)" -ForegroundColor Yellow
    Write-Host "  2. kubectl apply -k k8s/            (Deploy namespace, configmaps, secrets, PVCs, pods)" -ForegroundColor Yellow
    Write-Host "  3. kubectl get pods,svc,pvc -n stockrag (Monitor rollout & PVC binding)" -ForegroundColor Yellow
    Write-Host "  4. kubectl port-forward -n stockrag svc/stock-terminal 8000:8000 (Expose local UI)" -ForegroundColor Yellow
    Write-Host "  5. kubectl delete -k k8s/           (Clean teardown of all cluster resources)" -ForegroundColor Yellow
}

function Show-Menu {
    Show-Header
    Write-Host "Select an action to present to your teacher/evaluator:" -ForegroundColor White
    Write-Host "  [1] Pre-Flight Health & Environment Check" -ForegroundColor White
    Write-Host "  [2] Run Automated Unit Tests (116 Tests - Pytest)" -ForegroundColor White
    Write-Host "  [3] Run 7-Stage Live Deployment Verification (verify_deployment.py)" -ForegroundColor White
    Write-Host "  [4] Run Complete REST API 14-Endpoint Test (test_all_endpoints.py)" -ForegroundColor White
    Write-Host "  [5] Docker Compose: Preview Configuration (docker compose config)" -ForegroundColor White
    Write-Host "  [6] Docker Compose: Start Services (docker compose up -d --build)" -ForegroundColor White
    Write-Host "  [7] Docker Compose: Check Status (docker compose ps)" -ForegroundColor White
    Write-Host "  [8] Docker Compose: View Logs (docker compose logs -f api)" -ForegroundColor White
    Write-Host "  [9] Docker Compose: Teardown Services (docker compose down)" -ForegroundColor White
    Write-Host "  [K1] Kubernetes: Compile Manifests (kubectl kustomize k8s/)" -ForegroundColor White
    Write-Host "  [K2] Kubernetes: Deploy Cluster (kubectl apply -k k8s/)" -ForegroundColor White
    Write-Host "  [K3] Kubernetes: Check Pods & PVCs (kubectl get pods,pvc -n stockrag)" -ForegroundColor White
    Write-Host "  [K4] Kubernetes: Teardown (kubectl delete -k k8s/)" -ForegroundColor White
    Write-Host "  [A] Run Automated Full Demonstration Sequence" -ForegroundColor Green
    Write-Host "  [Q] Exit Terminal" -ForegroundColor Gray
    Write-Host ""
}

# Interactive CLI loop
if ($args.Count -eq 0) {
    do {
        Show-Menu
        $choice = Read-Host "Enter Option"
        switch ($choice) {
            "1" { Run-PreFlight; Read-Host "`nPress Enter to continue..." }
            "2" { Run-Pytest; Read-Host "`nPress Enter to continue..." }
            "3" { Run-DeploymentVerification; Read-Host "`nPress Enter to continue..." }
            "4" { Run-EndpointVerification; Read-Host "`nPress Enter to continue..." }
            "5" { docker compose config; Read-Host "`nPress Enter to continue..." }
            "6" { docker compose up -d --build; Read-Host "`nPress Enter to continue..." }
            "7" { docker compose ps; Read-Host "`nPress Enter to continue..." }
            "8" { docker compose logs -f api; Read-Host "`nPress Enter to continue..." }
            "9" { docker compose down; Read-Host "`nPress Enter to continue..." }
            "K1" { kubectl kustomize k8s/; Read-Host "`nPress Enter to continue..." }
            "K2" { kubectl apply -k k8s/; Read-Host "`nPress Enter to continue..." }
            "K3" { kubectl get pods,svc,pvc -n stockrag; Read-Host "`nPress Enter to continue..." }
            "K4" { kubectl delete -k k8s/; Read-Host "`nPress Enter to continue..." }
            "A" {
                Run-PreFlight
                Run-Pytest
                Run-DeploymentVerification
                Run-EndpointVerification
                Show-DockerComposeWorkflow
                Show-KubernetesWorkflow
                Read-Host "`nAutomated sequence complete. Press Enter to return to menu..."
            }
        }
    } while ($choice -ne "Q" -and $choice -ne "q")
} else {
    # Non-interactive automated pass
    Run-PreFlight
    Run-Pytest
    Run-DeploymentVerification
    Run-EndpointVerification
}
