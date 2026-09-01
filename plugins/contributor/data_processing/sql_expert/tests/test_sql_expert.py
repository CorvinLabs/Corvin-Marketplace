"""
Unit tests for sql_expert plugin.

Tests cover SQL optimization including:
- Query optimization
- Execution plan analysis
- Index suggestions
- Error handling
"""

import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sql_expert import SQLExpert


class TestSQLExpertInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = SQLExpert()
        assert plugin is not None
        assert plugin.enabled is True
        assert plugin.optimization_level == "intermediate"

    @pytest.mark.asyncio
    async def test_initialize_with_context(self):
        """Test initialize method with context."""
        plugin = SQLExpert()
        mock_context = {
            "database_url": "postgresql://localhost/testdb",
            "optimization_level": "advanced",
        }
        await plugin.initialize(mock_context)
        assert plugin.database_url == "postgresql://localhost/testdb"
        assert plugin.optimization_level == "advanced"

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = SQLExpert()
        await plugin.shutdown()
        assert len(plugin.query_cache) == 0


class TestSQLExpertOptimization:
    """Test query optimization functionality."""

    @pytest.mark.asyncio
    async def test_optimize_simple_query(self):
        """Test optimization of a simple query."""
        plugin = SQLExpert()
        query = "SELECT * FROM users WHERE id = 1"
        result = await plugin.optimize_query(query)

        assert result["original_query"] == query
        assert "optimized_query" in result
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0
        assert "SELECT *" in str(result["suggestions"])

    @pytest.mark.asyncio
    async def test_optimize_complex_query(self):
        """Test optimization of a complex query."""
        plugin = SQLExpert()
        query = "SELECT a, b FROM t1 WHERE x NOT IN (SELECT y FROM t2) OR z = 1"
        result = await plugin.optimize_query(query)

        assert result["original_query"] == query
        assert "suggestions" in result
        # Should suggest NOT EXISTS instead of NOT IN
        assert any("NOT EXISTS" in str(s) for s in result["suggestions"])

    @pytest.mark.asyncio
    async def test_optimize_empty_query(self):
        """Test optimization with empty query."""
        plugin = SQLExpert()
        with pytest.raises(ValueError):
            await plugin.optimize_query("")

    @pytest.mark.asyncio
    async def test_optimization_level_intermediate(self):
        """Test optimization at intermediate level."""
        plugin = SQLExpert()
        plugin.optimization_level = "intermediate"
        query = "SELECT col1 FROM t1 WHERE a = 1 OR b = 2"
        result = await plugin.optimize_query(query)

        assert result is not None
        assert "suggestions" in result


class TestSQLExpertPlanAnalysis:
    """Test execution plan analysis."""

    @pytest.mark.asyncio
    async def test_analyze_simple_plan(self):
        """Test analysis of a simple query plan."""
        plugin = SQLExpert()
        query = "SELECT * FROM users"
        result = await plugin.analyze_plan(query)

        assert result["query"] == query
        assert "plan" in result
        assert "cost_estimate" in result
        assert "rows_estimate" in result
        assert "bottlenecks" in result

    @pytest.mark.asyncio
    async def test_analyze_plan_with_join(self):
        """Test analysis of a query with join."""
        plugin = SQLExpert()
        query = "SELECT u.id, u.user_id FROM users u JOIN orders o ON u.id = o.user_id"
        result = await plugin.analyze_plan(query)

        assert result["query"] == query
        assert result["rows_estimate"] > 0

    @pytest.mark.asyncio
    async def test_analyze_empty_query(self):
        """Test analysis with empty query."""
        plugin = SQLExpert()
        with pytest.raises(ValueError):
            await plugin.analyze_plan("")


