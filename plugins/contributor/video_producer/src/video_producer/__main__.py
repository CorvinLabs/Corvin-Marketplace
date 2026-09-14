"""CLI entry point for Video Producer Skill 2.0."""

import sys
import argparse
import asyncio
import json
from pathlib import Path

from .orchestrator import VideoProducerOrchestrator
from .exceptions import AnalysisGateFailedError


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Video Producer Skill 2.0 — Orchestrated video production system"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: orchestrate
    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Run full orchestration pipeline"
    )
    orchestrate_parser.add_argument(
        "--assets",
        type=str,
        required=True,
        help="Comma-separated list of asset paths (PPT, images, etc.)"
    )
    orchestrate_parser.add_argument(
        "--project-dir",
        type=str,
        default=".",
        help="Project directory (default: current directory)"
    )
    orchestrate_parser.add_argument(
        "--instructions",
        type=str,
        help="Optional JSON string with user instructions"
    )
    orchestrate_parser.add_argument(
        "--output",
        type=str,
        default="orchestration_result.json",
        help="Output file for result JSON"
    )

    # Command: health check
    health_parser = subparsers.add_parser(
        "health",
        help="Health check — verify plugin is working"
    )
    health_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.command == "orchestrate":
        return _cmd_orchestrate(args)
    elif args.command == "health":
        return _cmd_health(args)
    else:
        parser.print_help()
        return 1


def _cmd_orchestrate(args):
    """Execute orchestration pipeline."""
    try:
        # Parse assets
        asset_paths = [p.strip() for p in args.assets.split(",")]

        # Parse instructions if provided
        instructions = None
        if args.instructions:
            try:
                instructions = json.loads(args.instructions)
            except json.JSONDecodeError:
                print(f"❌ Error: Invalid JSON in --instructions: {args.instructions}")
                return 1

        # Verify assets exist
        missing = [p for p in asset_paths if not Path(p).exists()]
        if missing:
            print(f"❌ Error: Assets not found: {missing}")
            return 1

        # Run orchestrator
        print(f"📹 Video Producer — Orchestration Pipeline")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Assets: {asset_paths}")
        print(f"  Project: {args.project_dir}")
        print(f"  Instructions: {instructions or '(none)'}")
        print()

        orchestrator = VideoProducerOrchestrator(args.project_dir)
        result = asyncio.run(orchestrator.orchestrate(asset_paths, instructions))

        # Save result
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"✅ Orchestration complete")
        print(f"   Status: {result.get('status')}")
        print(f"   Output: {output_path}")

        # Print summary
        if result.get("status") == "success":
            analysis = result.get("analysis", {})
            storyboard = result.get("storyboard")
            print()
            print(f"  📊 Analysis:")
            print(f"     Facts: {len(analysis.get('factual_claims', []))}")
            print(f"     Ready: {analysis.get('ready_for_narration', False)}")
            if storyboard:
                print(f"  📝 Storyboard:")
                print(f"     Scenes: {len(storyboard.get('scenes', []))}")
            return 0
        else:
            blockers = result.get("analysis", {}).get("blockers", [])
            if blockers:
                print(f"  ⚠️  Blockers:")
                for blocker in blockers:
                    print(f"     • {blocker}")
            return 1

    except AnalysisGateFailedError as e:
        print(f"❌ Analysis gate failed:")
        print(f"   {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def _cmd_health(args):
    """Health check."""
    try:
        orchestrator = VideoProducerOrchestrator(".")
        optimizer = None
        panel = None

        if args.verbose:
            print("📹 Video Producer — Health Check")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Try to import all components
        try:
            from .learning_optimizer import VideoProducerLearningOptimizer
            optimizer = VideoProducerLearningOptimizer()
        except Exception as e:
            if args.verbose:
                print(f"⚠️  Learning optimizer unavailable: {e}")

        try:
            from .console_panel import VideoProducerPanel
            panel = VideoProducerPanel()
        except Exception as e:
            if args.verbose:
                print(f"⚠️  Console panel unavailable: {e}")

        status = "healthy" if orchestrator else "degraded"
        if args.verbose:
            print(f"  Orchestrator: ✅")
            print(f"  Optimizer: {'✅' if optimizer else '⚠️'}")
            print(f"  Console Panel: {'✅' if panel else '⚠️'}")
            print()
            print(f"Status: {status}")
        else:
            print(f"✅ {status}")

        return 0
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
