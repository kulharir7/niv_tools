# Introspect System Tool - Full system map: apps, modules, DocTypes, customizations

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class IntrospectSystem(BaseTool):
    """Full system introspection - installed apps, modules, DocType relationships, customizations."""

    def __init__(self):
        super().__init__()
        self.name = "introspect_system"
        self.description = (
            "Get a full system map: installed apps and versions, modules and their DocTypes, "
            "customizations (Custom Fields, Scripts, Property Setters), and DocType link/dependency graphs. "
            "Use to understand the system before making changes."
        )
        self.category = "Metadata"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["apps", "modules", "doctypes", "customizations", "links", "all"],
                    "description": "What to introspect: apps, modules, doctypes, customizations, links, or all",
                },
                "doctype": {
                    "type": "string",
                    "description": "Optional: specific DocType for detailed info (used with doctypes/links/customizations scope)",
                },
                "module": {
                    "type": "string",
                    "description": "Optional: filter by module name",
                },
            },
            "required": ["scope"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            scope = arguments.get("scope", "all")
            doctype = arguments.get("doctype", "")
            module = arguments.get("module", "")

            result = {"success": True}

            if scope == "apps" or scope == "all":
                result["apps"] = self._get_apps()
            if scope == "modules" or scope == "all":
                result["modules"] = self._get_modules(module)
            if scope == "doctypes" or scope == "all":
                result["doctypes"] = self._get_doctypes(doctype, module)
            if scope == "customizations" or scope == "all":
                result["customizations"] = self._get_customizations(doctype)
            if scope == "links" or scope == "all":
                if doctype:
                    result["links"] = self._get_links(doctype)
                elif scope == "links":
                    return {"success": False, "error": "doctype is required for links scope"}

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_apps(self):
        """Get installed apps and versions."""
        try:
            apps = frappe.get_installed_apps()
            app_info = []
            for app in apps:
                try:
                    version = frappe.get_attr(app + ".__version__") if app != "frappe" else frappe.__version__
                except Exception:
                    version = "unknown"
                app_info.append({"app": app, "version": str(version)})
            return app_info
        except Exception as e:
            return {"error": str(e)}

    def _get_modules(self, module_filter=""):
        """Get modules with DocType counts."""
        try:
            filters = {}
            if module_filter:
                filters["module"] = module_filter

            modules = frappe.get_all(
                "DocType",
                filters=filters,
                fields=["module", "count(name) as doctype_count"],
                group_by="module",
                order_by="doctype_count desc",
            )
            return [{"module": m.get("module", ""), "doctype_count": m.get("doctype_count", 0)} for m in modules]
        except Exception as e:
            return {"error": str(e)}

    def _get_doctypes(self, doctype_filter="", module_filter=""):
        """Get DocTypes, optionally filtered."""
        try:
            filters = {}
            if doctype_filter:
                filters["name"] = doctype_filter
            if module_filter:
                filters["module"] = module_filter

            doctypes = frappe.get_all(
                "DocType",
                filters=filters,
                fields=["name", "module", "custom", "issingle", "istable"],
                order_by="name",
                limit_page_length=100,
            )

            results = []
            for dt in doctypes:
                info = {
                    "name": dt.get("name", ""),
                    "module": dt.get("module", ""),
                    "custom": dt.get("custom", 0),
                    "is_single": dt.get("issingle", 0),
                    "is_child": dt.get("istable", 0),
                }
                if doctype_filter:
                    # Detailed view for single DocType
                    try:
                        meta = frappe.get_meta(dt.get("name", ""))
                        info["fields_count"] = len(meta.fields)
                        info["has_workflow"] = bool(meta.get("workflow"))
                        info["autoname"] = getattr(meta, "autoname", "")
                    except Exception:
                        pass
                results.append(info)

            return results
        except Exception as e:
            return {"error": str(e)}

    def _get_customizations(self, doctype_filter=""):
        """Get Custom Fields, Client Scripts, Server Scripts, Property Setters."""
        try:
            result = {}

            # Custom Fields
            try:
                cf_filters = {}
                if doctype_filter:
                    cf_filters["dt"] = doctype_filter
                custom_fields = frappe.get_all(
                    "Custom Field",
                    filters=cf_filters,
                    fields=["name", "dt", "fieldname", "fieldtype", "label"],
                    limit_page_length=50,
                )
                result["custom_fields"] = {"count": len(custom_fields), "items": custom_fields}
            except Exception as e:
                result["custom_fields"] = {"error": str(e)}

            # Client Scripts
            try:
                cs_filters = {}
                if doctype_filter:
                    cs_filters["dt"] = doctype_filter
                client_scripts = frappe.get_all(
                    "Client Script",
                    filters=cs_filters,
                    fields=["name", "dt", "enabled", "script_type"],
                    limit_page_length=50,
                )
                result["client_scripts"] = {"count": len(client_scripts), "items": client_scripts}
            except Exception as e:
                result["client_scripts"] = {"error": str(e)}

            # Server Scripts
            try:
                ss_filters = {}
                if doctype_filter:
                    ss_filters["reference_doctype"] = doctype_filter
                server_scripts = frappe.get_all(
                    "Server Script",
                    filters=ss_filters,
                    fields=["name", "reference_doctype", "script_type", "disabled"],
                    limit_page_length=50,
                )
                result["server_scripts"] = {"count": len(server_scripts), "items": server_scripts}
            except Exception as e:
                result["server_scripts"] = {"error": str(e)}

            # Property Setters
            try:
                ps_filters = {}
                if doctype_filter:
                    ps_filters["doc_type"] = doctype_filter
                prop_setters = frappe.get_all(
                    "Property Setter",
                    filters=ps_filters,
                    fields=["name", "doc_type", "field_name", "property", "value"],
                    limit_page_length=50,
                )
                result["property_setters"] = {"count": len(prop_setters), "items": prop_setters}
            except Exception as e:
                result["property_setters"] = {"error": str(e)}

            return result
        except Exception as e:
            return {"error": str(e)}

    def _get_links(self, doctype):
        """Get dependency graph for a DocType - what links to it and what it links to."""
        try:
            if not frappe.db.exists("DocType", doctype):
                return {"error": "DocType '{}' does not exist".format(doctype)}

            meta = frappe.get_meta(doctype)
            links_to = []  # Fields in this DocType that link to others
            linked_from = []  # Other DocTypes that link to this one

            # Outgoing links
            for field in meta.fields:
                if field.fieldtype == "Link" and field.options:
                    links_to.append({
                        "fieldname": field.fieldname,
                        "linked_doctype": field.options,
                        "reqd": field.reqd or 0,
                    })
                elif field.fieldtype == "Table" and field.options:
                    links_to.append({
                        "fieldname": field.fieldname,
                        "linked_doctype": field.options,
                        "type": "child_table",
                    })

            # Incoming links - other DocTypes that have Link fields pointing here
            try:
                incoming = frappe.get_all(
                    "DocField",
                    filters={"fieldtype": "Link", "options": doctype},
                    fields=["parent", "fieldname"],
                    limit_page_length=50,
                )
                seen = set()
                for link in incoming:
                    parent = link.get("parent", "")
                    if parent and parent != doctype and parent not in seen:
                        seen.add(parent)
                        linked_from.append({
                            "doctype": parent,
                            "fieldname": link.get("fieldname", ""),
                        })
            except Exception:
                pass

            # Also check Custom Fields for incoming links
            try:
                custom_incoming = frappe.get_all(
                    "Custom Field",
                    filters={"fieldtype": "Link", "options": doctype},
                    fields=["dt", "fieldname"],
                    limit_page_length=50,
                )
                for link in custom_incoming:
                    dt_name = link.get("dt", "")
                    if dt_name and dt_name != doctype:
                        linked_from.append({
                            "doctype": dt_name,
                            "fieldname": link.get("fieldname", ""),
                            "custom": True,
                        })
            except Exception:
                pass

            return {
                "doctype": doctype,
                "links_to": links_to,
                "linked_from": linked_from,
                "outgoing_count": len(links_to),
                "incoming_count": len(linked_from),
            }
        except Exception as e:
            return {"error": str(e)}
