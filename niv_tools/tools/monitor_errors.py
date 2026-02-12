# Monitor Errors Tool - Check Error Log for recent errors, detect patterns, suggest fixes

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class MonitorErrors(BaseTool):
    """Check Error Log for recent errors, detect patterns, and suggest fixes."""

    def __init__(self):
        super().__init__()
        self.name = "monitor_errors"
        self.description = (
            "Check the Error Log for recent errors, detect repeating patterns, "
            "and suggest fixes. Use after making changes to verify nothing broke, "
            "or to diagnose issues reported by users."
        )
        self.category = "Monitoring"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Look back this many minutes (default: 30)",
                    "default": 30,
                },
                "doctype_filter": {
                    "type": "string",
                    "description": "Optional: filter errors related to a specific DocType",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max errors to return (default: 20)",
                    "default": 20,
                },
            },
            "required": [],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            minutes = arguments.get("minutes", 30)
            doctype_filter = arguments.get("doctype_filter", "")
            limit = arguments.get("limit", 20)

            try:
                frappe.has_permission("Error Log", "read", throw=True)
            except Exception:
                return {"success": False, "error": "No read permission for Error Log"}

            from frappe.utils import now_datetime, add_to_date

            cutoff = add_to_date(now_datetime(), minutes=-minutes)

            filters = {"creation": (">=", str(cutoff))}
            if doctype_filter:
                filters["method"] = ("like", "%{}%".format(doctype_filter))

            errors = frappe.get_all(
                "Error Log",
                filters=filters,
                fields=["name", "method", "error", "creation"],
                order_by="creation desc",
                limit_page_length=limit,
            )

            if not errors:
                return {
                    "success": True,
                    "message": "No errors found in the last {} minutes".format(minutes),
                    "total": 0,
                    "errors": [],
                    "patterns": [],
                }

            # Group by error type (first line of traceback)
            groups = {}
            error_summaries = []
            for err in errors:
                error_text = err.get("error", "") or ""
                first_line = error_text.strip().split("\n")[-1] if error_text.strip() else "Unknown"
                # Truncate for readability
                first_line = first_line[:200]

                if first_line not in groups:
                    groups[first_line] = {"count": 0, "methods": set(), "first_seen": str(err.get("creation", "")), "last_seen": str(err.get("creation", ""))}
                groups[first_line]["count"] += 1
                method = err.get("method", "") or ""
                if method:
                    groups[first_line]["methods"].add(method)

                error_summaries.append({
                    "name": err.get("name", ""),
                    "method": err.get("method", ""),
                    "error_line": first_line,
                    "creation": str(err.get("creation", "")),
                })

            # Build patterns
            patterns = []
            for error_line, info in groups.items():
                pattern = {
                    "error": error_line,
                    "count": info["count"],
                    "methods": list(info["methods"])[:5],
                    "suggestion": self._suggest_fix(error_line),
                }
                if info["count"] >= 3:
                    pattern["severity"] = "high"
                    pattern["note"] = "Repeating error ({} times) - likely a systematic issue".format(info["count"])
                else:
                    pattern["severity"] = "low"
                patterns.append(pattern)

            # Sort patterns by count desc
            patterns.sort(key=lambda x: x["count"], reverse=True)

            return {
                "success": True,
                "total": len(errors),
                "time_range_minutes": minutes,
                "errors": error_summaries[:10],
                "patterns": patterns[:10],
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _suggest_fix(self, error_line):
        """Suggest fixes for common error patterns."""
        line_lower = error_line.lower()

        if "does not exist" in line_lower:
            return "A referenced document or DocType doesn't exist. Check if it was deleted or renamed."
        elif "permission" in line_lower or "not permitted" in line_lower:
            return "Permission issue. Check Role Permissions for the relevant DocType."
        elif "mandatory" in line_lower or "required" in line_lower:
            return "A required field is missing. Check the form or script that creates this document."
        elif "duplicate" in line_lower or "unique" in line_lower:
            return "Duplicate entry. A record with this value already exists. Check naming series or unique fields."
        elif "syntaxerror" in line_lower:
            return "Syntax error in a script. Check Client Scripts or Server Scripts for typos."
        elif "importerror" in line_lower or "modulenotfounderror" in line_lower:
            return "Missing module/import. A required Python package may not be installed."
        elif "typeerror" in line_lower:
            return "Type mismatch. A function received wrong argument types. Check API calls and field types."
        elif "attributeerror" in line_lower:
            return "Accessing a non-existent attribute. Check if the field/method exists on the DocType."
        elif "timeout" in line_lower or "timed out" in line_lower:
            return "Operation timed out. Could be a slow query, external API, or heavy computation."
        elif "linkvalidation" in line_lower:
            return "Link validation failed. The linked document doesn't exist or is not permitted."
        elif "valueerror" in line_lower:
            return "Invalid value. Check data formats (dates, numbers) and select field options."
        else:
            return "Review the full traceback in Error Log for details."
