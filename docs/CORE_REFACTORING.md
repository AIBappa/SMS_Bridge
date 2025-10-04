# Core Package Refactoring

## Overview
All Python application code, dependencies, and related packages have been consolidated into a `core/` directory to improve code organization and maintainability.

## What Changed

### Directory Structure

**Before:**
```
sms_bridge/
├── sms_server.py
├── redis_client.py
├── background_workers.py
├── requirements.txt
├── checks/
│   ├── blacklist_check.py
│   ├── duplicate_check.py
│   └── ...
└── observability/
    ├── __init__.py
    ├── metrics.py
    └── asgi_metrics.py
```

**After:**
```
sms_bridge/
└── core/
    ├── __init__.py
    ├── sms_server.py
    ├── redis_client.py
    ├── background_workers.py
    ├── requirements.txt
    ├── checks/
    │   ├── blacklist_check.py
    │   ├── duplicate_check.py
    │   └── ...
    └── observability/
        ├── __init__.py
        ├── metrics.py
        └── asgi_metrics.py
```

### Import Changes

All imports have been updated to use the `core.` prefix:

**Python Files:**
- `from redis_client import redis_pool` → `from core.redis_client import redis_pool`
- `from background_workers import start_background_workers` → `from core.background_workers import start_background_workers`
- `from observability.metrics import X` → `from core.observability.metrics import X`
- `from checks.X import Y` → `from core.checks.X import Y`

### Deployment Changes

#### Ansible Playbooks Updated

1. **`ansible-k3s/setup_sms_bridge_k3s.yml`**
   - Consolidated multiple copy tasks into single `core/` package copy
   - Updated Dockerfile to use `core/` structure
   - CMD changed: `uvicorn sms_server:app` → `uvicorn core.sms_server:app`

2. **`ansible-k3s/upgrade_sms_bridge_k3s.yml`**
   - Updated to copy `core/` package
   - Updated Dockerfile structure

3. **`ansible-docker/setup_sms_bridge.yml`**
   - Updated Docker build to use `core/` structure

#### Dockerfile Changes

**Before:**
```dockerfile
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY sms_server.py /app/sms_server.py
COPY redis_client.py /app/redis_client.py
COPY background_workers.py /app/background_workers.py
COPY observability/ /app/observability/
COPY checks/ /app/checks/
CMD ["uvicorn", "sms_server:app", "--host", "0.0.0.0", "--port", "8080"]
```

**After:**
```dockerfile
COPY core/requirements.txt /app/core/requirements.txt
RUN pip install --no-cache-dir -r core/requirements.txt
COPY core/ /app/core/
CMD ["uvicorn", "core.sms_server:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Test File Updates

**`tests/test_metrics_collector.py`**
- Updated import: `from observability.metrics import collect_once` → `from core.observability.metrics import collect_once`

### Documentation Updates

Updated the following documentation files:
- `docs/OBSERVABILITY_INTEGRATION.md` - Updated all import examples and file paths
- `docs/REDIS_MIGRATION_GUIDE.md` - References updated (historical documentation)
- `docs/REDIS_INTEGRATION_COMPLETE.md` - Import examples updated

## Benefits

1. **Cleaner Repository Root**: Non-code files (configs, docs, ansible) are clearly separated from application code
2. **Better Package Management**: All application code is now in a proper Python package with `__init__.py`
3. **Easier Deployment**: Single directory to copy instead of multiple files/directories
4. **Improved Imports**: Clear namespace (`core.`) makes it obvious what's application code vs external libraries
5. **Maintainability**: Future refactoring and code organization is simpler with everything under one package
6. **Docker Efficiency**: Simpler Dockerfile with fewer COPY commands

## Migration Checklist

If you have local development setup or custom scripts:

- [ ] Update any local import statements to use `core.` prefix
- [ ] Update any custom Dockerfiles to use the new structure
- [ ] Update environment setup scripts that reference old file paths
- [ ] Rebuild Docker images with the new structure
- [ ] Update IDE/editor Python path configuration if needed

## Deployment

To deploy the refactored code:

```bash
# For k3s deployment
cd ansible-k3s
ansible-playbook -i inventory.txt --ask-become-pass --ask-vault-pass setup_sms_bridge_k3s.yml

# For Docker deployment
cd ansible-docker
ansible-playbook -i inventory.txt --ask-become-pass --ask-vault-pass setup_sms_bridge.yml
```

The playbooks have been updated to handle the new structure automatically.

## Rollback

If you need to rollback to the old structure:

```bash
cd /home/shantanu/Documents/Software/SMS_Laptop_Setup/sms_bridge
git checkout <previous-commit>
```

Or manually:
1. Move files from `core/` back to root
2. Revert import statements
3. Revert Ansible playbooks
4. Rebuild images

## Testing

After deployment, verify:

1. Application starts successfully: `curl http://localhost:30080/health`
2. Metrics endpoint works: `curl http://localhost:30080/metrics`
3. SMS processing works: Test with sample SMS submission
4. Background workers running: Check logs for worker startup messages

## File Mappings

| Old Path | New Path |
|----------|----------|
| `sms_server.py` | `core/sms_server.py` |
| `redis_client.py` | `core/redis_client.py` |
| `background_workers.py` | `core/background_workers.py` |
| `requirements.txt` | `core/requirements.txt` |
| `checks/` | `core/checks/` |
| `observability/` | `core/observability/` |

## Notes

- The `core/__init__.py` package marker has been added with version info
- All Python syntax has been validated
- Import errors in IDE are expected until Python path is configured to include the repository root
- The refactoring maintains 100% backward compatibility in functionality
