#!/usr/bin/env python3
"""Plugin Registry Manager — Validation, registration, and registry generation.

References:
- ADR-0233: Plugin System (plugin architecture)
- ADR-0243: Boot Layers (compliance·core·bundled·installed)
- ADR-0249: Trust Anchor (signature verification)
- ADR-0262: Plugin Builder v2 (builder framework)
"""

import os
import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import importlib.util
import base64

try:
    import yaml
    import jsonschema
except ImportError:
    print("ERROR: Missing required packages. Install with:", file=sys.stderr)
    print("  pip install pyyaml jsonschema", file=sys.stderr)
    sys.exit(1)


@dataclass
class ValidationError:
    """A validation error with context."""
    code: str
    message: str
    path: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class PluginManifest:
    """Parsed plugin manifest."""
    id: str
    name: str
    version: str
    description: str
    author: str
    license: str
    entry_point: str
    plugin_type: str
    origin: str = "community"
    boot_layer: str = "installed"
    tier: Optional[str] = None
    dependencies: List[Dict[str, str]] = None
    permissions: Dict[str, Any] = None
    requires: List[str] = None
    keywords: List[str] = None
    homepage: Optional[str] = None
    repository: Optional[str] = None
    email: Optional[str] = None
    min_corvin_version: Optional[str] = None
    max_corvin_version: Optional[str] = None
    signature: Optional[Dict[str, str]] = None
    categories: List[str] = None
    supports_auto_update: bool = False
    health_check_interval: int = 60
    plugin: Optional[str] = None  # Format version from manifest, not stored

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.requires is None:
            self.requires = []
        if self.keywords is None:
            self.keywords = []
        if self.categories is None:
            self.categories = []
        if self.permissions is None:
            self.permissions = {}


