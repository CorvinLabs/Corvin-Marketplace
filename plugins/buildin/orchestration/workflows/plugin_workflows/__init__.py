"""Workflows Plugin — Orchestration and automation platform.

Extracts ADR-0039 workflow builder from console → standalone plugin.
Phases 1-7: YAML AWP execution, design chat, cron scheduling, AWPKG export.
"""

__version__ = "1.0.0"

from .plugin import WorkflowsPlugin

__all__ = ["WorkflowsPlugin"]
