# Field Explorer Tool - Explains every field in a DocType
# Shows data lineage: fetch_from, formulas, child tables, dependencies
# Registered via FAC hooks, served via MCP to Niv AI

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class FieldExplorer(BaseTool):
    """Explains DocType fields - where data comes from, dependencies, relationships"""

    def __init__(self):
        super().__init__()
        self.name = "explore_fields"
        self.description = (
            "Field Explorer - explains every field in a DocType: "
            "what it does, where data comes from (fetch_from, formula, Link), "
            "child table relationships, and field dependencies. "
            "Use when a user wants to understand any form/document structure."
        )
        self.category = "Metadata"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "DocType to explore (e.g., 'Sales Order', 'Customer', 'Item')"
                },
                "field": {
                    "type": "string",
                    "description": "Optional: specific field name for detailed info"
                },
                "section": {
                    "type": "string",
                    "description": "Optional: section label to filter fields"
                },
            },
            "required": ["doctype"],
        }

    def execute(self, arguments):
        doctype = arguments.get("doctype")
        field_name = arguments.get("field")
        section = arguments.get("section")

        if not frappe.db.exists("DocType", doctype):
            return {"success": False, "error": "DocType '%s' not found" % doctype}
        if not frappe.has_permission(doctype, "read"):
            return {"success": False, "error": "No read permission for '%s'" % doctype}

        meta = frappe.get_meta(doctype)

        if field_name:
            return self._explore_single_field(meta, doctype, field_name)
        return self._explore_all_fields(meta, doctype, section)

    def _get_field_source(self, field):
        source = {"type": "user_input", "description": "Manually entered by user"}

        if field.fetch_from:
            source = {
                "type": "fetch_from",
                "fetch_from": field.fetch_from,
                "description": "Auto-fetched from linked document: %s" % field.fetch_from,
                "editable": not bool(field.fetch_if_empty),
            }
        elif field.fieldtype == "Link":
            source = {
                "type": "link",
                "links_to": field.options,
                "description": "Links to %s DocType. Select from existing records." % field.options,
            }
        elif field.read_only and field.fieldtype in ("Currency", "Float", "Int", "Percent"):
            source = {
                "type": "computed",
                "description": "Calculated automatically (read-only). Likely aggregated from child table or server logic.",
            }
        elif field.fieldtype == "Select":
            options = [o.strip() for o in (field.options or "").split("\n") if o.strip()]
            source = {
                "type": "select",
                "options": options,
                "description": "Dropdown with %d options" % len(options),
            }
        elif field.fieldtype == "Table":
            source = {
                "type": "child_table",
                "child_doctype": field.options,
                "description": "Contains rows of %s (child table)" % field.options,
            }
        elif field.fieldtype == "Dynamic Link":
            source = {
                "type": "dynamic_link",
                "depends_on": field.options,
                "description": "Dynamic link - DocType determined by '%s' field" % field.options,
            }

        return source

    def _get_dependents(self, meta, field_name):
        dependents = []
        for f in meta.fields:
            if f.fetch_from and field_name in str(f.fetch_from):
                dependents.append({"field": f.fieldname, "relation": "fetch_from", "detail": f.fetch_from})
            if f.depends_on and field_name in str(f.depends_on):
                dependents.append({"field": f.fieldname, "relation": "visibility_depends_on", "detail": f.depends_on})
            if f.mandatory_depends_on and field_name in str(f.mandatory_depends_on):
                dependents.append({"field": f.fieldname, "relation": "mandatory_depends_on", "detail": f.mandatory_depends_on})
        return dependents

    def _explore_single_field(self, meta, doctype, field_name):
        field = meta.get_field(field_name)
        if not field:
            if field_name == "name":
                return {
                    "success": True, "doctype": doctype,
                    "field": {
                        "fieldname": "name", "label": "ID / Name", "fieldtype": "Data",
                        "description": "Unique identifier. Auto-generated by naming series.",
                        "source": {"type": "auto_generated", "description": "Auto-generated by naming series"},
                        "dependents": self._get_dependents(meta, "name"),
                    }
                }
            return {"success": False, "error": "Field '%s' not found in %s" % (field_name, doctype)}

        source = self._get_field_source(field)
        dependents = self._get_dependents(meta, field_name)

        field_info = {
            "fieldname": field.fieldname, "label": field.label, "fieldtype": field.fieldtype,
            "description": field.description or "", "required": bool(field.reqd),
            "read_only": bool(field.read_only), "unique": bool(field.unique),
            "default": field.default, "source": source, "dependents": dependents,
            "in_list_view": bool(field.in_list_view), "hidden": bool(field.hidden),
        }

        if field.fieldtype == "Table" and field.options:
            try:
                child_meta = frappe.get_meta(field.options)
                field_info["child_table_fields"] = [
                    {"fieldname": cf.fieldname, "label": cf.label, "fieldtype": cf.fieldtype, "required": bool(cf.reqd)}
                    for cf in child_meta.fields
                    if cf.fieldtype not in ("Section Break", "Column Break", "Tab Break")
                ]
            except Exception:
                pass

        return {"success": True, "doctype": doctype, "field": field_info}

    def _explore_all_fields(self, meta, doctype, section_filter=None):
        sections = []
        current_section = {"label": "Default", "fields": []}

        for field in meta.fields:
            if field.fieldtype in ("Tab Break", "Section Break"):
                if current_section["fields"]:
                    sections.append(current_section)
                current_section = {"label": field.label or field.fieldtype.replace(" Break", ""), "fields": []}
                continue
            if field.fieldtype == "Column Break" or field.hidden:
                continue

            source = self._get_field_source(field)
            current_section["fields"].append({
                "fieldname": field.fieldname, "label": field.label, "fieldtype": field.fieldtype,
                "required": bool(field.reqd),
                "source_type": source["type"],
                "source_detail": source.get("fetch_from") or source.get("links_to") or source.get("child_doctype") or "",
            })

        if current_section["fields"]:
            sections.append(current_section)

        if section_filter:
            sections = [s for s in sections if section_filter.lower() in (s.get("label") or "").lower()]

        total = sum(len(s["fields"]) for s in sections)
        return {
            "success": True, "doctype": doctype,
            "title_field": meta.title_field, "is_submittable": bool(meta.is_submittable),
            "summary": {
                "total_fields": total,
                "required_fields": sum(1 for s in sections for f in s["fields"] if f["required"]),
                "auto_fetched_fields": sum(1 for s in sections for f in s["fields"] if f["source_type"] == "fetch_from"),
                "link_fields": sum(1 for s in sections for f in s["fields"] if f["source_type"] == "link"),
                "child_tables": sum(1 for s in sections for f in s["fields"] if f["source_type"] == "child_table"),
                "computed_fields": sum(1 for s in sections for f in s["fields"] if f["source_type"] == "computed"),
                "sections": len(sections),
            },
            "sections": sections,
        }
