#!/usr/bin/env bash
# ==============================================================================
# Automated Docker Hub Build, Tag, and Push Script for MyStock AI Terminal
# Repository: https://hub.docker.com/repository/docker/joshuajomon246/stockterminal/general
# ==============================================================================

set -euo pipefail

USERNAME="${1:-joshuajomon246}"
REPOSITORY="${2:-stockterminal}"
VERSION="${3:-1.0.0}"
MULTIARCH="${4:-false}"

REPO_TARGET="${USERNAME}/${REPOSITORY}"
LATEST_TAG="${REPO_TARGET}:latest"
VERSION_TAG="${REPO_TARGET}:${VERSION}"

echo "=========================================================="
echo "   MyStock AI — Docker Hub Automated Push Utility        "
echo "=========================================================="
echo "Docker Hub Target: ${REPO_TARGET}"
echo "Tags to Publish:   ${LATEST_TAG}, ${VERSION_TAG}"
echo "Multi-Platform:    ${MULTIARCH}"
echo "=========================================================="

# 1. Verify Docker CLI
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker CLI not found. Please install Docker."
    exit 1
fi
echo "[OK] Docker CLI found: $(docker --version)"

# 2. Verify Daemon
if ! docker info &> /dev/null; then
    echo "[ERROR] Cannot connect to Docker daemon. Is Docker Desktop or dockerd running?"
    exit 1
fi
echo "[OK] Docker daemon is running."

# 3. Verify Docker Hub Authentication
echo "[+] Checking Docker Hub authentication..."
if ! grep -q "index.docker.io" "${HOME}/.docker/config.json" 2>/dev/null; then
    echo "[WARN] Docker Hub login required."
    docker login -u "${USERNAME}"
else
    echo "[OK] Docker Hub authentication detected for ${USERNAME}."
fi

# 4. Build & Push
if [ "${MULTIARCH}" = "true" ] || [ "${MULTIARCH}" = "--multiarch" ]; then
    echo "[+] Building multi-platform image (linux/amd64, linux/arm64) using Buildx..."
    docker buildx create --name stockbuilder --use --bootstrap 2>/dev/null || docker buildx use stockbuilder 2>/dev/null || true
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        -t "${LATEST_TAG}" \
        -t "${VERSION_TAG}" \
        -f Dockerfile \
        --push \
        .
    echo "[OK] Multi-architecture images pushed."
else
    echo "[+] Building image [${LATEST_TAG}] and [${VERSION_TAG}]..."
    docker build \
        -t "${LATEST_TAG}" \
        -t "${VERSION_TAG}" \
        -f Dockerfile \
        .
    echo "[OK] Image built."

    echo "[+] Pushing ${LATEST_TAG}..."
    docker push "${LATEST_TAG}"
    echo "[OK] Pushed ${LATEST_TAG}."

    echo "[+] Pushing ${VERSION_TAG}..."
    docker push "${VERSION_TAG}"
    echo "[OK] Pushed ${VERSION_TAG}."
fi

echo "=========================================================="
echo "   DOCKER HUB PUSH COMPLETED SUCCESSFULLY!                "
echo "=========================================================="
echo "Repository: https://hub.docker.com/repository/docker/${USERNAME}/${REPOSITORY}/general"
echo "Pull with:  docker pull ${LATEST_TAG}"
