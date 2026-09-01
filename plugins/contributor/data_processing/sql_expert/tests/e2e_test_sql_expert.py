"""
End-to-end tests for sql_expert plugin.

Tests real plugin initialization, configuration, and execution flows.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sql_expert import SQLExpert


class TestSQLExpertE2E:
    """End-to-end tests for SQL Expert."""

    @pytest.mark.asyncio
    async def test_e2e_basic_optimization(self):
        """E2E test: Basic query optimization workflow."""
        # Setup
        plugin = SQLExpert()
        context = {
            "database_url": "postgresql://localhost/testdb",
            "optimization_level": "intermediate",
        }
        await plugin.initialize(context)

        # Execute: Optimize a query
        query = "SELECT * FROM users WHERE id = 1"
        result = await plugin.execute(query=query, optimize=True)

        # Verify
        assert result is not None
        assert "optimized_query" in result
        assert "suggestions" in result
        assert result["original_query"] == query

        # Cleanup
        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_analysis_workflow(self):
        """E2E test: Query analysis and index suggestion workflow."""
        plugin = SQLExpert()
        await plugin.initialize({"optimization_level": "advanced"})

        query = "SELECT u.id, u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE u.created_at > '2026-01-01'"

        # Analyze
        analysis = await plugin.analyze_plan(query)
        assert analysis["cost_estimate"] > 0
        assert len(analysis["bottlenecks"]) >= 0

        # Suggest indexes
        indexes = await plugin.suggest_index(query)
        assert "suggested_indexes" in indexes

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_multi_query_processing(self):
        """E2E test: Processing multiple queries in sequence."""
        plugin = SQLExpert()
        await plugin.initialize()

        queries = [
            ("SELECT * FROM products", "optimize"),
            ("SELECT * FROM sales WHERE year = 2026", "analyze"),
            ("SELECT * FROM customers WHERE user_id = 123", "suggest_index"),
        ]

        results = []
        for query, operation in queries:
            if operation == "optimize":
                result = await plugin.optimize_query(query)
            elif operation == "analyze":
                result = await plugin.analyze_plan(query)
            else:
                result = await plugin.suggest_index(query)

            results.append(result)
            assert result is not None

        assert len(results) == 3
        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_different_optimization_levels(self):
        """E2E test: Query optimization at different levels."""
        query = "SELECT col1, col2 FROM table1 WHERE id NOT IN (SELECT id FROM table2) OR status = 1"

        levels = ["basic", "intermediate", "advanced"]
        results = {}

        for level in levels:
            plugin = SQLExpert()
            plugin.optimization_level = level
            result = await plugin.optimize_query(query)
            results[level] = result
            await plugin.shutdown()

        # Each level should process the query
        assert all(r is not None for r in results.values())

    @pytest.mark.asyncio
    async def test_e2e_error_recovery(self):
        """E2E test: Error handling and recovery."""
        plugin = SQLExpert()
        await plugin.initialize()

        # Try empty query (should fail)
        try:
            await plugin.optimize_query("")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected

        # Continue with valid query
        result = await plugin.optimize_query("SELECT * FROM users")
        assert result is not None

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_realistic_workflow(self):
        """E2E test: Realistic DBA workflow."""
        plugin = SQLExpert()
        context = {
            "database_url": "postgresql://localhost/production",
            "optimization_level": "advanced",
        }
        await plugin.initialize(context)

        # Simulate DBA investigating slow query
        slow_query = (
            "SELECT u.id, u.email, COUNT(o.id) as order_count "
            "FROM users u "
            "LEFT JOIN orders o ON u.id = o.user_id "
            "WHERE u.created_at > '2025-01-01' "
            "GROUP BY u.id, u.email"
        )

        # Get suggestions
        optimized = await plugin.optimize_query(slow_query)
        analysis = await plugin.analyze_plan(slow_query)
        indexes = await plugin.suggest_index(slow_query)

        # Verify results
        assert optimized["original_query"] == slow_query
        assert analysis["cost_estimate"] > 0
        assert len(indexes["suggested_indexes"]) >= 0

        await plugin.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
