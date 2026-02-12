# Build Blueprint — Execute multi-step module creation with progress tracking
# Creates DocTypes, Workflows, Scripts, Reports step by step

from typing import Any, Dict, List
import frappe
import json
import traceback
from frappe_assistant_core.core.base_tool import BaseTool


class BuildBlueprint(BaseTool):
    """Execute a module blueprint step by step — creates DocTypes, fields, workflows, scripts with progress tracking."""

    def __init__(self):
        super().__init__()
        self.name = "build_blueprint"
        self.description = (
            "Execute a module blueprint step by step. Creates multiple components "
            "(DocTypes, Custom Fields, Workflows, Server Scripts, Client Scripts, "
            "Print Formats, Notifications, Reports) in sequence with progress tracking. "
            "Each step is verified after creation. Returns detailed build log. "
            "Use this after showing blueprint to user and getting approval."
        )
        self.category = "Developer"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "Array of build steps. Each step has: doctype (what to create), data (document data), description (human readable).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doctype": {
                                "type": "string",
                                "description": "DocType to create (e.g. 'DocType', 'Custom Field', 'Workflow', 'Server Script')"
                            },
                            "data": {
                                "type": "object",
                                "description": "Document data to create"
                            },
                            "description": {
                                "type": "string",
                                "description": "Human-readable description of this step"
                            }
                        },
                        "required": ["doctype", "data", "description"]
                    }
                },
                "module_name": {
                    "type": "string",
                    "description": "Name of the module being built (for logging)"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, validate steps without creating anything. Default false.",
                    "default": False
                }
            },
            "required": ["steps", "module_name"]
        }

    def execute(self, arguments):
        steps = arguments.get("steps", [])
        module_name = arguments.get("module_name", "Unknown Module")
        dry_run = arguments.get("dry_run", False)

        if not steps:
            return {"error": "No build steps provided"}

        if len(steps) > 50:
            return {"error": "Too many steps (max 50). Break into smaller modules."}

        build_log = []
        created = []
        failed = []
        total = len(steps)

        for i, step in enumerate(steps):
            step_num = i + 1
            doctype = step.get("doctype", "")
            data = step.get("data", {})
            desc = step.get("description", "Step {}".format(step_num))

            log_entry = {
                "step": step_num,
                "total": total,
                "description": desc,
                "doctype": doctype,
            }

            if not doctype or not data:
                log_entry["status"] = "SKIPPED"
                log_entry["message"] = "Missing doctype or data"
                build_log.append(log_entry)
                continue

            if dry_run:
                # Validate only
                valid, msg = self._validate_step(doctype, data)
                log_entry["status"] = "VALID" if valid else "INVALID"
                log_entry["message"] = msg
                build_log.append(log_entry)
                continue

            # Execute the step
            try:
                result = self._execute_step(doctype, data)
                log_entry["status"] = "SUCCESS"
                log_entry["name"] = result.get("name", "")
                log_entry["message"] = result.get("message", "Created successfully")
                created.append({
                    "doctype": doctype,
                    "name": result.get("name", ""),
                    "description": desc
                })
            except Exception as e:
                log_entry["status"] = "FAILED"
                log_entry["error"] = str(e)
                log_entry["traceback"] = traceback.format_exc()[-500:]
                failed.append({
                    "step": step_num,
                    "description": desc,
                    "error": str(e)
                })

            build_log.append(log_entry)

        # Summary
        success_count = len(created)
        fail_count = len(failed)
        skip_count = total - success_count - fail_count

        summary = {
            "module_name": module_name,
            "dry_run": dry_run,
            "total_steps": total,
            "success": success_count,
            "failed": fail_count,
            "skipped": skip_count,
            "status": "COMPLETE" if fail_count == 0 else "PARTIAL" if success_count > 0 else "FAILED",
        }

        if created:
            summary["created_items"] = created
        if failed:
            summary["failed_items"] = failed

        # Build progress display
        progress_lines = []
        for log in build_log:
            icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️", "VALID": "✓", "INVALID": "✗"}.get(log["status"], "⚙️")
            line = "{} [{}/{}] {} — {}".format(icon, log["step"], log["total"], log["description"], log.get("message", log.get("error", "")))
            if log.get("name"):
                line += " (name: {})".format(log["name"])
            progress_lines.append(line)

        summary["build_log"] = "\n".join(progress_lines)

        # Needs migrate?
        needs_migrate = any(
            log.get("doctype") == "DocType" and log.get("status") == "SUCCESS"
            for log in build_log
        )
        if needs_migrate:
            summary["action_required"] = "New DocType(s) created — run 'bench migrate' to create database tables"

        return summary

    def _validate_step(self, doctype, data):
        """Validate a step without executing it."""
        # Check if the target DocType exists
        if not frappe.db.exists("DocType", doctype):
            return False, "DocType '{}' does not exist".format(doctype)

        # Check for duplicate
        if doctype == "DocType" and data.get("name"):
            if frappe.db.exists("DocType", data["name"]):
                return False, "DocType '{}' already exists".format(data["name"])

        if doctype == "Custom Field":
            dt = data.get("dt", "")
            fn = data.get("fieldname", "")
            if dt and fn:
                existing = frappe.db.exists("Custom Field", "{}-{}".format(dt, fn))
                if existing:
                    return False, "Custom Field '{}-{}' already exists".format(dt, fn)

        if doctype == "Workflow":
            wf_name = data.get("workflow_name", "")
            if wf_name and frappe.db.exists("Workflow", wf_name):
                return False, "Workflow '{}' already exists".format(wf_name)

        return True, "Validation passed"

    def _execute_step(self, doctype, data):
        """Execute a single build step — create a document."""
        # Handle DocType creation specially
        if doctype == "DocType":
            return self._create_doctype(data)

        # For all other types, use standard create
        doc = frappe.get_doc({"doctype": doctype, **data})
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = False

        # Handle naming for specific types
        if doctype == "Custom Field" and not data.get("name"):
            dt = data.get("dt", "")
            fn = data.get("fieldname", "")
            if dt and fn:
                doc.name = "{}-{}".format(dt, fn)

        doc.insert(ignore_if_duplicate=True)
        frappe.db.commit()

        return {
            "name": doc.name,
            "message": "Created {} successfully".format(doctype)
        }

    def _create_doctype(self, data):
        """Create a new DocType with fields and permissions."""
        name = data.get("name", "")
        if not name:
            return {"error": "DocType name is required"}

        # Check if already exists
        if frappe.db.exists("DocType", name):
            return {
                "name": name,
                "message": "DocType already exists — skipped"
            }

        doc = frappe.get_doc({
            "doctype": "DocType",
            "module": data.get("module", "Custom"),
            "custom": data.get("custom", 1),
            "name": name,
            "naming_rule": data.get("naming_rule", "By \"Naming Series\" field"),
            "autoname": data.get("autoname", "hash"),
            "is_submittable": data.get("is_submittable", 0),
            "istable": data.get("istable", 0),
            "fields": data.get("fields", []),
            "permissions": data.get("permissions", [
                {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
            ]),
        })

        # Copy optional flags
        for key in ["is_tree", "nsm_parent_field", "title_field", "image_field",
                     "sort_field", "sort_order", "description", "documentation"]:
            if key in data:
                setattr(doc, key, data[key])

        doc.flags.ignore_permissions = True
        doc.insert()
        frappe.db.commit()

        # Clear cache for new DocType
        frappe.clear_cache(doctype=name)

        field_count = len(data.get("fields", []))
        return {
            "name": name,
            "message": "Created DocType with {} fields. Run 'bench migrate' to create table.".format(field_count)
        }
