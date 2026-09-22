"""Design Assistant — Claude-powered workflow design handler (Phase 7)."""
import asyncio
import logging
import subprocess
from typing import Optional

_log = logging.getLogger(__name__)


class DesignAssistant:
    """Claude-powered workflow design assistant.

    Handles:
    - Template suggestions based on user input
    - Workflow generation via Claude CLI
    - Design conversation persistence
    - YAML draft generation
    """

    # Workflow templates with keyword matching
    TEMPLATES = {
        "daily-digest": {
            "keywords": ["daily", "digest", "rss", "feed", "morning", "news", "summary"],
            "description": "Summarize and deliver daily news/updates",
            "example_prompt": "Create a workflow that fetches news, summarizes key stories, and sends a daily digest email",
            "steps": "TRIGGER > fetch_content > summarise > deliver",
        },
        "content-moderation": {
            "keywords": ["moderation", "content", "filter", "safety", "detect"],
            "description": "Review and moderate user-generated content",
            "example_prompt": "Build a workflow that reviews content, flags violations, and notifies moderators",
            "steps": "TRIGGER > classify > filter > log",
        },
        "data-pipeline": {
            "keywords": ["etl", "pipeline", "extract", "transform", "load", "data", "api"],
            "description": "Extract, transform, load data",
            "example_prompt": "Create an ETL pipeline that pulls data from APIs, transforms it, and loads to database",
            "steps": "TRIGGER > fetch > transform > load",
        },
        "customer-support": {
            "keywords": ["support", "customer", "ticket", "help", "response"],
            "description": "Automate customer support workflows",
            "example_prompt": "Build a workflow that routes support tickets, generates responses, and tracks resolution",
            "steps": "TRIGGER > route > respond > track",
        },
        "lead-scoring": {
            "keywords": ["lead", "score", "sales", "prospect", "qualify"],
            "description": "Score and qualify leads for sales",
            "example_prompt": "Create a workflow that scores leads by engagement, qualifies them, and notifies sales",
            "steps": "TRIGGER > collect > score > notify",
        },
        "quality-assurance": {
            "keywords": ["qa", "quality", "test", "validate", "assert"],
            "description": "Automated QA and testing workflows",
            "example_prompt": "Build a workflow that runs tests, reports results, and blocks bad deployments",
            "steps": "TRIGGER > test > validate > report",
        },
    }

    def __init__(self, storage_backend=None, audit_backend=None):
        """Initialize design assistant.

        Args:
            storage_backend: Storage backend for persisting conversations
            audit_backend: Audit backend for logging design decisions
        """
        self.storage = storage_backend
        self.audit = audit_backend

    async def process_message(
        self,
        workflow_id: str,
        user_message: str,
        template_hint: Optional[str] = None,
    ) -> str:
        """Process user message and generate workflow assistance.

        This invokes Claude via subprocess to provide design guidance.

        Args:
            workflow_id: Workflow ID for context
            user_message: User's design intent
            template_hint: Optional template name hint

        Returns:
            Claude's response text

        Raises:
            RuntimeError: If Claude CLI is unavailable or times out
        """

        # Build system prompt
        system_prompt = self._build_system_prompt(template_hint)

        # Call Claude CLI (via subprocess)
        try:
            response = await self._invoke_claude(user_message, system_prompt)
            return response
        except Exception as e:
            _log.error(f"Claude invocation failed for workflow {workflow_id}: {e}")
            raise

    def suggest_template(self, query: str) -> Optional[str]:
        """Suggest a workflow template based on keywords.

        Args:
            query: User's workflow description

        Returns:
            Template name if matched, None otherwise
        """
        query_lower = query.lower()
        for template_name, template_info in self.TEMPLATES.items():
            keywords = template_info.get("keywords", [])
            if any(kw in query_lower for kw in keywords):
                return template_name
        return None

    def get_template_info(self, template_name: str) -> Optional[dict]:
        """Get template information.

        Args:
            template_name: Template name

        Returns:
            Template dict with description, steps, example_prompt
        """
        if template_name in self.TEMPLATES:
            return self.TEMPLATES[template_name]
        return None

    def _build_system_prompt(self, template_hint: Optional[str] = None) -> str:
        """Build system prompt for Claude.

        Args:
            template_hint: Optional template to contextualize the prompt

        Returns:
            System prompt string
        """
        base = """You are an expert workflow designer helping users build automation workflows.

Your role:
1. Understand the user's workflow intent from their description
2. Ask clarifying questions if needed
3. Suggest a workflow structure (steps, triggers, conditions)
4. Provide a YAML skeleton the user can copy/edit
5. Explain each component and how it works

Keep responses concise, actionable, and focused on the workflow design.
Always suggest concrete YAML examples.

Format YAML in a code block like:
```yaml
awp: "1.0.0"
workflow:
  name: example_workflow
  ...
```

Encourage the user to iterate on the design."""

        if template_hint and template_hint in self.TEMPLATES:
            template = self.TEMPLATES[template_hint]
            base += f"\n\nTemplate context: {template['description']}"
            base += f"\nExample prompt: {template['example_prompt']}"

        return base

    async def _invoke_claude(self, user_message: str, system_prompt: str) -> str:
        """Invoke Claude CLI and return response.

        Args:
            user_message: The user's design intent
            system_prompt: System prompt to guide Claude

        Returns:
            Claude's response text

        Raises:
            RuntimeError: If Claude CLI is unavailable or times out
        """

        def _run_claude_sync():
            try:
                # Construct prompt with system context
                full_prompt = f"""{system_prompt}

User: {user_message}"""

                # Invoke Claude CLI
                result = subprocess.run(
                    ["claude", "-p", "--max-tokens", "1000", "--output-format", "text"],
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    raise RuntimeError(
                        f"Claude CLI error (rc={result.returncode}): {result.stderr.strip()[:200]}"
                    )
            except FileNotFoundError:
                raise RuntimeError("Claude CLI not found — ensure claude is in PATH")
            except subprocess.TimeoutExpired:
                raise RuntimeError("Claude CLI timeout after 30s — response too slow")
            except Exception as e:
                raise RuntimeError(f"Claude invocation error: {e}")

        # Run in thread pool to avoid blocking
        return await asyncio.to_thread(_run_claude_sync)
