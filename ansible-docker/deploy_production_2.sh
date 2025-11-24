#!/bin/bash
# Production_2 Deployment Quick Start
# Run this script to deploy SMS Bridge Production_2 with one command

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKUP_DIR="$HOME/sms_bridge/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SMS Bridge Production_2 Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Ansible
if ! command -v ansible-playbook &> /dev/null; then
    echo -e "${RED}❌ Ansible not found. Please install Ansible 2.9+${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Ansible found: $(ansible --version | head -n1)${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker${NC}"
    exit 1
fi
if ! docker ps &> /dev/null; then
    echo -e "${RED}❌ Docker daemon not running. Please start Docker${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker running${NC}"

# Check vault.yml
if [ ! -f "$SCRIPT_DIR/../vault.yml" ]; then
    echo -e "${RED}❌ vault.yml not found. Please create vault.yml from vault.example.yml${NC}"
    exit 1
fi
echo -e "${GREEN}✅ vault.yml found${NC}"

# Check schema.sql
if [ ! -f "$SCRIPT_DIR/../schema.sql" ]; then
    echo -e "${RED}❌ schema.sql not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ schema.sql found (Production_2)${NC}"

# Check core/ package
if [ ! -d "$SCRIPT_DIR/../core" ]; then
    echo -e "${RED}❌ core/ package not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ core/ package found${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Deployment Options${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "1) Automated Migration (RECOMMENDED)"
echo "   - Creates backups automatically"
echo "   - Graceful shutdown of all containers"
echo "   - Schema migration with data preservation"
echo "   - Updates application code"
echo "   - Restarts all services"
echo "   - Post-deployment validation"
echo ""
echo "2) Fresh Install (DESTROYS EXISTING DATA)"
echo "   - Stops all containers"
echo "   - Deletes PostgreSQL data volume"
echo "   - Fresh schema installation"
echo "   - Clean start with Production_2"
echo ""
echo "3) Manual Backup Only"
echo "   - Creates backup of current system"
echo "   - No deployment changes"
echo ""
echo "4) Exit"
echo ""
read -p "Select option [1-4]: " OPTION

