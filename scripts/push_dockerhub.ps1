<#
.SYNOPSIS
    Automated Docker Hub Build, Tag, and Push Script for MyStock AI Terminal.

.DESCRIPTION
    Builds the production-hardened Docker image for MyStock AI Terminal,
    tags it with both semantic version (:1.0.0) and :latest, and pushes
    the images to the official Docker Hub repository:
    https://hub.docker.com/repository/docker/joshuajomon246/stockterminal/general

.PARAMETER Username
    The Docker Hub organization or username (Default: joshuajomon246).

.PARAMETER Repository
    The Docker Hub repository name (Default: stockterminal).

.PARAMETER Version
    The semantic version tag (Default: 1.0.0).

.PARAMETER MultiArch
    Build multi-platform image (linux/amd64, linux/arm64) via Docker Buildx.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1
    powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1 -Version 1.0.0
    powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1 -MultiArch
#>

[CmdletBinding()]
param(
    [string]$Username = "joshuajomon246",
    [string]$Repository = "stockterminal",
    [string]$Version = "1.0.0",
    [switch]$MultiArch = $false
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "[+] $msg" -ForegroundColor Cyan
}

function Write-Success([string]$msg) {
    Write-Host "[OK] $msg" -ForegroundColor Green
}

function Write-WarnMsg([string]$msg) {
    Write-Host "[WARN] $msg" -ForegroundColor Yellow
}

function Write-ErrorMsg([string]$msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
}

$repoTarget = "$Username/$Repository"
$latestTag = "${repoTarget}:latest"
$versionTag = "${repoTarget}:${Version}"

Write-Host "==========================================================" -ForegroundColor Blue
Write-Host "   MyStock AI - Docker Hub Automated Push Utility        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Blue
Write-Host "Docker Hub Target: $repoTarget"
Write-Host "Tags to Publish:   $latestTag, $versionTag"
Write-Host "Multi-Platform:    $($MultiArch.IsPresent)"
Write-Host "=========================================================="

# 1. Check Docker CLI
Write-Step "Checking Docker CLI availability..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-ErrorMsg "Docker CLI is not found on your system PATH."
    Write-WarnMsg "Please ensure Docker Desktop is installed and added to PATH."
    exit 1
}
$dockerVer = & docker --version
Write-Success "Found: $dockerVer"

# 2. Check Docker Daemon Connectivity
Write-Step "Checking Docker Daemon engine connection..."
try {
    $daemonInfo = & docker info --format "{{.ServerVersion}}" 2>$null
    if (-not $daemonInfo) {
        throw "Daemon not responding"
    }
    Write-Success "Docker daemon is active (Server version: $daemonInfo)."
} catch {
    Write-ErrorMsg "Cannot connect to the Docker daemon."
    Write-WarnMsg "Docker Desktop is currently not running or still starting up."
    Write-Host ""
    Write-Host "To resolve this:" -ForegroundColor White
    Write-Host "  1. Open 'Docker Desktop' from your Windows Start Menu or Desktop." -ForegroundColor Gray
    Write-Host "  2. Wait until the Docker whale icon in the taskbar turns solid green." -ForegroundColor Gray
    Write-Host "  3. Re-run this script: powershell -ExecutionPolicy Bypass -File scripts/push_dockerhub.ps1" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# 3. Verify Docker Hub Authentication
Write-Step "Verifying Docker Hub authentication for user '$Username'..."
$configPath = "$env:USERPROFILE\.docker\config.json"
$isLoggedIn = $false

if (Test-Path $configPath) {
    try {
        $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
        if ($cfg.auths."https://index.docker.io/v1/" -ne $null -or $cfg.credsStore -ne $null) {
            $isLoggedIn = $true
        }
    } catch {
        # Fallback to test login
    }
}

if (-not $isLoggedIn) {
    Write-WarnMsg "Docker Hub credentials not detected in ~/.docker/config.json."
    Write-Host "Initiating interactive 'docker login'..." -ForegroundColor White
    & docker login -u $Username
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Docker login failed. Aborting push."
        exit 1
    }
} else {
    Write-Success "Docker Hub authentication configured for $Username."
}

# 4. Multi-Platform Build & Push OR Standard Build & Push
if ($MultiArch.IsPresent) {
    Write-Step "Building and pushing multi-platform image (linux/amd64, linux/arm64) using Buildx..."
    
    # Ensure buildx builder is initialized
    & docker buildx inspect 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating and bootstrapping buildx builder..." -ForegroundColor Gray
        & docker buildx create --name stockbuilder --use --bootstrap
    }
    
    & docker buildx build --platform linux/amd64,linux/arm64 -t $latestTag -t $versionTag -f Dockerfile --push .
        
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Docker Buildx multi-arch build failed."
        exit 1
    }
    Write-Success "Multi-architecture images built and published successfully!"
} else {
    Write-Step "Building container image for tags [$latestTag] and [$versionTag]..."
    & docker build -t $latestTag -t $versionTag -f Dockerfile .

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Docker build failed."
        exit 1
    }
    Write-Success "Docker image built successfully."

    Write-Step "Pushing $latestTag to Docker Hub..."
    & docker push $latestTag
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to push $latestTag. Please run 'docker login' and try again."
        exit 1
    }
    Write-Success "Pushed: $latestTag"

    Write-Step "Pushing $versionTag to Docker Hub..."
    & docker push $versionTag
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to push $versionTag."
        exit 1
    }
    Write-Success "Pushed: $versionTag"
}

# 5. Success Summary
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   DOCKER HUB PUSH COMPLETED SUCCESSFULLY!                " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Repository URL:  https://hub.docker.com/repository/docker/$Username/$Repository/general" -ForegroundColor Cyan
Write-Host "Published Tags:  $latestTag, $versionTag" -ForegroundColor White
Write-Host ""
Write-Host "To pull and run anywhere in the world:" -ForegroundColor White
Write-Host "   docker pull $latestTag" -ForegroundColor Gray
Write-Host "   docker run -d -p 8000:8000 --name mystock $latestTag" -ForegroundColor Gray
Write-Host ""
