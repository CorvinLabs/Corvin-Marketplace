"""L34 data flow guard - Data flow classification and enforcement.

Classifies data by sensitivity level (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)
and enforces flow rules per engine/destination.

Reference: ADR-0320 (Metric Collection), L34 (Data Flow Guard), GDPR Art. 32
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re

_logger = logging.getLogger(__name__)


class DataClassification(Enum):
    """Data sensitivity classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # PII, secrets, etc.


@dataclass(frozen=True)
class DataFlowRule:
    """A rule governing data flow to a destination."""
    from_engine: str  # e.g., "claude-opus", "claude-haiku"
    to_destination: str  # e.g., "local", "cloud", "api"
    min_classification: DataClassification  # minimum data class allowed
    allow_flow: bool


class FlowGuard:
    """L34 data flow guard plugin - enforce data flow rules per engine/destination."""

    # PII/Secret detection patterns (fail-closed)
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
        "ssn": r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b",
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "api_key": r"(?:api[_-]?key|secret|password|token)[\s]*[:=][\s]*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        "aws_key": r"AKIA[0-9A-Z]{16}",
        "jwt": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+",
    }

    # Engine trust levels
    TRUSTED_ENGINES = {"claude-opus"}  # Opus can send RESTRICTED
    UNTRUSTED_ENGINES = {"claude-haiku"}  # Haiku can only send PUBLIC/INTERNAL

    # Flow rules (fail-closed by default)
    DEFAULT_RULES = [
        DataFlowRule("claude-opus", "local", DataClassification.RESTRICTED, True),
        DataFlowRule("claude-opus", "cloud", DataClassification.CONFIDENTIAL, True),
        DataFlowRule("claude-opus", "api", DataClassification.INTERNAL, True),
        DataFlowRule("claude-haiku", "local", DataClassification.INTERNAL, True),
        DataFlowRule("claude-haiku", "cloud", DataClassification.PUBLIC, True),
        DataFlowRule("claude-haiku", "api", DataClassification.PUBLIC, True),
    ]

    def __init__(self):
        """Initialize the flow guard."""
        self.enabled = True
        self.rules = self.DEFAULT_RULES.copy()
        self._classified_cache: dict[str, DataClassification] = {}

    async def initialize(self, context):
        """Initialize the plugin with context."""
        _logger.info("FlowGuard initialized")

    async def classify_data(self, data: str) -> DataClassification:
        """Classify data by sensitivity level (fail-closed).

        Args:
            data: String data to classify

        Returns:
            DataClassification level (RESTRICTED if PII/secrets detected)
        """
        try:
            # Check cache
            if data in self._classified_cache:
                return self._classified_cache[data]

            # Detect PII/secrets (fail-closed - mark as RESTRICTED if found)
            for pattern_name, pattern in self.PII_PATTERNS.items():
                if re.search(pattern, data, re.IGNORECASE):
                    _logger.warning(f"PII detected ({pattern_name}) - classifying as RESTRICTED")
                    result = DataClassification.RESTRICTED
                    self._classified_cache[data] = result
                    return result

            # Heuristics for classification
            lower_data = data.lower()

            if any(keyword in lower_data for keyword in ["secret", "password", "token", "api_key", "private"]):
                result = DataClassification.RESTRICTED
            elif any(keyword in lower_data for keyword in ["confidential", "internal", "proprietary"]):
                result = DataClassification.CONFIDENTIAL
            elif any(keyword in lower_data for keyword in ["internal", "company"]):
                result = DataClassification.INTERNAL
            else:
                result = DataClassification.PUBLIC

            self._classified_cache[data] = result
            return result
        except Exception as e:
            _logger.error(f"Data classification failed: {e}")
            # Fail-closed: mark as RESTRICTED if error
            return DataClassification.RESTRICTED

    async def check_flow_allowed(
        self, engine: str, destination: str, data_classification: DataClassification
    ) -> bool:
        """Check if data flow is allowed (fail-closed).

        Args:
            engine: Source engine (e.g., "claude-opus")
            destination: Target destination (e.g., "cloud")
            data_classification: Classification level of the data

        Returns:
            True if flow allowed, False otherwise
        """
        try:
            # Find matching rule
            matching_rules = [
                r for r in self.rules
                if r.from_engine == engine and r.to_destination == destination
            ]

            if not matching_rules:
                _logger.error(f"No flow rule for {engine}->{destination}: DENYING")
                return False  # Fail-closed

            rule = matching_rules[0]

            # Check if data classification meets minimum requirement
            # Hierarchy: PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED
            classification_order = {
                DataClassification.PUBLIC: 0,
                DataClassification.INTERNAL: 1,
                DataClassification.CONFIDENTIAL: 2,
                DataClassification.RESTRICTED: 3,
            }

            data_level = classification_order[data_classification]
            min_level = classification_order[rule.min_classification]

            # Allow only if data classification <= rule minimum (fail-closed)
            if data_level <= min_level and rule.allow_flow:
                _logger.debug(f"Flow allowed: {engine}->{destination} ({data_classification.value})")
                return True

            _logger.warning(
                f"Flow denied: {engine}->{destination} ({data_classification.value}) "
                f"exceeds rule minimum ({rule.min_classification.value})"
            )
            return False
        except Exception as e:
            _logger.error(f"Flow check failed: {e}")
            return False  # Fail-closed

    async def execute(self, operation: str, **kwargs) -> dict:
        """Execute flow guard operations.

        Args:
            operation: "classify" or "check_flow"
            **kwargs: Operation-specific arguments

        Returns:
            Operation result
        """
        try:
            if operation == "classify":
                data = kwargs.get("data", "")
                classification = await self.classify_data(data)
                return {"classification": classification.value, "success": True}

            elif operation == "check_flow":
                engine = kwargs.get("engine")
                destination = kwargs.get("destination")
                data = kwargs.get("data", "")

                # Classify the data
                data_classification = await self.classify_data(data)

                # Check if flow is allowed
                allowed = await self.check_flow_allowed(engine, destination, data_classification)

                return {
                    "allowed": allowed,
                    "data_classification": data_classification.value,
                    "engine": engine,
                    "destination": destination,
                    "success": True
                }

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            _logger.error(f"Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check plugin health."""
        try:
            # Test classification
            test_result = await self.classify_data("test data")
            return test_result == DataClassification.PUBLIC
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown the plugin."""
        _logger.info("FlowGuard shutting down")