case $OPTION in
    1)
        echo ""
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${YELLOW}Option 1: Automated Migration${NC}"
        echo -e "${YELLOW}========================================${NC}"
        echo ""
        echo "This will:"
        echo "  1. Create backups of PostgreSQL and Redis"
        echo "  2. Stop all SMS Bridge containers"
        echo "  3. Migrate database schema to Production_2"
        echo "  4. Update application code"
        echo "  5. Restart all services"
        echo "  6. Validate deployment"
        echo ""
        read -p "Continue? [y/N]: " CONFIRM
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
            echo -e "${RED}Deployment cancelled${NC}"
            exit 0
        fi
        
        echo ""
        echo -e "${GREEN}Starting automated migration...${NC}"
        ansible-playbook -i "$SCRIPT_DIR/inventory.txt" "$SCRIPT_DIR/migrate_to_production_2.yml" --ask-vault-pass
        
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✅ Deployment Complete!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Test health: curl http://localhost:8080/health"
        echo "  2. Test admin UI: http://localhost:8080/admin/settings/ui"
        echo "  3. View logs: docker logs sms_receiver -f"
        echo ""
        echo "Migration report: ~/sms_bridge/migration_report_*.txt"
        echo "Backups: ~/sms_bridge/backups/"
        ;;
        
    2)
        echo ""
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}Option 2: Fresh Install${NC}"
        echo -e "${RED}========================================${NC}"
        echo ""
        echo -e "${RED}⚠️  WARNING: This will DELETE all existing data!${NC}"
        echo ""
        echo "This will:"
        echo "  1. Stop all SMS Bridge containers"
        echo "  2. DELETE PostgreSQL data volume (pg_data)"
        echo "  3. Install fresh Production_2 schema"
        echo "  4. Start all services from scratch"
        echo ""
        echo "Current data will be PERMANENTLY LOST unless you have backups."
        echo ""
        read -p "Type 'DELETE ALL DATA' to confirm: " CONFIRM
        if [ "$CONFIRM" != "DELETE ALL DATA" ]; then
            echo -e "${RED}Fresh install cancelled${NC}"
            exit 0
        fi
        
        echo ""
        echo -e "${YELLOW}Creating final backup before deletion...${NC}"
        mkdir -p "$BACKUP_DIR"
        
        # Try to backup if containers are running
        if docker ps --filter "name=postgres" --format "{{.Names}}" | grep -q postgres; then
            docker exec postgres pg_dump -U postgres sms_bridge > "$BACKUP_DIR/final_backup_before_fresh_install_$TIMESTAMP.sql" 2>/dev/null || echo "Could not backup database"
        fi
        
        echo -e "${YELLOW}Stopping all containers...${NC}"
        ansible-playbook -i "$SCRIPT_DIR/inventory.txt" "$SCRIPT_DIR/stop_sms_bridge.yml" --ask-vault-pass
        
        echo -e "${RED}Deleting PostgreSQL data volume...${NC}"
        docker volume rm pg_data 2>/dev/null || echo "Volume already removed or does not exist"
        
        echo -e "${GREEN}Installing Production_2 (fresh)...${NC}"
        ansible-playbook -i "$SCRIPT_DIR/inventory.txt" "$SCRIPT_DIR/setup_sms_bridge.yml" --ask-vault-pass
        
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✅ Fresh Install Complete!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Test health: curl http://localhost:8080/health"
        echo "  2. Access admin UI: http://localhost:8080/admin/settings/ui"
        echo "  3. Configure settings as needed"
        echo ""
        echo "Final backup (if created): $BACKUP_DIR/final_backup_before_fresh_install_$TIMESTAMP.sql"
        ;;
        
    3)
        echo ""
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${YELLOW}Option 3: Manual Backup${NC}"
        echo -e "${YELLOW}========================================${NC}"
        echo ""
        
        mkdir -p "$BACKUP_DIR"
        
        # Check if PostgreSQL is running
        if docker ps --filter "name=postgres" --format "{{.Names}}" | grep -q postgres; then
            echo -e "${GREEN}Creating PostgreSQL backup...${NC}"
            docker exec postgres pg_dump -U postgres sms_bridge > "$BACKUP_DIR/manual_backup_$TIMESTAMP.sql"
            echo -e "${GREEN}✅ Database backup: $BACKUP_DIR/manual_backup_$TIMESTAMP.sql${NC}"
        else
            echo -e "${YELLOW}⚠️  PostgreSQL container not running. Starting temporarily...${NC}"
            docker start postgres 2>/dev/null || echo "Could not start postgres"
            sleep 5
            docker exec postgres pg_dump -U postgres sms_bridge > "$BACKUP_DIR/manual_backup_$TIMESTAMP.sql" 2>/dev/null || echo "Backup failed"
        fi
        
        # Check if Redis is running
        if docker ps --filter "name=redis" --format "{{.Names}}" | grep -q redis; then
            echo -e "${GREEN}Creating Redis backup...${NC}"
            # Get Redis password from vault
            REDIS_PASS=$(grep redis_password ../vault.yml | awk '{print $2}' | tr -d '"')
            docker exec redis redis-cli -a "$REDIS_PASS" SAVE 2>/dev/null || echo "Redis backup skipped"
            echo -e "${GREEN}✅ Redis backup triggered (saved to Redis data dir)${NC}"
        fi
        
        # Backup current code
        if [ -d "$HOME/sms_bridge/core" ]; then
            echo -e "${GREEN}Creating code backup...${NC}"
            tar -czf "$BACKUP_DIR/core_backup_$TIMESTAMP.tar.gz" -C "$HOME/sms_bridge" core/
            echo -e "${GREEN}✅ Code backup: $BACKUP_DIR/core_backup_$TIMESTAMP.tar.gz${NC}"
        fi
        
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✅ Backup Complete!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "Backup location: $BACKUP_DIR"
        echo ""
        echo "To restore from backup:"
        echo "  docker exec -i postgres psql -U postgres sms_bridge < $BACKUP_DIR/manual_backup_$TIMESTAMP.sql"
        ;;
        
    4)
        echo -e "${BLUE}Deployment cancelled${NC}"
        exit 0
        ;;
        
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Deployment script finished${NC}"
echo -e "${BLUE}========================================${NC}"
