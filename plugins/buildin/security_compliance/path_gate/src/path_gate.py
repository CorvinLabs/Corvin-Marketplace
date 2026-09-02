"""L10 path-gate - Filesystem access control enforcement.

Prevents directory traversal attacks and enforces write-access to whitelisted paths only.
Implements fail-closed access control.

Reference: ADR-0232, L10 (Path Gate), GDPR Art. 32
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Set
import os

_logger = logging.getLogger(__name__)


class PathGate:
    """L10 path-gate plugin - enforce filesystem access control."""

    # Default allowed write paths (fail-closed)
    DEFAULT_ALLOWED_PATHS = {
        "~/.corvin",
        "~/.corvin/audit.jsonl",
        "~/.corvin/tenants",
        "~/.config/corvin-voice",
        "/tmp/corvin*",
    }

    def __init__(self):
        """Initialize the path gate."""
        self.enabled = True
        self.allowed_write_paths: Set[Path] = set()
        self._initialize_allowed_paths()

    def _initialize_allowed_paths(self):
        """Initialize the set of allowed write paths."""
        for pattern in self.DEFAULT_ALLOWED_PATHS:
            # Expand ~ and wildcards
            if pattern.startswith("~"):
                expanded = Path(pattern).expanduser()
                self.allowed_write_paths.add(expanded)
            else:
                self.allowed_write_paths.add(Path(pattern))

    async def initialize(self, context):
        """Initialize the plugin with context."""
        _logger.info("PathGate initialized")

    def _normalize_path(self, path_str: str) -> Path:
        """Normalize a path and prevent directory traversal.

        Args:
            path_str: Raw path string

        Returns:
            Normalized absolute path

        Raises:
            ValueError: If path traversal detected
        """
        try:
            # Expand home directory and resolve symlinks
            path = Path(path_str).expanduser().resolve()

            # Prevent directory traversal attacks
            # Check for suspicious patterns
            if ".." in path.parts or path.parts[0] == "..":
                raise ValueError(f"Directory traversal detected: {path_str}")

            # Ensure path is absolute
            if not path.is_absolute():
                raise ValueError(f"Relative path not allowed: {path_str}")

            return path
        except ValueError:
            raise
        except Exception as e:
            _logger.error(f"Path normalization failed: {e}")
            raise ValueError(f"Invalid path: {path_str}")

    async def is_write_allowed(self, path_str: str) -> bool:
        """Check if writing to a path is allowed (fail-closed).

        Args:
            path_str: Path to check

        Returns:
            True if write is allowed, False otherwise
        """
        try:
            path = self._normalize_path(path_str)

            # Check against allowed paths
            for allowed in self.allowed_write_paths:
                # Exact match
                if path == allowed:
                    _logger.debug(f"Write allowed (exact match): {path}")
                    return True

                # Parent directory match (for wildcards)
                try:
                    if path.is_relative_to(allowed):
                        _logger.debug(f"Write allowed (under allowed dir): {path}")
                        return True
                except (ValueError, AttributeError):
                    # is_relative_to not available in older Python
                    if str(path).startswith(str(allowed)):
                        _logger.debug(f"Write allowed (under allowed dir): {path}")
                        return True

            _logger.warning(f"Write denied: {path} not in allowed paths")
            return False
        except Exception as e:
            _logger.error(f"Write permission check failed: {e}")
            return False  # Fail-closed

    async def is_read_allowed(self, path_str: str) -> bool:
        """Check if reading from a path is allowed.

        Note: Read access is more permissive than write access.

        Args:
            path_str: Path to check

        Returns:
            True if read is allowed, False otherwise
        """
        try:
            path = self._normalize_path(path_str)

            # Block reading from sensitive system paths
            blocked_prefixes = {
                "/etc/shadow",
                "/root/.ssh",
                "/proc/[0-9]+/environ",  # Process environment
            }

            path_str_normalized = str(path).lower()
            for blocked in blocked_prefixes:
                if blocked in path_str_normalized:
                    _logger.warning(f"Read denied (sensitive path): {path}")
                    return False

            # Allow reading from most paths by default (less restrictive)
            _logger.debug(f"Read allowed: {path}")
            return True
        except Exception as e:
            _logger.error(f"Read permission check failed: {e}")
            return False  # Fail-closed

    async def add_allowed_path(self, path_str: str) -> bool:
        """Add a path to the allowed write list.

        Args:
            path_str: Path to add

        Returns:
            True if added successfully
        """
        try:
            path = self._normalize_path(path_str)
            self.allowed_write_paths.add(path)
            _logger.info(f"Allowed path added: {path}")
            return True
        except Exception as e:
            _logger.error(f"Failed to add allowed path: {e}")
            return False

    async def execute(self, operation: str, **kwargs) -> dict:
        """Execute path gate operations.

        Args:
            operation: "check_write", "check_read", "add_allowed_path"
            **kwargs: Operation-specific arguments

        Returns:
            Operation result
        """
        try:
            if operation == "check_write":
                path = kwargs.get("path")
                if not path:
                    return {"success": False, "error": "path required"}

                allowed = await self.is_write_allowed(path)
                return {
                    "allowed": allowed,
                    "path": path,
                    "operation": "write",
                    "success": True
                }

            elif operation == "check_read":
                path = kwargs.get("path")
                if not path:
                    return {"success": False, "error": "path required"}

                allowed = await self.is_read_allowed(path)
                return {
                    "allowed": allowed,
                    "path": path,
                    "operation": "read",
                    "success": True
                }

            elif operation == "add_allowed_path":
                path = kwargs.get("path")
                if not path:
                    return {"success": False, "error": "path required"}

                result = await self.add_allowed_path(path)
                return {
                    "added": result,
                    "path": path,
                    "success": result
                }

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            _logger.error(f"Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check plugin health."""
        try:
            # Test allowed write check
            home_corvin = Path.home() / ".corvin"
            allowed = await self.is_write_allowed(str(home_corvin))
            return allowed
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown the plugin."""
        _logger.info("PathGate shutting down")
