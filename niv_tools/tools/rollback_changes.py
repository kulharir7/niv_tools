# Rollback Changes Tool - Undo custom changes safely

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class RollbackChanges(BaseTool):
    """Undo custom changes: Custom Fields, Property Setters, Client Scripts, Server Scripts."""

    def __init__(self):
        super().__init__()
        self.name = "rollback_changes"
        self.description = (
            "Undo or disable custom changes made by the chatbot or user. "
            "Supports rolling back Custom Fields, Property Setters, Client Scripts, "
            "and Server Scripts. Can delete or disable. Checks dependencies before deleting."
        )
        self.category = "Management"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "enum": ["Custom Field", "Property Setter", "Client Script", "Server Script"],
                    "description": "Type of customization to rollback",
                },
                "name": {
                    "type": "string",
                    "description": "Name/ID of the document to rollback",
                },
                "action": {
                    "type": "string",
                    "enum": ["delete", "disable"],
                    "description": "Action: delete (remove entirely) or disable (safer, can re-enable)",
                },
            },
            "required": ["doctype", "name", "action"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            doctype = arguments.get("doctype", "")
            name = arguments.get("name", "")
            action = arguments.get("action", "disable")

            if not doctype or not name:
                return {"success": False, "error": "doctype and name are required"}

            allowed = ["Custom Field", "Property Setter", "Client Script", "Server Script"]
            if doctype not in allowed:
                return {"success": False, "error": "doctype must be one of: {}".format(", ".join(allowed))}

            # Permission check
            try:
                frappe.has_permission(doctype, "write", throw=True)
            except Exception:
                return {"success": False, "error": "No write permission for {}".format(doctype)}

            if not frappe.db.exists(doctype, name):
                return {"success": False, "error": "{} '{}' does not exist".format(doctype, name)}

            doc = frappe.get_doc(doctype, name)

            if action == "disable":
                return self._disable(doc)
            elif action == "delete":
                return self._delete(doc)
            else:
                return {"success": False, "error": "action must be 'delete' or 'disable'"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _disable(self, doc):
        """Disable a script or customization."""
        try:
            dt = doc.doctype

            if dt in ("Client Script", "Server Script"):
                if hasattr(doc, "disabled"):
                    doc.disabled = 1
                    doc.save(ignore_permissions=False)
                    frappe.db.commit()
                    return {"success": True, "message": "{} '{}' has been disabled".format(dt, doc.name)}
                elif hasattr(doc, "enabled"):
                    doc.enabled = 0
                    doc.save(ignore_permissions=False)
                    frappe.db.commit()
                    return {"success": True, "message": "{} '{}' has been disabled".format(dt, doc.name)}
                else:
                    return {"success": False, "error": "{} does not support disable".format(dt)}

            elif dt == "Custom Field":
                # Custom Fields don't have a disable flag; suggest using hidden
                try:
                    doc.hidden = 1
                    doc.save(ignore_permissions=False)
                    frappe.db.commit()
                    return {
                        "success": True,
                        "message": "Custom Field '{}' has been hidden (set hidden=1). To fully remove, use action=delete.".format(doc.name),
                    }
                except Exception as e:
                    return {"success": False, "error": "Failed to hide field: {}".format(str(e))}

            elif dt == "Property Setter":
                # Property Setters can't be disabled, only deleted
                return {
                    "success": False,
                    "error": "Property Setters cannot be disabled, only deleted. Use action=delete.",
                }

            else:
                return {"success": False, "error": "Disable not supported for {}".format(dt)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _delete(self, doc):
        """Delete a customization after checking dependencies."""
        try:
            dt = doc.doctype

            # Check dependencies
            deps = self._check_dependencies(doc)
            if deps.get("has_dependencies"):
                return {
                    "success": False,
                    "error": "Cannot delete - has dependencies",
                    "dependencies": deps.get("details", []),
                    "suggestion": "Use action=disable instead, or remove dependencies first.",
                }

            # For scripts, recommend disable first
            if dt in ("Client Script", "Server Script"):
                is_disabled = getattr(doc, "disabled", 0) == 1
                if not is_disabled:
                    return {
                        "success": False,
                        "error": "Script is still enabled. Disable it first before deleting.",
                        "suggestion": "Use action=disable first, verify nothing breaks, then delete.",
                    }

            # Record what we're deleting for the response
            info = {"doctype": dt, "name": doc.name}
            if dt == "Custom Field":
                info["dt"] = getattr(doc, "dt", "")
                info["fieldname"] = getattr(doc, "fieldname", "")
            elif dt == "Property Setter":
                info["doc_type"] = getattr(doc, "doc_type", "")
                info["property"] = getattr(doc, "property", "")

            frappe.delete_doc(dt, doc.name, ignore_permissions=False)
            frappe.db.commit()

            return {
                "success": True,
                "message": "{} '{}' has been deleted".format(dt, doc.name),
                "deleted": info,
            }

        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": str(e)}

    def _check_dependencies(self, doc):
        """Check if anything depends on this customization."""
        try:
            dt = doc.doctype
            details = []

            if dt == "Custom Field":
                fieldname = getattr(doc, "fieldname", "")
                target_dt = getattr(doc, "dt", "")

                if fieldname and target_dt:
                    # Check if any fetch_from references this field
                    try:
                        refs = frappe.get_all(
                            "Custom Field",
                            filters={"fetch_from": ("like", "%{}.{}%".format(target_dt, fieldname))},
                            fields=["name", "dt", "fieldname"],
                            limit=5,
                        )
                        for ref in refs:
                            details.append("Custom Field '{}.{}' has fetch_from referencing this field".format(ref.get("dt", ""), ref.get("fieldname", "")))
                    except Exception:
                        pass

                    # Check if Server Scripts reference this field
                    try:
                        scripts = frappe.get_all(
                            "Server Script",
                            filters={"script": ("like", "%{}%".format(fieldname)), "disabled": 0},
                            fields=["name"],
                            limit=5,
                        )
                        for s in scripts:
                            details.append("Server Script '{}' references this field".format(s.get("name", "")))
                    except Exception:
                        pass

            elif dt in ("Client Script", "Server Script"):
                # Scripts generally don't have dependents
                pass

            return {"has_dependencies": len(details) > 0, "details": details}

        except Exception:
            return {"has_dependencies": False, "details": []}