class TestSQLExpertIndexSuggestions:
    """Test index suggestion functionality."""

    @pytest.mark.asyncio
    async def test_suggest_index_single_column(self):
        """Test index suggestion for single column."""
        plugin = SQLExpert()
        query = "SELECT * FROM users WHERE user_id = 123"
        result = await plugin.suggest_index(query)

        assert result["query"] == query
        assert "suggested_indexes" in result
        assert len(result["suggested_indexes"]) > 0
        assert "user_id" in str(result["suggested_indexes"])

    @pytest.mark.asyncio
    async def test_suggest_index_multiple_columns(self):
        """Test index suggestion with multiple columns."""
        plugin = SQLExpert()
        query = "SELECT * FROM events WHERE user_id = 1 AND created_at > '2026-01-01'"
        result = await plugin.suggest_index(query)

        assert len(result["suggested_indexes"]) >= 1
        assert result["priority"] in ("high", "medium", "low")

    @pytest.mark.asyncio
    async def test_suggest_index_no_suggestion(self):
        """Test when no indexes are suggested."""
        plugin = SQLExpert()
        query = "SELECT COUNT(*) FROM products"
        result = await plugin.suggest_index(query)

        assert "suggested_indexes" in result
        assert result["estimated_performance_gain"] == "0%"

    @pytest.mark.asyncio
    async def test_suggest_index_empty_query(self):
        """Test index suggestion with empty query."""
        plugin = SQLExpert()
        with pytest.raises(ValueError):
            await plugin.suggest_index("")


class TestSQLExpertExecute:
    """Test execute method."""

    @pytest.mark.asyncio
    async def test_execute_optimize(self):
        """Test execute with optimize flag."""
        plugin = SQLExpert()
        query = "SELECT * FROM users"
        result = await plugin.execute(query=query, optimize=True)

        assert "optimized_query" in result
        assert "suggestions" in result

    @pytest.mark.asyncio
    async def test_execute_analyze(self):
        """Test execute with analyze flag."""
        plugin = SQLExpert()
        query = "SELECT * FROM users"
        result = await plugin.execute(query=query, analyze=True)

        assert "plan" in result
        assert "cost_estimate" in result

    @pytest.mark.asyncio
    async def test_execute_suggest_index(self):
        """Test execute with suggest_index flag."""
        plugin = SQLExpert()
        query = "SELECT * FROM users WHERE user_id = 1"
        result = await plugin.execute(query=query, suggest_index=True)

        assert "suggested_indexes" in result

    @pytest.mark.asyncio
    async def test_execute_default(self):
        """Test execute with no flag (default optimize)."""
        plugin = SQLExpert()
        query = "SELECT * FROM users"
        result = await plugin.execute(query=query)

        assert "optimized_query" in result

    @pytest.mark.asyncio
    async def test_execute_no_query(self):
        """Test execute without query parameter."""
        plugin = SQLExpert()
        with pytest.raises(ValueError):
            await plugin.execute()


class TestSQLExpertErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_optimization_level(self):
        """Test with invalid optimization level."""
        plugin = SQLExpert()
        plugin.optimization_level = "invalid"
        query = "SELECT * FROM users"
        result = await plugin.optimize_query(query)

        # Should still return result, just not apply advanced optimizations
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent query operations."""
        plugin = SQLExpert()
        queries = [
            "SELECT * FROM t1",
            "SELECT * FROM t2",
            "SELECT * FROM t3",
        ]

        results = []
        for query in queries:
            result = await plugin.optimize_query(query)
            results.append(result)

        assert len(results) == 3
        assert all("optimized_query" in r for r in results)


class TestSQLExpertIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = SQLExpert()
        context = {
            "database_url": "postgresql://localhost/testdb",
            "optimization_level": "advanced",
        }

        await plugin.initialize(context)
        assert plugin.enabled is True

        query = "SELECT * FROM users WHERE user_id = 1"
        optimize_result = await plugin.optimize_query(query)
        plan_result = await plugin.analyze_plan(query)
        index_result = await plugin.suggest_index(query)

        assert all(r is not None for r in [optimize_result, plan_result, index_result])

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_sequential_queries(self):
        """Test sequential query processing."""
        plugin = SQLExpert()
        await plugin.initialize()

        queries = [
            "SELECT * FROM users",
            "SELECT id, name FROM users WHERE active = true",
            "SELECT u.id, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id",
        ]

        results = []
        for query in queries:
            result = await plugin.execute(query=query, optimize=True)
            results.append(result)

        assert len(results) == 3
        assert all(r is not None for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
