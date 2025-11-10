"""FastAPI application exposing LabFrame core services."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from labframe_core.app.bootstrap import Services, bootstrap
from labframe_core.app.dto import (
    ParameterDefinitionItem,
    SampleParameterValueItem,
    SampleParameterValuePayload,
)
from labframe_core.domain.exceptions import DomainError, UnknownSampleError
from labframe_core.register.head import ensure_schema
from labframe_core.shared.clone_db import clone_database_data
from labframe_core.shared.projects import (
    create_project,
    delete_project,
    get_active_project_name,
    get_project,
    list_projects,
    rename_project,
    set_active_project_name,
    update_last_opened,
)
from labframe_core.shared.project_stats import (
    ProjectStatistics,
    get_project_statistics,
)

from .change_detector import ChangeDetector
from .config import resolve_db_path
from .sse_manager import get_sse_manager


# Logging configuration is handled via --log-config logging.yaml
# No need to configure logging here as uvicorn will load the YAML config


class CreateSamplePayload(BaseModel):
    """Request body for creating a sample."""

    prepared_on: date = Field(description="Date the sample was prepared.")
    author_name: str | None = Field(default=None, description="Full name of the preparer.")
    template_sample_id: int | None = Field(
        default=None,
        description="Optional sample to copy parameters from.",
    )
    copy_parameters: bool = Field(
        default=False,
        description="Whether to copy parameters from the template sample.",
    )


class RecordParametersPayload(BaseModel):
    """Request body for recording parameter values for a sample."""

    parameters: tuple[SampleParameterValuePayload, ...] = Field(default_factory=tuple)


class CreateProjectPayload(BaseModel):
    """Request body for creating a new project."""

    name: str = Field(description="Name of the project to create.")


class SetActiveProjectPayload(BaseModel):
    """Request body for setting the active project."""

    project_name: str | None = Field(description="Name of the project to activate, or None to clear.")


class CreateProjectWithTemplatePayload(BaseModel):
    """Request body for creating a project with template cloning."""

    name: str = Field(description="Name of the project to create.")
    template_project_name: str | None = Field(
        default=None,
        description="Name of the project to use as template, or None for empty project.",
    )
    clone_groups: bool = Field(default=False, description="Clone parameter groups.")
    clone_parameters: bool = Field(default=False, description="Clone parameter definitions (requires groups).")
    clone_values: bool = Field(default=False, description="Clone parameter values (requires groups and parameters).")


class RenameProjectPayload(BaseModel):
    """Request body for renaming a project."""

    name: str = Field(description="New name for the project.")


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    # Cache services per project to avoid recreating them
    _services_cache: dict[str | None, Services] = {}
    # Cache change detectors per project
    _change_detectors: dict[str | None, ChangeDetector] = {}
    # Background task for polling
    _polling_task: asyncio.Task | None = None
    sse_manager = get_sse_manager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifespan: start and stop background tasks."""
        # Startup: Start background polling task
        async def poll_database_changes() -> None:
            """Background task to poll database for changes."""
            while True:
                try:
                    await asyncio.sleep(3)  # Poll every 3 seconds

                    # Check all projects
                    for project_name, detector in list(_change_detectors.items()):
                        try:
                            has_changes, affected_parameters = detector.detect_changes()
                            if has_changes and affected_parameters:
                                # Broadcast notification
                                await sse_manager.broadcast(
                                    project_name,
                                    {
                                        "type": "parameter_values_changed",
                                        "parameters": affected_parameters,
                                    },
                                )
                        except Exception:
                            # Log error but continue polling
                            pass

                except asyncio.CancelledError:
                    break
                except Exception:
                    # Log error but continue polling
                    await asyncio.sleep(3)

        # Start polling task
        nonlocal _polling_task
        _polling_task = asyncio.create_task(poll_database_changes())

        yield

        # Shutdown: Cancel polling task
        if _polling_task:
            _polling_task.cancel()
            try:
                await _polling_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="LabFrame API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_services_for_project(project_name: str | None = None) -> Services:
        """Get services for a specific project, with caching."""
        if project_name not in _services_cache:
            if project_name:
                project = get_project(project_name)
                if project is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Project '{project_name}' not found",
                    )
                db_path = project.db_path
                # Ensure schema exists for project database
                ensure_schema(db_path)
            else:
                db_path = resolve_db_path()
                # Ensure schema exists for default database
                ensure_schema(db_path)
            _services_cache[project_name] = bootstrap(db_path)

        # Initialize change detector for this project (if not already initialized)
        if project_name not in _change_detectors:
            # Get db_path from services or project
            if project_name:
                project = get_project(project_name)
                if project:
                    db_path = project.db_path
                else:
                    # Fallback to default
                    db_path = resolve_db_path()
            else:
                db_path = resolve_db_path()
            _change_detectors[project_name] = ChangeDetector(Path(db_path))

        return _services_cache[project_name]

    def get_services(
        x_project: str | None = Header(None, alias="X-Project"),
    ) -> Services:
        """Get services, using project from header or active project."""
        project_name = x_project or get_active_project_name()
        return get_services_for_project(project_name)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/samples", tags=["samples"])
    def list_samples(
        include_deleted: bool = Query(False, description="Include soft-deleted samples."),
        services: Services = Depends(get_services),
    ) -> list[dict[str, object]]:
        summaries = services.samples.list_samples(include_deleted=include_deleted)
        return [summary.model_dump() for summary in summaries]

    @app.get("/samples/{sample_id}", tags=["samples"])
    def get_sample(
        sample_id: int,
        services: Services = Depends(get_services),
    ) -> dict[str, object]:
        sample = services.samples.get_sample(sample_id=sample_id, include_deleted=True)
        if sample is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")
        return sample.model_dump()

    @app.post("/samples", tags=["samples"], status_code=status.HTTP_201_CREATED)
    def create_sample(
        payload: CreateSamplePayload,
        services: Services = Depends(get_services),
    ) -> dict[str, object]:
        try:
            created = services.samples.create_sample(
                prepared_on=payload.prepared_on,
                author_name=payload.author_name,
            )
        except DomainError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        warnings: list[str] = []
        copied = 0
        if payload.copy_parameters and payload.template_sample_id is not None:
            try:
                result = services.samples.copy_parameters_from_sample(
                    source_sample_id=payload.template_sample_id,
                    target_sample_id=created.sample_id,
                )
            except DomainError as exc:
                warnings.append(str(exc))
            else:
                copied = result.applied
                created = result.sample
                warnings.extend(result.warnings)

        return {
            "sample": created.model_dump(),
            "copied_parameters": copied,
            "warnings": warnings,
        }

    @app.post("/samples/{sample_id}/parameters", tags=["samples"])
    def record_parameters(
        sample_id: int,
        payload: RecordParametersPayload,
        services: Services = Depends(get_services),
    ) -> dict[str, object]:
        assignments: tuple[SampleParameterValuePayload | dict[str, object], ...] = (
            payload.parameters
        )
        try:
            updated = services.samples.record_parameters(
                sample_id=sample_id,
                parameters=assignments,
            )
        except UnknownSampleError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except DomainError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"sample": updated.model_dump()}

    @app.delete("/samples/{sample_id}", tags=["samples"])
    def delete_sample(
        sample_id: int,
        services: Services = Depends(get_services),
    ) -> dict[str, object]:
        try:
            deleted = services.samples.delete_sample(sample_id=sample_id)
        except UnknownSampleError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except DomainError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"sample": deleted.model_dump()}

    @app.get("/samples/{sample_id}/parameters", tags=["samples"])
    def list_sample_parameters(
        sample_id: int,
        services: Services = Depends(get_services),
    ) -> list[dict[str, object]]:
        try:
            values = services.samples.get_sample_parameter_values(sample_id)
        except UnknownSampleError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return [value.model_dump() for value in values]

    @app.get("/parameters/definitions", tags=["parameters"])
    def list_parameter_definitions(
        services: Services = Depends(get_services),
    ) -> list[dict[str, object]]:
        definitions: tuple[ParameterDefinitionItem, ...] = (
            services.samples.list_parameter_definitions()
        )
        return [definition.model_dump() for definition in definitions]

    @app.get("/parameters/{parameter_name}/history", tags=["parameters"])
    def get_parameter_history(
        parameter_name: str,
        limit: int = Query(25, ge=1, le=200, description="Number of history entries to return."),
        services: Services = Depends(get_services),
    ) -> list[dict[str, object]]:
        values: tuple[SampleParameterValueItem, ...] = (
            services.samples.list_parameter_value_history(
                parameter_name,
                limit=limit,
            )
        )
        return [value.model_dump() for value in values]

    @app.get("/parameters/{parameter_name}/values", tags=["parameters"])
    def get_parameter_unique_values(
        parameter_name: str,
        services: Services = Depends(get_services),
    ) -> list[str]:
        """Return all unique display values currently in the database for the parameter."""
        values = services.samples.list_all_unique_parameter_values(parameter_name)

        # Format values as display strings (value + unit if present)
        # Use the service's stringify method to format values consistently
        from labframe_core.app.samples.services import SampleService

        display_values: list[str] = []
        for value in values:
            value_text, _ = SampleService._stringify_value(value.value)
            display_value = value_text
            if value.unit_symbol:
                display_value = f"{value_text} {value.unit_symbol}"
            display_values.append(display_value)

        return display_values

    @app.get("/events/database-changes", tags=["events"])
    async def stream_database_changes(
        request: Request,
        project: str | None = Query(None, description="Project name (alternative to X-Project header)"),
        x_project: str | None = Header(None, alias="X-Project"),
    ):
        """Stream database change notifications via Server-Sent Events."""
        project_name = project or x_project or get_active_project_name()

        # Ensure change detector exists for this project
        if project_name not in _change_detectors:
            # Initialize services (which will create the detector)
            get_services_for_project(project_name)

        return await sse_manager.stream_events(request, project_name)

    # Project management endpoints
    @app.get("/projects", tags=["projects"])
    def list_projects_endpoint() -> list[dict[str, object]]:
        """List all available projects."""
        projects = list_projects()
        active = get_active_project_name()
        return [
            {
                "name": project.name,
                "db_path": str(project.db_path),
                "is_active": project.name == active,
            }
            for project in projects
        ]

    @app.get("/projects/active", tags=["projects"])
    def get_active_project() -> dict[str, object] | None:
        """Get the currently active project."""
        active_name = get_active_project_name()
        if active_name is None:
            return None
        project = get_project(active_name)
        if project is None:
            return None
        return {
            "name": project.name,
            "db_path": str(project.db_path),
        }

    @app.post("/projects", tags=["projects"], status_code=status.HTTP_201_CREATED)
    def create_project_endpoint(payload: CreateProjectPayload) -> dict[str, object]:
        """Create a new project and initialize its database schema."""
        try:
            project = create_project(payload.name)
            # Initialize the database schema
            ensure_schema(project.db_path)
            # Clear cache for this project
            if payload.name in _services_cache:
                del _services_cache[payload.name]
            return {
                "name": project.name,
                "db_path": str(project.db_path),
            }
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create project: {exc}",
            ) from exc

    @app.post("/projects/with-template", tags=["projects"], status_code=status.HTTP_201_CREATED)
    def create_project_with_template_endpoint(
        payload: CreateProjectWithTemplatePayload,
    ) -> dict[str, object]:
        """Create a new project with optional template cloning."""
        try:
            # Validate cloning options
            if payload.clone_parameters and not payload.clone_groups:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot clone parameters without cloning groups",
                )
            if payload.clone_values and not payload.clone_groups:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot clone values without cloning groups",
                )
            if payload.clone_values and not payload.clone_parameters:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot clone values without cloning parameters",
                )

            # Create the project
            project = create_project(payload.name)

            # Initialize the database schema
            ensure_schema(project.db_path)

            # Clone data from template if specified
            if payload.template_project_name:
                template_project = get_project(payload.template_project_name)
                if template_project is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Template project '{payload.template_project_name}' not found",
                    )

                if payload.clone_groups or payload.clone_parameters or payload.clone_values:
                    clone_database_data(
                        source_db_path=template_project.db_path,
                        target_db_path=project.db_path,
                        clone_groups=payload.clone_groups,
                        clone_parameters=payload.clone_parameters,
                        clone_values=payload.clone_values,
                    )

            # Clear cache for this project
            if payload.name in _services_cache:
                del _services_cache[payload.name]

            return {
                "name": project.name,
                "db_path": str(project.db_path),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create project: {exc}",
            ) from exc

    @app.post("/projects/active", tags=["projects"])
    def set_active_project(payload: SetActiveProjectPayload) -> dict[str, object]:
        """Set the active project."""
        if payload.project_name is not None:
            project = get_project(payload.project_name)
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project '{payload.project_name}' not found",
                )
            # Update last_opened timestamp
            update_last_opened(payload.project_name)
        set_active_project_name(payload.project_name)
        return {"project_name": payload.project_name}

    @app.get("/projects/{project_name}/stats", tags=["projects"])
    def get_project_stats(project_name: str) -> dict[str, object]:
        """Get statistics for a project."""
        project = get_project(project_name)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not found",
            )
        
        stats = get_project_statistics(project.db_path)
        
        return {
            "sample_count": stats.sample_count,
            "parameter_definitions_count": stats.parameter_definitions_count,
            "parameters_with_values_count": stats.parameters_with_values_count,
            "parameters_without_values_count": stats.parameters_without_values_count,
            "run_count": stats.run_count,
            "data_points_count": stats.data_points_count,
            "people_involved": stats.people_involved,
            "institutes": stats.institutes,
            "responsible_persons": stats.responsible_persons,
            "project_stage": stats.project_stage,
            "database_health": stats.database_health,
            "last_modified": stats.last_modified.isoformat() if stats.last_modified else None,
        }

    @app.get("/projects/details", tags=["projects"])
    def get_project_details() -> list[dict[str, object]]:
        """Get all projects with full details and statistics."""
        projects = list_projects()
        active = get_active_project_name()
        
        result = []
        for project in projects:
            stats = get_project_statistics(project.db_path)
            result.append({
                "name": project.name,
                "db_path": str(project.db_path),
                "is_active": project.name == active,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "created_by": project.created_by,
                "last_opened": project.last_opened.isoformat() if project.last_opened else None,
                "last_modified": project.last_modified.isoformat() if project.last_modified else None,
                "stats": {
                    "sample_count": stats.sample_count,
                    "parameter_definitions_count": stats.parameter_definitions_count,
                    "parameters_with_values_count": stats.parameters_with_values_count,
                    "parameters_without_values_count": stats.parameters_without_values_count,
                    "run_count": stats.run_count,
                    "data_points_count": stats.data_points_count,
                    "people_involved": stats.people_involved,
                    "institutes": stats.institutes,
                    "responsible_persons": stats.responsible_persons,
                    "project_stage": stats.project_stage,
                    "database_health": stats.database_health,
                    "last_modified": stats.last_modified.isoformat() if stats.last_modified else None,
                },
            })
        
        return result

    @app.patch("/projects/{project_name}", tags=["projects"])
    def rename_project_endpoint(
        project_name: str,
        payload: RenameProjectPayload,
    ) -> dict[str, object]:
        """Rename a project."""
        try:
            updated_project = rename_project(project_name, payload.name)
            # Clear cache for both old and new project names
            if project_name in _services_cache:
                del _services_cache[project_name]
            if payload.name in _services_cache:
                del _services_cache[payload.name]
            return {
                "name": updated_project.name,
                "db_path": str(updated_project.db_path),
            }
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    @app.delete("/projects/{project_name}", tags=["projects"])
    def delete_project_endpoint(project_name: str) -> dict[str, object]:
        """Delete a project."""
        if not delete_project(project_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not found",
            )
        # Clear cache for this project
        if project_name in _services_cache:
            del _services_cache[project_name]
        return {"message": f"Project '{project_name}' deleted successfully"}

    return app


app = create_app()

