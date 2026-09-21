"""Workflow plugin route module — 7 focused route handlers."""
from fastapi import APIRouter

from . import crud, yaml, runs, schedule, export, import_workflows, chat

__all__ = [
    "create_workflow_routers",
    "register_workflow_routes",
]


def create_workflow_routers(
    audit_backend,
    forge_paths,
    license_backend,
    spawn_gates=None,
    scheduler=None,
    prompt_guard=None,
    awp_engine=None,
):
    """Create and return all 7 workflow route routers with dependency injection.
    
    This is the plugin's route factory. It wires adapters and returns routers
    that can be registered with FastAPI.
    
    Args:
        audit_backend: Audit logging backend (action_performed, action_failed)
        forge_paths: Path resolver for tenant homes, forges, etc.
        license_backend: License enforcement (get_limit, assert_limit)
        spawn_gates: L44 compliance gate for CLI spawns (optional)
        scheduler: corvin-scheduler integration (optional, Phase 4)
        prompt_guard: Claude CLI prompt guard (optional, soft dep)
        awp_engine: AWP execution engine (optional, soft dep)
    
    Returns:
        Tuple of 7 routers: (crud, yaml, runs, schedule, export, import, chat)
    """
    
    # ── Wire adapters ──────────────────────────────────────
    
    crud_adapter = crud.CRUDAdapter(audit_backend, forge_paths, license_backend)
    yaml_adapter = yaml.YAMLAdapter(audit_backend, forge_paths)
    runs_adapter = runs.RunsAdapter(audit_backend, forge_paths, spawn_gates, license_backend, awp_engine)
    schedule_adapter = schedule.ScheduleAdapter(audit_backend, forge_paths, scheduler)
    export_adapter = export.ExportAdapter(forge_paths)
    import_adapter = import_workflows.ImportAdapter(audit_backend, forge_paths, license_backend)
    chat_adapter = chat.ChatAdapter(forge_paths, prompt_guard, spawn_gates)
    
    # ── Override dependency injection ──────────────────────
    
    crud.get_crud_adapter = lambda: crud_adapter
    yaml.get_yaml_adapter = lambda: yaml_adapter
    runs.get_runs_adapter = lambda: runs_adapter
    schedule.get_schedule_adapter = lambda: schedule_adapter
    export.get_export_adapter = lambda: export_adapter
    import_workflows.get_import_adapter = lambda: import_adapter
    chat.get_chat_adapter = lambda: chat_adapter
    
    # ── Return routers ─────────────────────────────────────
    
    return (
        crud.router,
        yaml.router,
        runs.router,
        schedule.router,
        export.router,
        import_workflows.router,
        chat.router,
    )


def register_workflow_routes(app, **kwargs):
    """Convenience function to register all workflow routes on a FastAPI app.
    
    Usage:
        from fastapi import FastAPI
        app = FastAPI()
        from plugin_workflows.routes import register_workflow_routes
        register_workflow_routes(
            app,
            audit_backend=my_audit,
            forge_paths=my_paths,
            license_backend=my_license,
        )
    """
    routers = create_workflow_routers(**kwargs)
    for router in routers:
        app.include_router(router, prefix="/workflows", tags=["workflows"])
