#!/bin/bash
set -e

################################################################################
# Video Producer Skill 2.0 — Production Installation
#
# Installs the complete plugin with all tiers + production hardening
################################################################################

VERSION="2.0.0"
PLUGIN_NAME="video-producer-skill-2.0"

echo "════════════════════════════════════════════════════════════════"
echo "  VIDEO PRODUCER SKILL 2.0 — PRODUCTION INSTALLER"
echo "════════════════════════════════════════════════════════════════"
echo ""

# 1. Check prerequisites
echo "📋 Checking prerequisites..."
for cmd in python3 ffmpeg; do
    if ! command -v $cmd &> /dev/null; then
        echo "❌ ERROR: $cmd not installed"
        exit 1
    fi
    echo "   ✅ $cmd"
done

# 2. Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
if [ -f requirements.txt ]; then
    pip3 install -q -r requirements.txt
    echo "   ✅ Base dependencies installed"
fi

# 3. Install optional tier dependencies
echo ""
echo "🎨 Optional rendering tiers:"
echo "   1.5) Three.js GPU rendering (Puppeteer required)"
echo "   2)   Manim + color grading"
echo "   3)   Blender (requires Blender installation)"
echo "   all) Install all tiers"
echo "   none) Skip optional tiers"
read -p "Enter choice [1.5/2/3/all/none]: " tier_choice

case $tier_choice in
    1.5)
        echo "Installing Tier 1.5 (Three.js)..."
        npm install -g puppeteer
        echo "   ✅ Puppeteer installed"
        ;;
    2)
        echo "Installing Tier 2 (Manim)..."
        pip3 install -q manim
        echo "   ✅ Manim installed"
        ;;
    3)
        echo "Installing Tier 3 (Blender)..."
        if command -v blender &> /dev/null; then
            echo "   ✅ Blender found"
        else
            echo "   ⚠️  Blender not found in PATH"
            echo "      Install from https://www.blender.org/download/"
        fi
        ;;
    all)
        echo "Installing all tiers..."
        npm install -g puppeteer 2>/dev/null || true
        pip3 install -q manim
        echo "   ✅ All optional tiers installed"
        ;;
    none)
        echo "   ⏭️  Skipping optional tiers (fallback to Tier 1)"
        ;;
esac

# 4. Create plugin directories
echo ""
echo "📁 Setting up plugin directories..."
mkdir -p ~/.corvin/video-producer/{outputs,metadata,audit,learning-events}
echo "   ✅ Directories created"

# 5. Verify installation
echo ""
echo "✔️  Verifying installation..."
python3 -c "
import sys
sys.path.insert(0, '$(pwd)/src')
try:
    from skill import TaskOrchestrator
    from maestro import Maestro
    from learning_event_store import LearningEventStore
    from tier_learning_optimizer import TierLearningOptimizer
    from threejs_renderer import ThreeJSRenderer
    from blender_async_executor import BlenderAsyncExecutor
    from tier_dispatcher import TierDispatcher
    from production_hardening import ProductionHardening
    print('✅ All modules imported successfully')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
"

# 6. Run production hardening checks
echo ""
echo "🔒 Running production hardening checks..."
python3 -c "
import sys
sys.path.insert(0, '$(pwd)/src')
from production_hardening import production_sign_off
if not production_sign_off():
    sys.exit(1)
"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ INSTALLATION COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Configure API keys in ~/.corvin/video-producer/config.json"
echo "  2. Start the plugin: corvinctl plugin start video-producer-skill-2.0"
echo "  3. Monitor logs: tail -f ~/.corvin/video-producer/plugin.log"
echo ""
