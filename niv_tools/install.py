"""Install hooks for niv_tools.

Runs lightweight validations so v14/v15 installs are predictable.
"""
from __future__ import annotations

import importlib
import frappe


TOOL_PATHS = [
    "niv_tools.tools.universal_search.UniversalSearch",
    "niv_tools.tools.field_explorer.FieldExplorer",
    "niv_tools.tools.test_created_item.TestCreatedItem",
    "niv_tools.tools.monitor_errors.MonitorErrors",
    "niv_tools.tools.rollback_changes.RollbackChanges",
    "niv_tools.tools.introspect_system.IntrospectSystem",
    "niv_tools.tools.map_relationships.MapRelationships",
    "niv_tools.tools.build_blueprint.BuildBlueprint",
    "niv_tools.tools.verify_build.VerifyBuild",
]


def _import_string(path: str):
    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def after_install():
    """Validate installation and tool class imports."""
    missing = []

    # FAC is required for assistant_tools discovery
    if not frappe.db.exists("Installed Application", "frappe_assistant_core"):
        missing.append("frappe_assistant_core")

    bad_tools = []
    for path in TOOL_PATHS:
        try:
            _import_string(path)
        except Exception as e:
            bad_tools.append("{0} -> {1}".format(path, str(e)))

    if missing or bad_tools:
        msg_parts = []
        if missing:
            msg_parts.append("Missing apps: {0}".format(", ".join(missing)))
        if bad_tools:
            msg_parts.append("Tool import errors:\n- {0}".format("\n- ".join(bad_tools)))
        frappe.log_error("\n\n".join(msg_parts), "niv_tools install validation")

    # Non-blocking install: log only
    frappe.logger().info("niv_tools after_install validation complete")
