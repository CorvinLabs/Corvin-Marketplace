# SQL Expert Plugin

Advanced SQL query optimization and debugging assistant for Corvin-Marketplace.

## Description

The SQL Expert plugin analyzes SQL queries and provides:
- Query optimization suggestions
- Execution plan analysis  
- Index recommendations
- Performance bottleneck identification

Perfect for data engineering tasks, database optimization, and performance tuning.

## Installation

```bash
pip install -e .
```

Or via Corvin-Marketplace:
```bash
corvin plugin install sql_expert
```

## Configuration

The plugin accepts configuration via context:

```json
{
  "database_url": "postgresql://user:pass@localhost/dbname",
  "optimization_level": "intermediate"
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `database_url` | string | (required) | Database connection string for analysis |
| `optimization_level` | string | `intermediate` | Depth of analysis: `basic`, `intermediate`, `advanced` |

## Usage

### Basic Query Optimization

```python
plugin = SQLExpert()
await plugin.initialize({"optimization_level": "intermediate"})

result = await plugin.optimize_query("SELECT * FROM users WHERE id = 1")
# Returns: { optimized_query, suggestions, estimated_improvement }
```

### Analyze Execution Plan

```python
result = await plugin.analyze_plan("SELECT u.id, o.amount FROM users u JOIN orders o ON u.id = o.user_id")
# Returns: { plan, cost_estimate, rows_estimate, execution_time_estimate_ms, bottlenecks }
```

### Get Index Suggestions

```python
result = await plugin.suggest_index("SELECT * FROM users WHERE user_id = 123 AND created_at > '2026-01-01'")
# Returns: { suggested_indexes, estimated_performance_gain, priority }
```

### Via execute() Method

```python
# Optimize
result = await plugin.execute(query="SELECT ...", optimize=True)

# Analyze plan
result = await plugin.execute(query="SELECT ...", analyze=True)

# Suggest indexes
result = await plugin.execute(query="SELECT ...", suggest_index=True)
```

## Architecture

```
┌─────────────────────────────────┐
│    SQL Query Input              │
│  (SELECT * FROM users...)       │
└────────────┬────────────────────┘
             │
      ┌──────▼──────┐
      │   Parser    │
      │ (Validate)  │
      └──────┬──────┘
             │
      ┌──────▼────────────┐
      │   Analyzer        │
      │ (Pattern Match)   │
      └──────┬────────────┘
             │
   ┌─────────┼─────────┐
   │         │         │
┌──▼──┐ ┌───▼───┐ ┌──▼────┐
│Opt. │ │Plan   │ │Index  │
│     │ │Anal.  │ │Sugg.  │
└──┬──┘ └───┬───┘ └──┬────┘
   │        │        │
   └────────┼────────┘
            │
     ┌──────▼───────┐
     │   Output     │
     │ (Suggestions)│
     └──────────────┘
```

## Features

- **Query Optimization**: Identifies and suggests improvements for inefficient queries
- **Execution Plan Analysis**: Analyzes query costs, row estimates, and execution times
- **Index Suggestions**: Recommends optimal indexes based on query patterns
- **Multi-level Analysis**: Basic, intermediate, and advanced optimization depths
- **Error Handling**: Graceful error handling with descriptive messages

## Testing

Run unit tests:

```bash
pytest tests/test_sql_expert.py -v
```

Run E2E tests:

```bash
pytest tests/e2e_test_sql_expert.py -v
```

## Limitations

- **Demo Implementation**: Current version uses heuristics for optimization
- **Database Agnostic**: Does not connect to actual database for real-time analysis
- **Limited Pattern Recognition**: Basic pattern matching; production version would use more advanced parsing
- **Configuration-only**: Requires manual configuration for each instance

## Requirements

- Python 3.8+
- sqlalchemy >= 2.0.0
- psycopg2 >= 2.9.0

## Author

Community Contributor (db-community.org)

## License

MIT - See LICENSE file

## Support

For issues, feature requests, or contributions, visit:
https://github.com/community-plugin/sql-expert
