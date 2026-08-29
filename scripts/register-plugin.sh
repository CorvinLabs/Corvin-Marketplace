#!/bin/bash
# register-plugin.sh — Register a plugin with the Corvin Marketplace
#
# Usage:
#   ./scripts/register-plugin.sh <plugin-directory>
#   ./scripts/register-plugin.sh --validate <plugin-directory>
#   ./scripts/register-plugin.sh --generate-registry
#
# References:
#   - ADR-0233: Plugin System
#   - ADR-0243: Boot Layers
#   - ADR-0249: Trust Anchor (signatures)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGINS_DIR="$MARKETPLACE_ROOT/plugins"
REGISTRY_FILE="$MARKETPLACE_ROOT/registry.json"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_error() {
    echo -e "${RED}ERROR${NC}: $1" >&2
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

show_help() {
    cat << 'EOF'
register-plugin.sh — Plugin registration tool

Usage:
  register-plugin.sh <plugin-directory>
    Validate and register a single plugin

  register-plugin.sh --validate <plugin-directory>
    Validate without registering

  register-plugin.sh --generate-registry
    Generate registry.json from all plugins

  register-plugin.sh --help
    Show this help message

Examples:
  # Register a plugin
  ./scripts/register-plugin.sh ./plugins/my-router

  # Validate only
  ./scripts/register-plugin.sh --validate ./plugins/my-router

  # Regenerate entire registry
  ./scripts/register-plugin.sh --generate-registry

References:
  - Plugin Development: docs/PLUGIN_DEVELOPMENT.md
  - Manifest Schema: schema/plugin-manifest.v1.json
  - ADR-0233: Plugin System
  - ADR-0243: Boot Layers
  - ADR-0249: Trust Anchor
EOF
}

# Check Python is available
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Please install Python 3.8+"
        exit 1
    fi

    # Check for required packages
    python3 -c "import yaml, jsonschema" 2>/dev/null || {
        print_error "Missing required Python packages"
        echo "Install with: pip install pyyaml jsonschema" >&2
        exit 1
    }
}

# Validate a single plugin
validate_plugin() {
    local plugin_dir="$1"

    if [[ ! -d "$plugin_dir" ]]; then
        print_error "Plugin directory not found: $plugin_dir"
        exit 1
    fi

    if [[ ! -f "$plugin_dir/manifest.yaml" ]]; then
        print_error "manifest.yaml not found in $plugin_dir"
        exit 1
    fi

    print_info "Validating plugin: $plugin_dir"

    # Run Python validation
    python3 "$SCRIPT_DIR/plugin_registry_manager.py" validate "$plugin_dir"
    local exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        print_success "Plugin is valid"
        return 0
    else
        print_error "Plugin validation failed"
        return 1
    fi
}

# Register a plugin by copying it to plugins/ and regenerating registry
register_plugin() {
    local plugin_dir="$1"

    # Resolve to absolute path
    plugin_dir="$(cd "$plugin_dir" && pwd)"

    # Validate first
    if ! validate_plugin "$plugin_dir"; then
        exit 1
    fi

    # Extract plugin ID from manifest
    local plugin_id
    plugin_id=$(grep "^id:" "$plugin_dir/manifest.yaml" | sed 's/.*: "\([^"]*\)".*/\1/')

    if [[ -z "$plugin_id" ]]; then
        print_error "Could not extract plugin ID from manifest.yaml"
        exit 1
    fi

    print_info "Plugin ID: $plugin_id"

    # Check if plugin already exists
    local target_dir="$PLUGINS_DIR/$plugin_id"
    if [[ -d "$target_dir" ]]; then
        print_warning "Plugin already registered at $target_dir"
        echo "Do you want to update it? (y/n)"
        read -r response
        if [[ "$response" != "y" ]]; then
            exit 0
        fi
    fi

    # Copy plugin to registry
    print_info "Copying plugin to $target_dir"
    mkdir -p "$target_dir"
    cp -r "$plugin_dir"/* "$target_dir/"

    # Regenerate registry
    print_info "Regenerating registry.json"
    python3 "$SCRIPT_DIR/plugin_registry_manager.py" \
        generate \
        --plugins-dir "$PLUGINS_DIR" \
        --output "$REGISTRY_FILE"

    print_success "Plugin registered: $plugin_id"
    print_info "Registry updated: $REGISTRY_FILE"
}

# Generate registry from all plugins
generate_registry() {
    print_info "Generating registry.json from $PLUGINS_DIR"

    python3 "$SCRIPT_DIR/plugin_registry_manager.py" \
        generate \
        --plugins-dir "$PLUGINS_DIR" \
        --output "$REGISTRY_FILE"

    local plugin_count
    plugin_count=$(python3 -c "import json; f=open('$REGISTRY_FILE'); data=json.load(f); print(len(data.get('plugins', {})))")

    print_success "Registry generated with $plugin_count plugins"
    echo "  File: $REGISTRY_FILE"
}

# Main
main() {
    check_python

    if [[ $# -eq 0 ]]; then
        show_help
        exit 0
    fi

    case "$1" in
        --help)
            show_help
            exit 0
            ;;
        --validate)
            if [[ $# -lt 2 ]]; then
                print_error "Missing plugin directory argument for --validate"
                exit 1
            fi
            validate_plugin "$2"
            ;;
        --generate-registry)
            generate_registry
            ;;
        *)
            # Assume first argument is plugin directory to register
            register_plugin "$1"
            ;;
    esac
}

main "$@"
