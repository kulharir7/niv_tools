# Map DocType Relationships — shows how DocTypes connect to each other
# Links TO other DocTypes, Links FROM other DocTypes, Child Tables, Workflows

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class MapRelationships(BaseTool):
    """Map all relationships for a DocType — links, child tables, workflows, auto-name"""

    def __init__(self):
        super().__init__()
        self.name = "map_relationships"
        self.description = (
            "Map all relationships for a DocType. Shows: "
            "1) What this DocType links TO (Link fields), "
            "2) What other DocTypes link TO this one (reverse links), "
            "3) Child tables, "
            "4) Workflow if any, "
            "5) Naming series, "
            "6) Auto-value/fetch_from fields, "
            "7) Connected documents flow (e.g. Quotation → Sales Order → Invoice). "
            "Essential for understanding ERPNext structure before creating new DocTypes."
        )
        self.category = "Developer"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "DocType name to map relationships for (e.g. 'Sales Order', 'Customer')"
                },
                "depth": {
                    "type": "integer",
                    "description": "How deep to follow links. 1=direct only, 2=one level deeper. Default 1. Max 3.",
                    "default": 1
                },
                "include_standard": {
                    "type": "boolean",
                    "description": "Include standard fields (owner, company, amended_from). Default false.",
                    "default": False
                }
            },
            "required": ["doctype"]
        }

    def execute(self, arguments):
        doctype = arguments.get("doctype", "").strip()
        depth = min(arguments.get("depth", 1), 3)
        include_standard = arguments.get("include_standard", False)

        if not doctype:
            return {"error": "doctype is required"}

        if not frappe.db.exists("DocType", doctype):
            # Try case-insensitive search
            found = frappe.db.sql(
                "SELECT name FROM tabDocType WHERE name LIKE %s LIMIT 5",
                ("%" + doctype + "%",), as_dict=True
            )
            if found:
                suggestions = [r["name"] for r in found]
                return {"error": "DocType '{}' not found. Did you mean: {}".format(doctype, ", ".join(suggestions))}
            return {"error": "DocType '{}' not found".format(doctype)}

        result = self._map_doctype(doctype, depth, include_standard, set())
        return result

    def _map_doctype(self, doctype, depth, include_standard, visited):
        if doctype in visited:
            return {"doctype": doctype, "note": "already mapped (circular reference)"}
        visited.add(doctype)

        meta = frappe.get_meta(doctype)
        result = {
            "doctype": doctype,
            "module": meta.module,
            "is_submittable": bool(meta.is_submittable),
            "is_child": bool(meta.istable),
            "is_single": bool(meta.issingle),
            "is_tree": bool(meta.is_tree),
        }

        # Naming
        if meta.autoname:
            result["naming"] = meta.autoname
        if meta.naming_rule:
            result["naming_rule"] = meta.naming_rule

        # Standard fields to skip
        standard_link_fields = {"owner", "modified_by", "company", "amended_from", "parent", "parenttype", "parentfield"}

        # 1. Links TO other DocTypes (this DocType's Link fields)
        links_to = []
        for f in meta.fields:
            if f.fieldtype == "Link" and f.options:
                if not include_standard and f.fieldname in standard_link_fields:
                    continue
                link_info = {
                    "fieldname": f.fieldname,
                    "label": f.label or f.fieldname,
                    "links_to": f.options,
                    "mandatory": bool(f.reqd),
                }
                if f.fetch_from:
                    link_info["fetch_from"] = f.fetch_from
                links_to.append(link_info)

            elif f.fieldtype == "Dynamic Link" and f.options:
                links_to.append({
                    "fieldname": f.fieldname,
                    "label": f.label or f.fieldname,
                    "links_to": "DYNAMIC (via {})".format(f.options),
                    "mandatory": bool(f.reqd),
                })

        if links_to:
            result["links_to"] = links_to

        # 2. Child Tables
        child_tables = []
        for f in meta.fields:
            if f.fieldtype == "Table" and f.options:
                child_meta = frappe.get_meta(f.options)
                child_links = []
                for cf in child_meta.fields:
                    if cf.fieldtype == "Link" and cf.options:
                        child_links.append({
                            "fieldname": cf.fieldname,
                            "links_to": cf.options
                        })
                child_info = {
                    "fieldname": f.fieldname,
                    "child_doctype": f.options,
                    "field_count": len([x for x in child_meta.fields if x.fieldtype not in ("Section Break", "Column Break", "Tab Break")]),
                }
                if child_links:
                    child_info["child_links"] = child_links
                child_tables.append(child_info)

        if child_tables:
            result["child_tables"] = child_tables

        # 3. Links FROM other DocTypes (reverse links — who links to this DocType)
        links_from = []
        try:
            # Find all Link fields pointing to this DocType
            link_fields = frappe.db.sql("""
                SELECT parent, fieldname, label, reqd
                FROM tabDocField
                WHERE fieldtype = 'Link' AND options = %s
                AND parent != %s
                ORDER BY parent
                LIMIT 50
            """, (doctype, doctype), as_dict=True)

            for lf in link_fields:
                # Skip internal/system DocTypes
                if lf.parent.startswith("__"):
                    continue
                links_from.append({
                    "from_doctype": lf.parent,
                    "fieldname": lf.fieldname,
                    "label": lf.label or lf.fieldname,
                    "mandatory": bool(lf.reqd),
                })

            # Also check Custom Fields
            custom_links = frappe.db.sql("""
                SELECT dt as parent, fieldname, label, reqd
                FROM `tabCustom Field`
                WHERE fieldtype = 'Link' AND options = %s
                ORDER BY dt
                LIMIT 20
            """, (doctype,), as_dict=True)

            for cl in custom_links:
                links_from.append({
                    "from_doctype": cl.parent,
                    "fieldname": cl.fieldname,
                    "label": cl.label or cl.fieldname,
                    "mandatory": bool(cl.reqd),
                    "custom": True,
                })
        except Exception:
            pass

        if links_from:
            result["links_from"] = links_from
            result["links_from_count"] = len(links_from)

        # 4. Workflow
        try:
            workflow = frappe.db.get_value(
                "Workflow", {"document_type": doctype, "is_active": 1},
                ["name", "workflow_state_field"], as_dict=True
            )
            if workflow:
                states = frappe.get_all(
                    "Workflow Document State",
                    filters={"parent": workflow.name},
                    fields=["state", "doc_status", "allow_edit"],
                    order_by="idx"
                )
                transitions = frappe.get_all(
                    "Workflow Transition",
                    filters={"parent": workflow.name},
                    fields=["state", "action", "next_state", "allowed"],
                    order_by="idx"
                )
                result["workflow"] = {
                    "name": workflow.name,
                    "state_field": workflow.workflow_state_field,
                    "states": [s.state for s in states],
                    "transitions": [
                        "{} --[{}]--> {} (by {})".format(t.state, t.action, t.next_state, t.allowed)
                        for t in transitions
                    ]
                }
        except Exception:
            pass

        # 5. Fetch From fields (auto-populated fields)
        fetch_fields = []
        for f in meta.fields:
            if f.fetch_from:
                fetch_fields.append({
                    "fieldname": f.fieldname,
                    "fetch_from": f.fetch_from,
                    "read_only": bool(f.read_only)
                })
        if fetch_fields:
            result["auto_fetch_fields"] = fetch_fields

        # 6. Document flow — connected via naming/amended_from
        if meta.is_submittable:
            result["submittable_flow"] = {
                "can_amend": bool(meta.allow_auto_repeat or any(
                    f.fieldname == "amended_from" for f in meta.fields
                )),
                "statuses": ["Draft", "Submitted", "Cancelled"]
            }

        # 7. Notifications/Auto-repeat linked
        try:
            notifs = frappe.get_all(
                "Notification",
                filters={"document_type": doctype, "enabled": 1},
                fields=["name", "event", "channel"],
                limit=5
            )
            if notifs:
                result["notifications"] = notifs
        except Exception:
            pass

        # 8. Server Scripts linked
        try:
            scripts = frappe.get_all(
                "Server Script",
                filters={"reference_doctype": doctype, "disabled": 0},
                fields=["name", "event_frequency"],
                limit=10
            )
            if scripts:
                result["server_scripts"] = scripts
        except Exception:
            pass

        # 9. Print Formats
        try:
            print_formats = frappe.get_all(
                "Print Format",
                filters={"doc_type": doctype, "disabled": 0},
                fields=["name", "standard"],
                limit=5
            )
            if print_formats:
                result["print_formats"] = print_formats
        except Exception:
            pass

        # 10. Record count
        try:
            if not meta.issingle and not meta.istable:
                count = frappe.db.count(doctype)
                result["record_count"] = count
        except Exception:
            pass

        # Deeper mapping
        if depth > 1 and links_to:
            deeper = {}
            for link in links_to[:5]:  # Max 5 to avoid explosion
                target = link.get("links_to", "")
                if target and not target.startswith("DYNAMIC") and target not in visited:
                    deeper[target] = self._map_doctype(target, depth - 1, include_standard, visited)
            if deeper:
                result["linked_doctypes_detail"] = deeper

        # Summary
        summary_parts = []
        if links_to:
            summary_parts.append("links to {} DocTypes".format(len(links_to)))
        if links_from:
            summary_parts.append("{} DocTypes link to it".format(len(links_from)))
        if child_tables:
            summary_parts.append("{} child tables".format(len(child_tables)))
        if result.get("workflow"):
            summary_parts.append("has active workflow")
        result["summary"] = "{}: {}".format(doctype, ", ".join(summary_parts) if summary_parts else "standalone DocType")

        return result
