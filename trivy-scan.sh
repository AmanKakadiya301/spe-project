#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# trivy-scan.sh
# Wrapper script for Trivy vulnerability scanner used in the Jenkins pipeline.
# Checks for CRITICAL and HIGH vulnerabilities. Fails the build if any are found.
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

SCAN_TYPE=$1  # 'fs' (filesystem) or 'image' (docker image)
TARGET=$2     # directory path or image name

if [ -z "$SCAN_TYPE" ] || [ -z "$TARGET" ]; then
    echo -e "${RED}Usage: ./trivy-scan.sh [fs|image] [target]${NC}"
    echo -e "Example 1: ./trivy-scan.sh fs ."
    echo -e "Example 2: ./trivy-scan.sh image myapp:latest"
    exit 1
fi

echo -e "${YELLOW}Starting Trivy $SCAN_TYPE scan on $TARGET...${NC}"

# Ensure Trivy is installed
if ! command -v trivy &> /dev/null; then
    echo -e "${YELLOW}Trivy not found. Downloading...${NC}"
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.48.3
fi

# Run the scan
# --exit-code 1 means the script will fail if vulnerabilities are found
# --severity HIGH,CRITICAL means we only care about serious issues
trivy $SCAN_TYPE \
    --severity HIGH,CRITICAL \
    --no-progress \
    --exit-code 1 \
    $TARGET

# Capture exit code
SCAN_RESULT=$?

if [ $SCAN_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ Scan passed! No HIGH or CRITICAL vulnerabilities found.${NC}"
else
    echo -e "${RED}❌ Scan failed! Vulnerabilities found. Fix them before deploying.${NC}"
    exit 1
fi
