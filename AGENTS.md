# LabFrame API — Agent Playbook

## Scope and Ownership

- Covers everything inside this `api/` repository.
- Ships the FastAPI server exposing LabFrame core services via REST API.
- Provides HTTP endpoints for web clients, CLI tools, and other API consumers.

## Local Environment

- Python 3.11+
- Use the thesis virtual environment: `~/Backend/python/venv/thesis/`
- Core dependency: `labframe-core` must be installed as a sibling package
  - Install with: `pip install -e ../core` (editable mode for development)

## Installation

### 1. Install Core Dependency

```bash
cd ../core
source ~/Backend/python/venv/thesis/bin/activate
pip install -e .
```

### 2. Install API Package

```bash
cd ../api
source ~/Backend/python/venv/thesis/bin/activate
pip install -e .
```

## Running the Server

You can run the server from any directory. Just ensure the virtual environment is activated:

```bash
source ~/Backend/python/venv/thesis/bin/activate
uvicorn labframe_api.app:app --reload --port 8000 --log-config logging.yaml
```

**Note:** The `cd api` command is optional - it's only needed if you want to work with files in the API directory. The uvicorn command works from any location once the package is installed.

**Timestamps and Colors:** The `--log-config` flag uses the `logging.yaml` file to add timestamps and colors to all HTTP request logs and other log messages. The format uses Python's logging format strings where `%(asctime)s` is the timestamp. INFO messages and 200 OK status codes are displayed in green.

## Project Layout

```
api/
├── src/
│   └── labframe_api/
│       ├── __init__.py
│       ├── app.py              # FastAPI application and endpoints
│       ├── config.py           # Configuration helpers
│       ├── change_detector.py  # Database change detection
│       └── sse_manager.py      # Server-Sent Events manager
├── pyproject.toml
├── README.md
└── AGENTS.md
```

## Architecture

- **Package structure**: Uses `src/` layout (consistent with `core/`)
- **Core dependency**: Uses package imports (`from labframe_core.app.bootstrap import ...`)
- **No path manipulation**: Removed all `sys.path.insert` calls
- **Logging**: Configured with timestamps in all log messages

## Key Files

- `app.py`: FastAPI application factory, endpoint definitions, lifespan management
- `config.py`: Database path resolution (respects `LABFRAME_DB_PATH` env var)
- `change_detector.py`: Polls database for changes and triggers SSE notifications
- `sse_manager.py`: Manages Server-Sent Events connections for real-time updates

## Endpoints

See `README.md` for complete API documentation. Main endpoint groups:
- `/samples` - Sample management
- `/parameters` - Parameter definitions and history
- `/projects` - Project management
- `/events/database-changes` - SSE stream for change notifications

## Development Guidelines

- Use type hints for all functions
- Follow FastAPI patterns for dependency injection
- Keep endpoints thin - delegate to core services
- Use Pydantic models for request/response validation
- Logging includes timestamps automatically

## Troubleshooting

- **Import errors**: Ensure `labframe-core` is installed: `pip install -e ../core`
- **Database path issues**: Check `LABFRAME_DB_PATH` environment variable
- **Port conflicts**: Change port in uvicorn command: `--port 8001`