class PluginRegistryValidator:
    """Validates plugin manifests against schema and semantic rules."""

    def __init__(self, schema_path: Optional[Path] = None):
        """Initialize validator with JSON schema.

        Args:
            schema_path: Path to schema/plugin-manifest.v1.json.
                        Defaults to marketplace root.
        """
        if schema_path is None:
            # Assume this script is in scripts/ and schema is in schema/
            script_dir = Path(__file__).parent
            schema_path = script_dir.parent / "schema" / "plugin-manifest.v1.json"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")

        with open(schema_path) as f:
            self.schema = json.load(f)

    def validate_manifest(self, manifest_path: Path) -> Tuple[bool, List[ValidationError]]:
        """Validate a manifest.yaml file.

        Args:
            manifest_path: Path to manifest.yaml

        Returns:
            (is_valid, errors) tuple
        """
        errors: List[ValidationError] = []

        # 1. Load YAML
        if not manifest_path.exists():
            return False, [
                ValidationError(
                    code="MANIFEST_NOT_FOUND",
                    message=f"manifest.yaml not found",
                    path=str(manifest_path)
                )
            ]

        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return False, [
                ValidationError(
                    code="YAML_PARSE_ERROR",
                    message=f"Invalid YAML: {e}",
                    path=str(manifest_path)
                )
            ]

        # 2. Validate against JSON schema
        try:
            jsonschema.validate(instance=data, schema=self.schema)
        except jsonschema.ValidationError as e:
            errors.append(
                ValidationError(
                    code="SCHEMA_VALIDATION_ERROR",
                    message=f"Schema validation failed: {e.message}",
                    path=str(manifest_path),
                    details={"schema_path": list(e.absolute_path)}
                )
            )
            return False, errors

        # 3. Semantic validations
        manifest = PluginManifest(**data)
        semantic_errors = self._validate_semantics(manifest, manifest_path.parent)
        errors.extend(semantic_errors)

        return len(errors) == 0, errors

    def _validate_semantics(self, manifest: PluginManifest, plugin_dir: Path) -> List[ValidationError]:
        """Validate semantic constraints beyond JSON schema.

        Args:
            manifest: Parsed manifest
            plugin_dir: Directory containing the plugin

        Returns:
            List of validation errors (empty if all pass)
        """
        errors: List[ValidationError] = []

        # 1. Entry point must exist
        entry_point_error = self._validate_entry_point(manifest, plugin_dir)
        if entry_point_error:
            errors.append(entry_point_error)

        # 2. Plugin type must be known (schema already validates this, but check it's implemented)
        if not self._plugin_type_is_live(manifest.plugin_type):
            errors.append(
                ValidationError(
                    code="PLUGIN_TYPE_NOT_LIVE",
                    message=f"Plugin type '{manifest.plugin_type}' is not invoked by CorvinOS (dead code path)",
                    path=f"{plugin_dir}/manifest.yaml",
                    details={"plugin_type": manifest.plugin_type}
                )
            )

        # 3. Check dependency versions are valid semver
        for dep in manifest.dependencies:
            if not self._is_valid_version_spec(dep.get("version", "")):
                errors.append(
                    ValidationError(
                        code="INVALID_DEPENDENCY_VERSION",
                        message=f"Invalid version spec in dependency '{dep['id']}': {dep['version']}",
                        path=f"{plugin_dir}/manifest.yaml"
                    )
                )

        # 4. Signature validation (if present)
        if manifest.signature:
            sig_error = self._validate_signature(manifest, plugin_dir)
            if sig_error:
                errors.append(sig_error)

        # 5. Boot layer / origin constraints
        if manifest.origin == "community" and manifest.boot_layer in ("compliance", "core"):
            errors.append(
                ValidationError(
                    code="INVALID_ORIGIN_BOOT_LAYER_COMBO",
                    message="Community plugins cannot declare compliance/core boot layers",
                    path=f"{plugin_dir}/manifest.yaml",
                    details={"origin": manifest.origin, "boot_layer": manifest.boot_layer}
                )
            )

        return errors

    def _validate_entry_point(self, manifest: PluginManifest, plugin_dir: Path) -> Optional[ValidationError]:
        """Validate that entry_point::ClassName exists.

        Args:
            manifest: Parsed manifest
            plugin_dir: Directory containing the plugin

        Returns:
            ValidationError if not found, None if valid
        """
        try:
            module_path, class_name = manifest.entry_point.rsplit("::", 1)
        except ValueError:
            return ValidationError(
                code="INVALID_ENTRY_POINT_FORMAT",
                message="entry_point must be 'module.py::ClassName'",
                path=f"{plugin_dir}/manifest.yaml",
                details={"entry_point": manifest.entry_point}
            )

        # Convert module path to file path
        py_file = plugin_dir / module_path
        if not py_file.exists():
            return ValidationError(
                code="ENTRY_POINT_MODULE_NOT_FOUND",
                message=f"Module not found: {module_path}",
                path=f"{plugin_dir}/manifest.yaml",
                details={"module_path": str(py_file)}
            )

        # Load module and check class exists
        try:
            spec = importlib.util.spec_from_file_location("plugin_module", py_file)
            if spec is None or spec.loader is None:
                return ValidationError(
                    code="CANNOT_LOAD_ENTRY_POINT_MODULE",
                    message=f"Cannot load module: {module_path}",
                    path=f"{plugin_dir}/manifest.yaml"
                )

            module = importlib.util.module_from_spec(spec)
            # Don't execute module code (security), just check AST for class definition
            # For simplicity, we'll just try to parse it
            with open(py_file) as f:
                code = f.read()
            try:
                compile(code, str(py_file), "exec")
            except SyntaxError as e:
                return ValidationError(
                    code="ENTRY_POINT_MODULE_SYNTAX_ERROR",
                    message=f"Syntax error in module: {e}",
                    path=str(py_file)
                )

            # Check class name appears in the file (basic check)
            if f"class {class_name}" not in code:
                return ValidationError(
                    code="ENTRY_POINT_CLASS_NOT_FOUND",
                    message=f"Class '{class_name}' not found in {module_path}",
                    path=f"{plugin_dir}/manifest.yaml"
                )

        except Exception as e:
            return ValidationError(
                code="ENTRY_POINT_VALIDATION_FAILED",
                message=f"Failed to validate entry point: {e}",
                path=f"{plugin_dir}/manifest.yaml"
            )

        return None

    def _validate_signature(self, manifest: PluginManifest, plugin_dir: Path) -> Optional[ValidationError]:
        """Validate Ed25519 signature (ADR-0249).

        For now, this is a placeholder that validates structure only.
        Full signature verification requires the public key trust anchor.

        Args:
            manifest: Parsed manifest
            plugin_dir: Directory containing the plugin

        Returns:
            ValidationError if signature is malformed, None if valid
        """
        sig = manifest.signature
        if not sig:
            return None

        # Validate signature structure
        if sig.get("algorithm") != "ed25519":
            return ValidationError(
                code="UNSUPPORTED_SIGNATURE_ALGORITHM",
                message=f"Only ed25519 signatures supported, got: {sig.get('algorithm')}",
                path=f"{plugin_dir}/manifest.yaml"
            )

        # Validate base64url encoding
        for field in ("public_key", "value"):
            if field not in sig:
                return ValidationError(
                    code="MISSING_SIGNATURE_FIELD",
                    message=f"Signature missing required field: {field}",
                    path=f"{plugin_dir}/manifest.yaml"
                )
            try:
                # Try to decode base64url
                base64.urlsafe_b64decode(sig[field] + "=" * (4 - len(sig[field]) % 4))
            except Exception as e:
                return ValidationError(
                    code="INVALID_SIGNATURE_ENCODING",
                    message=f"Signature field '{field}' is not valid base64url: {e}",
                    path=f"{plugin_dir}/manifest.yaml"
                )

        # TODO: Verify signature against manifest digest and trust anchor (ADR-0249 Stage 6)
        # This requires the maintainer's Ed25519 public key from ~/.corvin/global/plugin_trust_anchors.txt

        return None

    @staticmethod
    def _is_valid_version_spec(spec: str) -> bool:
        """Check if version spec is valid (>=X.Y.Z, ^X.Y.Z, ~X.Y.Z, etc.)."""
        import re
        # Simple check: starts with >=, ^, ~, or a digit
        return bool(re.match(r"^(>=|<=|~|\^)?[0-9]+\.[0-9]+\.[0-9]+", spec))

    @staticmethod
    def _plugin_type_is_live(plugin_type: str) -> bool:
        """Check if plugin type is currently invoked by CorvinOS.

        From PLUGIN_SYSTEM.md:
        - Live: router_backend, summary_provider, notification_backend, recall_backend, audit_backend
        - Dead (never invoked): user_backend, stt_provider, data_connector, compute_engine, worker_engine, bridge_channel
        """
        live_types = {
            "router_backend",
            "summary_provider",
            "notification_backend",
            "recall_backend",
            "audit_backend",
        }
        return plugin_type in live_types


