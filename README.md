# Niv Tools

**7 AI Developer Tools for Frappe Assistant Core (FAC)**

Custom MCP tools that extend Niv AI chatbot with powerful developer capabilities.

## Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `universal_search` | Search ALL fields across ALL DocTypes — names, amounts, status, dates |
| 2 | `explore_fields` | Show field data lineage — where data comes from, how it flows |
| 3 | `test_created_item` | Verify documents exist, validate by creating/deleting test records |
| 4 | `monitor_errors` | Fetch Error Log, group by type, detect patterns |
| 5 | `rollback_changes` | Disable/delete Custom Fields, Scripts, Property Setters |
| 6 | `introspect_system` | 6 scopes: apps, modules, doctypes, customizations, links, all |
| 7 | `map_relationships` | Map DocType connections — links, child tables, workflows, reverse links |

## Installation

```bash
# Requires Frappe Assistant Core (FAC) to be installed first
bench get-app https://github.com/kulharir7/niv_tools
bench --site your-site install-app niv_tools
```

## How It Works

Tools are auto-discovered by FAC via Frappe's hooks system. No manual configuration needed.

```python
# hooks.py
assistant_tools = [
    "niv_tools.tools.universal_search.UniversalSearch",
    "niv_tools.tools.field_explorer.FieldExplorer",
    "niv_tools.tools.test_created_item.TestCreatedItem",
    "niv_tools.tools.monitor_errors.MonitorErrors",
    "niv_tools.tools.rollback_changes.RollbackChanges",
    "niv_tools.tools.introspect_system.IntrospectSystem",
    "niv_tools.tools.map_relationships.MapRelationships",
]
```

## Requirements

- Frappe v14+ / v15+
- [Frappe Assistant Core (FAC)](https://github.com/buildswithpaul/Frappe_Assistant_Core)
- [Niv AI](https://github.com/kulharir7/niv_ai) (optional — tools work with any FAC-compatible chatbot)

## License

MIT
