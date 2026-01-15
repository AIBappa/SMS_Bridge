#!/bin/bash
# SMS Bridge - Coolify Deployment Setup Script
# Creates necessary directories and verifies configuration files
# SQL schema files already exist in init/ directory and are NOT modified

set -e # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "SMS Bridge - Coolify Setup"
echo "=========================================="
echo ""
# Color codes for output

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
# Function to print colored output

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}
# ===========================================
# Step 1: Create Directory Structure
# ===========================================

echo "Step 1: Creating directory structure..."
# Create logs directory and subdirectories for postgres and redis

if [ ! -d "logs" ]; then
    mkdir -p logs
    chmod 755 logs
    print_success "Created logs/ directory"
else
    print_warning "logs/ directory already exists"
fi

# Create postgres logs subdirectory with correct ownership
# NOTE: This is required on Linux/macOS. Windows Docker Desktop handles permissions automatically.
if [ ! -d "logs/postgres" ]; then
    mkdir -p logs/postgres
    print_success "Created logs/postgres/ directory"
else
    print_warning "logs/postgres/ directory already exists"
fi

# Try to set correct ownership (UID 999 = postgres user in container)
if command -v sudo &> /dev/null && [ "$OSTYPE" != "msys" ] && [ "$OSTYPE" != "win32" ]; then
    if sudo chown -R 999:999 logs/postgres 2>/dev/null; then
        print_success "Set postgres log directory ownership (UID 999)"
    else
        print_warning "Could not set postgres log ownership. Run manually: sudo chown -R 999:999 logs/postgres"
    fi
elif [ "$OSTYPE" = "msys" ] || [ "$OSTYPE" = "win32" ]; then
    print_info "Windows detected - Docker Desktop will handle permissions automatically"
else
    print_warning "Cannot set ownership (sudo not available). If on Linux, run: sudo chown -R 999:999 logs/postgres"
fi

# Create redis logs subdirectory with correct ownership
if [ ! -d "logs/redis" ]; then
    mkdir -p logs/redis
    print_success "Created logs/redis/ directory"
else
    print_warning "logs/redis/ directory already exists"
fi

# Try to set correct ownership (UID 999 = redis user in container)
if command -v sudo &> /dev/null && [ "$OSTYPE" != "msys" ] && [ "$OSTYPE" != "win32" ]; then
    if sudo chown -R 999:999 logs/redis 2>/dev/null; then
        print_success "Set redis log directory ownership (UID 999)"
    else
        print_warning "Could not set redis log ownership. Run manually: sudo chown -R 999:999 logs/redis"
    fi
elif [ "$OSTYPE" = "msys" ] || [ "$OSTYPE" = "win32" ]; then
    print_info "Windows detected - Docker Desktop will handle permissions automatically"
else
    print_warning "Cannot set ownership (sudo not available). If on Linux, run: sudo chown -R 999:999 logs/redis"
fi
# Resolve config directory once (prefer local `config/`, fall back to `core/config`)
if [ -d "config" ]; then
    CONFIG_PATH="$(cd "config" && pwd)"
    print_success "Found config/ directory at ${CONFIG_PATH}"
elif [ -d "$SCRIPT_DIR/../core/config" ]; then
    CONFIG_PATH="$(cd "$SCRIPT_DIR/../core/config" && pwd)"
    print_success "Found config directory in core/config at ${CONFIG_PATH}"
else
    CONFIG_PATH=""
    print_warning "config/ directory not found in coolify/ or core/. Will create config/ later if needed."
fi
# Verify init directory and SQL files exist

if [ ! -d "init" ]; then
    print_error "init/ directory missing! This should be in git."
    exit 1
fi

if [ ! -f "init/init.sql" ]; then
    print_error "init/init.sql missing! This should be in git."
    exit 1
fi

if [ ! -f "init/schema.sql" ]; then
    print_error "init/schema.sql missing! This should be in git."
    exit 1
fi

print_success "Found init/ directory with SQL schema files"
# ===========================================
# Step 2: Verify Configuration Directory
# ===========================================

echo ""
echo "Step 2: Verifying configuration directory..."
# If coolify/config missing but core/config exists use that. If neither exist, create coolify/config

