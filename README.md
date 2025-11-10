# LabFrame API

FastAPI facade exposing the LabFrame core services for web clients and other API consumers.

## Prerequisites

- Python 3.11+
- Access to the LabFrame core sources as a sibling directory: `../core`
- Existing SQLite database (default: `../db/database.sqlite`, override with `LABFRAME_DB_PATH`)

## Installation

### 1. Install LabFrame Core

First, install the core package in editable mode:

```bash
cd ../core
source ~/Backend/python/venv/thesis/bin/activate
pip install -e .
```

### 2. Install LabFrame API

Then install the API package:

```bash
cd ../api
source ~/Backend/python/venv/thesis/bin/activate
pip install -e .
```

## Running the server

You can run the server from any directory. Just ensure the virtual environment is activated:

```bash
source ~/Backend/python/venv/thesis/bin/activate
uvicorn labframe_api.app:app --reload --port 8000 --log-config logging.yaml
```

**Note:** The `--log-config` flag uses the `logging.yaml` file to add timestamps and colors to all HTTP request logs (GET, POST, etc.) and other log messages. INFO messages and 200 OK status codes are displayed in green.

**Note:** The `cd api` command is optional - it's only needed if you want to work with files in the API directory. The uvicorn command works from any location once the package is installed.

The server defaults to the database at `../db/database.sqlite` (relative to the LabFrame root directory). Override it via environment variable:

```bash
export LABFRAME_DB_PATH="/absolute/path/to/database.sqlite"
uvicorn labframe_api.app:app --reload --port 8000
```

## Logging

The API is configured with timestamped logging. All requests and server logs include timestamps in the format: `YYYY-MM-DD HH:MM:SS`.

## Available endpoints

### System
- `GET /health` - Health check endpoint

### Samples
- `GET /samples` - List all samples
- `POST /samples` - Create a new sample
- `GET /samples/{sample_id}` - Get a specific sample
- `GET /samples/{sample_id}/parameters` - Get parameter values for a sample
- `POST /samples/{sample_id}/parameters` - Record parameter values for a sample
- `DELETE /samples/{sample_id}` - Delete a sample

### Parameters
- `GET /parameters/definitions` - List all parameter definitions
- `GET /parameters/{parameter_name}/history` - Get parameter value history
- `GET /parameters/{parameter_name}/values` - Get unique parameter values

### Projects
- `GET /projects` - List all projects
- `GET /projects/active` - Get the active project
- `POST /projects` - Create a new project
- `POST /projects/with-template` - Create a project with template cloning
- `POST /projects/active` - Set the active project

### Events
- `GET /events/database-changes` - Stream database change notifications via SSE

These responses mirror the DTOs returned by the LabFrame core and are ready for consumption by frontend clients.

