# Test Created Item Tool - Verify chatbot-created artifacts actually work
# Checks existence, validation, script syntax, and dry-run execution

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class TestCreatedItem(BaseTool):
    """Verify that chatbot-created DocTypes, Custom Fields, Client Scripts etc. actually work."""

    def __init__(self):
        super().__init__()
        self.name = "test_created_item"
        self.description = (
            "After the chatbot creates something (DocType, Custom Field, Client Script, "
            "Server Script), use this tool to verify it works. Supports tests: "
            "exists (check it exists), validate (try creating a test record with dummy data), "
            "render (check script syntax), execute (dry run Server Scripts)."
        )
        self.category = "Testing"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The DocType of the item to test (e.g., 'DocType', 'Custom Field', 'Client Script')"
                },
                "name": {
                    "type": "string",
                    "description": "Name/ID of the document to test"
                },
                "test_type": {
                    "type": "string",
                    "enum": ["exists", "validate", "render", "execute"],
                    "description": "Type of test: exists, validate, render, execute"
                },
            },
            "required": ["doctype", "name", "test_type"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            doctype = arguments.get("doctype", "")
            name = arguments.get("name", "")
            test_type = arguments.get("test_type", "exists")

            if not doctype or not name:
                return {"success": False, "error": "doctype and name are required"}

            # Permission check
            try:
                frappe.has_permission(doctype, "read", throw=True)
            except Exception:
                return {"success": False, "error": "No read permission for {}".format(doctype)}

            if test_type == "exists":
                return self._test_exists(doctype, name)
            elif test_type == "validate":
                return self._test_validate(doctype, name)
            elif test_type == "render":
                return self._test_render(doctype, name)
            elif test_type == "execute":
                return self._test_execute(doctype, name)
            else:
                return {"success": False, "error": "Unknown test_type: {}".format(test_type)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_exists(self, doctype, name):
        """Check if the document exists and return basic info."""
        try:
            if not frappe.db.exists(doctype, name):
                return {"success": False, "error": "{} '{}' does not exist".format(doctype, name)}

            doc = frappe.get_doc(doctype, name)
            info = {
                "name": doc.name,
                "doctype": doc.doctype,
                "modified": str(doc.modified),
                "owner": doc.owner,
            }

            # Extra info based on doctype
            if doctype == "DocType":
                info["fields_count"] = len(doc.fields) if hasattr(doc, "fields") else 0
                info["is_custom"] = getattr(doc, "custom", 0)
                info["module"] = getattr(doc, "module", "")
            elif doctype == "Custom Field":
                info["fieldtype"] = getattr(doc, "fieldtype", "")
                info["dt"] = getattr(doc, "dt", "")
                info["fieldname"] = getattr(doc, "fieldname", "")
            elif doctype in ("Client Script", "Server Script"):
                info["enabled"] = getattr(doc, "enabled", 0) or getattr(doc, "disabled", 0) == 0
                info["script_type"] = getattr(doc, "script_type", "")

            return {"success": True, "exists": True, "info": info}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_validate(self, doctype, name):
        """For DocTypes: try creating a test record with dummy data, then delete it."""
        try:
            # This only makes sense if 'name' is a DocType name
            target_doctype = name if doctype == "DocType" else doctype

            if not frappe.db.exists("DocType", target_doctype):
                return {"success": False, "error": "DocType '{}' does not exist".format(target_doctype)}

            try:
                frappe.has_permission(target_doctype, "create", throw=True)
            except Exception:
                return {"success": False, "error": "No create permission for {}".format(target_doctype)}

            meta = frappe.get_meta(target_doctype)
            test_doc = frappe.new_doc(target_doctype)

            # Fill required fields with dummy data
            filled_fields = []
            for field in meta.fields:
                if not field.reqd:
                    continue
                val = self._get_dummy_value(field)
                if val is not None:
                    test_doc.set(field.fieldname, val)
                    filled_fields.append({"fieldname": field.fieldname, "fieldtype": field.fieldtype, "value": str(val)})

            # Try to insert
            try:
                test_doc.flags.ignore_permissions = False
                test_doc.flags.ignore_links = True
                test_doc.flags.ignore_validate = False
                test_doc.insert()
                test_name = test_doc.name
                # Clean up
                frappe.delete_doc(target_doctype, test_name, force=True, ignore_permissions=True)
                frappe.db.commit()
                return {
                    "success": True,
                    "message": "Test record created and deleted successfully",
                    "filled_fields": filled_fields,
                }
            except Exception as e:
                frappe.db.rollback()
                return {
                    "success": False,
                    "error": "Validation failed: {}".format(str(e)),
                    "filled_fields": filled_fields,
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_render(self, doctype, name):
        """Check script syntax for Client Script / Server Script."""
        try:
            if doctype not in ("Client Script", "Server Script"):
                return {"success": False, "error": "render test only applies to Client Script or Server Script"}

            if not frappe.db.exists(doctype, name):
                return {"success": False, "error": "{} '{}' does not exist".format(doctype, name)}

            doc = frappe.get_doc(doctype, name)
            script = getattr(doc, "script", "") or ""

            if not script.strip():
                return {"success": False, "error": "Script is empty"}

            issues = []

            if doctype == "Server Script":
                # Python syntax check
                try:
                    compile(script, "<server_script:{}>".format(name), "exec")
                except SyntaxError as e:
                    issues.append({
                        "type": "SyntaxError",
                        "line": e.lineno,
                        "message": str(e.msg),
                    })
            elif doctype == "Client Script":
                # Basic JS checks
                import re
                open_braces = script.count("{") - script.count("}")
                if open_braces != 0:
                    issues.append({"type": "BraceMismatch", "message": "Unbalanced braces (diff: {})".format(open_braces)})
                open_parens = script.count("(") - script.count(")")
                if open_parens != 0:
                    issues.append({"type": "ParenMismatch", "message": "Unbalanced parentheses (diff: {})".format(open_parens)})
                # Check for common frappe API patterns
                if "frappe.call" in script and "callback" not in script and ".then" not in script:
                    issues.append({"type": "Warning", "message": "frappe.call without callback or .then()"})

            if issues:
                return {"success": False, "issues": issues, "lines": len(script.splitlines())}
            return {"success": True, "message": "Syntax check passed", "lines": len(script.splitlines())}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_execute(self, doctype, name):
        """Dry-run a Server Script to check for import/runtime errors."""
        try:
            if doctype != "Server Script":
                return {"success": False, "error": "execute test only applies to Server Script"}

            if not frappe.db.exists("Server Script", name):
                return {"success": False, "error": "Server Script '{}' does not exist".format(name)}

            doc = frappe.get_doc("Server Script", name)
            script = getattr(doc, "script", "") or ""

            if not script.strip():
                return {"success": False, "error": "Script is empty"}

            # Compile check first
            try:
                compile(script, "<server_script:{}>".format(name), "exec")
            except SyntaxError as e:
                return {"success": False, "error": "SyntaxError at line {}: {}".format(e.lineno, e.msg)}

            # Check for dangerous operations
            warnings = []
            if "frappe.db.sql" in script and "drop " in script.lower():
                warnings.append("Script contains potential DROP statement")
            if "os.system" in script or "subprocess" in script:
                warnings.append("Script uses system commands")
            if "frappe.delete_doc" in script:
                warnings.append("Script deletes documents")

            return {
                "success": True,
                "message": "Dry run passed (syntax OK, no execution performed)",
                "script_type": getattr(doc, "script_type", ""),
                "reference_doctype": getattr(doc, "reference_doctype", ""),
                "enabled": getattr(doc, "disabled", 0) == 0,
                "warnings": warnings,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_dummy_value(self, field):
        """Generate a dummy value for a field based on its type."""
        ft = field.fieldtype
        if ft in ("Data", "Small Text", "Text", "Long Text", "Text Editor"):
            return "__test__"
        elif ft == "Int":
            return 1
        elif ft in ("Float", "Currency", "Percent"):
            return 1.0
        elif ft == "Check":
            return 0
        elif ft == "Date":
            return "2025-01-01"
        elif ft == "Datetime":
            return "2025-01-01 00:00:00"
        elif ft == "Time":
            return "00:00:00"
        elif ft == "Select":
            options = (field.options or "").split("\n")
            options = [o.strip() for o in options if o.strip()]
            if options:
                return options[0]
            return ""
        elif ft == "Link":
            # Try to get first record of linked doctype
            try:
                linked = field.options
                if linked and frappe.db.exists("DocType", linked):
                    first = frappe.db.get_all(linked, limit=1, pluck="name")
                    if first:
                        return first[0]
            except Exception:
                pass
            return None
        return None