if [ -z "$CONFIG_PATH" ]; then
    mkdir -p config
    chmod 755 config
    CONFIG_PATH="$(cd "config" && pwd)"
    print_success "Created config/ directory at ${CONFIG_PATH}"
    print_warning "You may want to populate config/ from core/config or check repository layout"
else
    print_success "Using configuration from ${CONFIG_PATH}"
fi
# Note: This deployment does NOT include Prometheus/Grafana
# For monitoring, use the separate coolify-monitoring setup
# ===========================================
# Step 3: Create .env File if Missing
# ===========================================

echo ""
echo "Step 3: Checking environment configuration..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        print_info "Creating .env from .env.example..."
        cp .env.example .env
        print_success "Created .env from template"
        print_warning "IMPORTANT: Edit .env and set all required passwords and secrets!"
    else
        print_error ".env.example not found. Cannot create .env template."
        exit 1
    fi
else
    print_warning ".env file already exists"
fi
# Check if .env has placeholder values

if [ -f ".env" ]; then
    if grep -q "CHANGE_ME" .env 2>/dev/null; then
        print_warning "⚠️ .env contains CHANGE_ME placeholders!"
        print_warning " You MUST update these before deploying:"
        echo ""
        grep "CHANGE_ME" .env | head -5 || true
        echo ""
    fi
fi
# ===========================================
# Step 4: Verify Docker Compose File
# ===========================================

echo ""
echo "Step 4: Verifying Docker Compose configuration..."

if [ ! -f "docker-compose.yml" ]; then
    print_error "docker-compose.yml not found!"
    exit 1
fi

print_success "Found docker-compose.yml"
# ===========================================
# Step 5: Verify Setup
# ===========================================

echo ""
echo "Step 5: Final verification..."
# Check if all required files exist

REQUIRED_FILES=(
"docker-compose.yml"
"Dockerfile"
".env"
"init/init.sql"
"init/schema.sql"
)

ALL_OK=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        print_success "Verified $file"
    else
        print_error "Missing $file"
        ALL_OK=false
    fi
done
# Check if directories exist (config may be in core/)

REQUIRED_DIRS=(
"logs"
"config"
"init"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ "$dir" = "config" ]; then
        if [ -n "$CONFIG_PATH" ] && [ -d "$CONFIG_PATH" ]; then
            print_success "Verified $dir/ directory (at ${CONFIG_PATH})"
        else
            print_error "Missing $dir/ directory"
            ALL_OK=false
        fi
    else
        if [ -d "$dir" ]; then
            print_success "Verified $dir/ directory"
        else
            print_error "Missing $dir/ directory"
            ALL_OK=false
        fi
    fi
done

echo ""
echo "=========================================="
if [ "$ALL_OK" = true ]; then
    print_success "Setup completed successfully!"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo ""
    echo "1. ${YELLOW}Edit .env file${NC} and set secure passwords:"
    echo " nano .env"
    echo ""
    echo " ${RED}Required changes:${NC}"
    echo " - POSTGRES_PASSWORD"
    echo " - REDIS_PASSWORD"
    echo " - SMS_BRIDGE_ADMIN_USERNAME"
    echo " - SMS_BRIDGE_ADMIN_PASSWORD"
    echo " - SMS_BRIDGE_ADMIN_SECRET_KEY"
    echo " - GRAFANA_ADMIN_PASSWORD"
    echo ""
    echo "2. ${YELLOW}Review configuration${NC} (optional):"
    echo " - config/prometheus.yml"
    echo " - init/schema.sql (database schema)"
    echo ""
    echo "3. ${YELLOW}Deploy services:${NC}"
    echo " docker-compose up -d"
    echo ""
    echo "4. ${YELLOW}Check status:${NC}"
    echo " docker-compose ps"
    echo " docker-compose logs -f sms_receiver"
    echo ""
    echo "5. ${YELLOW}Access services:${NC}"
    echo " - SMS Bridge: http://localhost:8080"
    echo " - Admin UI: http://localhost:8080/admin/"
    echo ""
    echo "6. ${YELLOW}For monitoring (optional):${NC}"
    echo " - Use the coolify-monitoring setup for Prometheus/Grafana"
    echo " - See coolify-monitoring/README.md for details"
    echo ""
else
    print_error "Setup incomplete. Please check errors above."
    exit 1
fi
echo "=========================================="

