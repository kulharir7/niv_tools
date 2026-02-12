app_name = "niv_tools"
app_title = "Niv Tools"
app_publisher = "Ravindra Kulhari"
app_description = "Custom AI tools for Niv AI chatbot via FAC MCP"
app_version = "0.1.0"

# FAC Custom Tools Registration
# These tools are auto-discovered by FAC via hooks and served via MCP
assistant_tools = [
    "niv_tools.tools.universal_search.UniversalSearch",
    "niv_tools.tools.field_explorer.FieldExplorer",
    "niv_tools.tools.test_created_item.TestCreatedItem",
    "niv_tools.tools.monitor_errors.MonitorErrors",
    "niv_tools.tools.rollback_changes.RollbackChanges",
    "niv_tools.tools.introspect_system.IntrospectSystem",
    "niv_tools.tools.map_relationships.MapRelationships",
]