class PluginRegistry:
    """Manages the registry.json file and plugin entries.

    Registry is auto-generated from manifests in plugins/{plugin_id}/ directories.
    Format: {plugin_id: {manifest_fields + registry metadata}}
    """

    def __init__(self, registry_path: Path):
        """Initialize registry.

        Args:
            registry_path: Path to registry.json (typically Corvin-Marketplace/registry.json)
        """
        self.path = registry_path
        self.data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load existing registry or initialize empty."""
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"WARNING: Failed to load registry: {e}", file=sys.stderr)
                self.data = {}

    def add_or_update(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Add or update a plugin entry in the registry.

        Args:
            manifest: Parsed plugin manifest
            plugin_dir: Directory containing the plugin
        """
        # Compute directory hash (for change detection)
        dir_hash = self._compute_dir_hash(plugin_dir)

        # Build registry entry
        entry = {
            **asdict(manifest),
            "plugin_id": manifest.id,
            "registered_at": datetime.utcnow().isoformat() + "Z",
            "dir_hash": dir_hash,  # Used for change detection
            "directory": str(plugin_dir.relative_to(self.path.parent)),  # Relative path
        }

        self.data[manifest.id] = entry

    def generate_registry_json(self, plugins_dir: Path) -> Dict[str, Any]:
        """Generate registry from all manifest.yaml files in plugins_dir.

        Args:
            plugins_dir: Path to plugins directory (typically Corvin-Marketplace/plugins)

        Returns:
            Registry dict
        """
        registry: Dict[str, Any] = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "plugins": {},
        }

        validator = PluginRegistryValidator()

        # Scan plugins_dir for manifest.yaml files
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith(("_", ".")):
                continue

            manifest_path = plugin_dir / "manifest.yaml"
            if not manifest_path.exists():
                print(f"WARNING: {plugin_dir.name} has no manifest.yaml, skipping", file=sys.stderr)
                continue

            # Validate manifest
            is_valid, errors = validator.validate_manifest(manifest_path)
            if not is_valid:
                print(f"ERROR: {plugin_dir.name} validation failed:", file=sys.stderr)
                for err in errors:
                    print(f"  {err.code}: {err.message}", file=sys.stderr)
                continue

            # Load manifest
            with open(manifest_path) as f:
                data = yaml.safe_load(f)
            manifest = PluginManifest(**data)

            # Build entry
            entry = {
                **asdict(manifest),
                "plugin_id": manifest.id,
                "registered_at": datetime.utcnow().isoformat() + "Z",
                "directory": str(plugin_dir.relative_to(plugins_dir.parent)),
            }

            registry["plugins"][manifest.id] = entry

        return registry

    def save(self) -> None:
        """Save registry to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)

    @staticmethod
    def _compute_dir_hash(plugin_dir: Path, exclude_patterns: Optional[List[str]] = None) -> str:
        """Compute hash of plugin directory (for change detection).

        Args:
            plugin_dir: Directory to hash
            exclude_patterns: Patterns to exclude (e.g., ['.git', '__pycache__'])

        Returns:
            SHA256 hash hex digest
        """
        if exclude_patterns is None:
            exclude_patterns = [".git", "__pycache__", ".pytest_cache", "*.pyc"]

        hash_obj = hashlib.sha256()

        # Walk directory and hash file contents in sorted order
        for root, dirs, files in os.walk(plugin_dir):
            # Filter excluded directories
            dirs[:] = [d for d in sorted(dirs) if not any(p in d for p in exclude_patterns)]

            for file in sorted(files):
                if any(p in file for p in exclude_patterns):
                    continue

                file_path = Path(root) / file
                try:
                    with open(file_path, "rb") as f:
                        hash_obj.update(f.read())
                except Exception:
                    continue

        return hash_obj.hexdigest()


def main():
    """CLI entry point for registry management."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Plugin registry manager — validate and generate registry.json"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Subcommand: validate
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a plugin manifest"
    )
    validate_parser.add_argument("plugin_dir", type=Path, help="Plugin directory")

    # Subcommand: generate
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate registry.json from all manifests"
    )
    generate_parser.add_argument(
        "--plugins-dir",
        type=Path,
        default=Path.cwd() / "plugins",
        help="Plugins directory (default: ./plugins)"
    )
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "registry.json",
        help="Output registry.json path (default: ./registry.json)"
    )

    args = parser.parse_args()

    if args.command == "validate":
        validator = PluginRegistryValidator()
        is_valid, errors = validator.validate_manifest(args.plugin_dir / "manifest.yaml")
        if not is_valid:
            print(f"VALIDATION FAILED: {args.plugin_dir}")
            for err in errors:
                print(f"  {err.code}: {err.message}")
            sys.exit(1)
        else:
            print(f"✓ {args.plugin_dir} is valid")
            sys.exit(0)

    elif args.command == "generate":
        registry = PluginRegistry(args.output)
        generated = registry.generate_registry_json(args.plugins_dir)
        registry.data = generated
        registry.save()
        print(f"✓ Generated registry with {len(generated['plugins'])} plugins")
        print(f"  Output: {args.output}")
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
