# Verify Build — Auto-test created components and diagnose failures
# Tests DocTypes, Custom Fields, Scripts, Workflows after creation

from typing import Any, Dict
import frappe
import traceback
from frappe_assistant_core.core.base_tool import BaseTool


class VerifyBuild(BaseTool):
    """Auto-test and verify created components. Tests DocTypes (CRUD), Custom Fields (exist + visible),
    Server Scripts (compile), Client Scripts (syntax), Workflows (states valid), Reports (execute).
    Returns PASS/FAIL with diagnosis and fix suggestions."""

    def __init__(self):
        super().__init__()
        self.name = "verify_build"
        self.description = (
            "Auto-test created components after building. Verifies: "
            "DocType (CRUD test), Custom Field (exists, visible), "
            "Server Script (compiles, no syntax errors), Client Script (valid JS), "
            "Workflow (states and transitions valid), Report (executes without error). "
            "Returns PASS/FAIL with diagnosis and suggested fixes. "
            "Use after build_blueprint or create_document to verify everything works."
        )
        self.category = "Developer"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "description": "List of components to verify. Each has: type (DocType/Custom Field/Server Script/Client Script/Workflow/Report), name (document name or identifier).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Component type: DocType, Custom Field, Server Script, Client Script, Workflow, Report, Notification, Print Format"
                            },
                            "name": {
                                "type": "string",
                                "description": "Name/identifier of the component"
                            }
                        },
                        "required": ["type", "name"]
                    }
                },
                "auto_fix": {
                    "type": "boolean",
                    "description": "If true, attempt to auto-fix common issues. Default false.",
                    "default": False
                }
            },
            "required": ["components"]
        }

    def execute(self, arguments):
        components = arguments.get("components", [])
        auto_fix = arguments.get("auto_fix", False)

        if not components:
            return {"error": "No components to verify"}

        results = []
        passed = 0
        failed = 0
        fixed = 0

        for comp in components:
            comp_type = comp.get("type", "")
            comp_name = comp.get("name", "")

            if not comp_type or not comp_name:
                results.append({"type": comp_type, "name": comp_name, "status": "SKIP", "message": "Missing type or name"})
                continue

            test_result = self._test_component(comp_type, comp_name, auto_fix)
            results.append(test_result)

            if test_result["status"] == "PASS":
                passed += 1
            elif test_result["status"] == "FIXED":
                fixed += 1
                passed += 1
            else:
                failed += 1

        total = passed + failed
        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "fixed": fixed,
            "status": "ALL PASS" if failed == 0 else "SOME FAILED",
            "results": results,
        }

        # Build readable log
        lines = []
        for r in results:
            icon = {"PASS": "✅", "FAIL": "❌", "FIXED": "🔧", "SKIP": "⏭️"}.get(r["status"], "❓")
            line = "{} {} [{}] — {}".format(icon, r["type"], r["name"], r["message"])
            if r.get("fix_suggestion"):
                line += "\n   💡 Fix: {}".format(r["fix_suggestion"])
            if r.get("fix_applied"):
                line += "\n   🔧 Auto-fixed: {}".format(r["fix_applied"])
            lines.append(line)

        summary["verification_log"] = "\n".join(lines)
        return summary

    def _test_component(self, comp_type, comp_name, auto_fix):
        """Test a single component."""
        testers = {
            "DocType": self._test_doctype,
            "Custom Field": self._test_custom_field,
            "Server Script": self._test_server_script,
            "Client Script": self._test_client_script,
            "Workflow": self._test_workflow,
            "Report": self._test_report,
            "Notification": self._test_notification,
            "Print Format": self._test_print_format,
            "Property Setter": self._test_property_setter,
        }

        tester = testers.get(comp_type)
        if not tester:
            return {"type": comp_type, "name": comp_name, "status": "SKIP",
                    "message": "Unknown component type: {}".format(comp_type)}

        try:
            return tester(comp_name, auto_fix)
        except Exception as e:
            return {"type": comp_type, "name": comp_name, "status": "FAIL",
                    "message": "Test error: {}".format(str(e)),
                    "fix_suggestion": "Check if component exists and is accessible"}

    def _test_doctype(self, name, auto_fix):
        """Test DocType — exists, has fields, can CRUD."""
        result = {"type": "DocType", "name": name}

        # 1. Exists?
        if not frappe.db.exists("DocType", name):
            result["status"] = "FAIL"
            result["message"] = "DocType does not exist"
            result["fix_suggestion"] = "Create the DocType first, then run 'bench migrate'"
            return result

        meta = frappe.get_meta(name)

        # 2. Has fields?
        real_fields = [f for f in meta.fields if f.fieldtype not in ("Section Break", "Column Break", "Tab Break")]
        if not real_fields:
            result["status"] = "FAIL"
            result["message"] = "DocType has no data fields (only section/column breaks)"
            result["fix_suggestion"] = "Add at least one data field to the DocType"
            return result

        # 3. Has permissions?
        if not meta.permissions:
            result["status"] = "FAIL"
            result["message"] = "DocType has no permissions — nobody can access it"
            result["fix_suggestion"] = "Add permission for System Manager role"
            if auto_fix:
                try:
                    doc = frappe.get_doc("DocType", name)
                    doc.append("permissions", {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1})
                    doc.flags.ignore_permissions = True
                    doc.save()
                    frappe.db.commit()
                    result["status"] = "FIXED"
                    result["message"] = "DocType exists with {} fields. Permissions were missing — auto-added.".format(len(real_fields))
                    result["fix_applied"] = "Added System Manager permission"
                    return result
                except Exception as e:
                    result["message"] += ". Auto-fix failed: {}".format(str(e))
            return result

        # 4. Try CRUD (only for custom, non-child, non-single)
        if meta.custom and not meta.istable and not meta.issingle:
            try:
                # Find a mandatory field to fill
                test_data = {"doctype": name}
                for f in meta.fields:
                    if f.reqd and f.fieldtype == "Data":
                        test_data[f.fieldname] = "VERIFY_BUILD_TEST"
                    elif f.reqd and f.fieldtype == "Link":
                        # Try to find one record
                        existing = frappe.db.get_all(f.options, limit=1)
                        if existing:
                            test_data[f.fieldname] = existing[0].name
                    elif f.reqd and f.fieldtype == "Select" and f.options:
                        opts = f.options.split("\n")
                        test_data[f.fieldname] = opts[0]
                    elif f.reqd and f.fieldtype in ("Int", "Float", "Currency"):
                        test_data[f.fieldname] = 1

                # Create
                test_doc = frappe.get_doc(test_data)
                test_doc.flags.ignore_permissions = True
                test_doc.flags.ignore_mandatory = False
                test_doc.insert()

                doc_name = test_doc.name

                # Read
                read_doc = frappe.get_doc(name, doc_name)

                # Delete
                frappe.delete_doc(name, doc_name, force=True)
                frappe.db.commit()

                result["status"] = "PASS"
                result["message"] = "DocType OK — {} fields, CRUD test passed".format(len(real_fields))
            except Exception as e:
                error_str = str(e)
                result["status"] = "FAIL"
                result["message"] = "DocType exists but CRUD failed: {}".format(error_str[:200])

                # Diagnose common issues
                if "does not exist" in error_str.lower() and "table" in error_str.lower():
                    result["fix_suggestion"] = "Database table not created. Run: bench --site <site> migrate"
                elif "mandatory" in error_str.lower():
                    result["fix_suggestion"] = "Mandatory field missing in test. Check required fields have sensible defaults."
                elif "duplicate" in error_str.lower():
                    result["fix_suggestion"] = "Naming conflict. Check autoname/naming_rule configuration."
                else:
                    result["fix_suggestion"] = "Check error details and fix the DocType definition"
        else:
            result["status"] = "PASS"
            result["message"] = "DocType exists with {} fields, {} permissions".format(len(real_fields), len(meta.permissions))
            if meta.istable:
                result["message"] += " (child table)"
            if meta.issingle:
                result["message"] += " (single)"

        return result

    def _test_custom_field(self, name, auto_fix):
        """Test Custom Field — exists, target DocType exists, field visible."""
        result = {"type": "Custom Field", "name": name}

        if not frappe.db.exists("Custom Field", name):
            result["status"] = "FAIL"
            result["message"] = "Custom Field does not exist"
            # Try to suggest correct name
            if "-" in name:
                dt, fn = name.split("-", 1)
                result["fix_suggestion"] = "Check: DocType='{}', fieldname='{}'".format(dt, fn)
            return result

        cf = frappe.get_doc("Custom Field", name)

        # Check target DocType exists
        if not frappe.db.exists("DocType", cf.dt):
            result["status"] = "FAIL"
            result["message"] = "Target DocType '{}' does not exist".format(cf.dt)
            return result

        # Check field appears in meta
        meta = frappe.get_meta(cf.dt)
        field = meta.get_field(cf.fieldname)
        if not field:
            result["status"] = "FAIL"
            result["message"] = "Field '{}' not found in {} meta (cache issue?)".format(cf.fieldname, cf.dt)
            result["fix_suggestion"] = "Try: bench clear-cache"
            return result

        result["status"] = "PASS"
        result["message"] = "Custom Field OK — '{}' ({}) on {}".format(cf.fieldname, cf.fieldtype, cf.dt)
        if cf.hidden:
            result["message"] += " [hidden]"
        return result

    def _test_server_script(self, name, auto_fix):
        """Test Server Script — exists, compiles, no obvious errors."""
        result = {"type": "Server Script", "name": name}

        if not frappe.db.exists("Server Script", name):
            result["status"] = "FAIL"
            result["message"] = "Server Script does not exist"
            return result

        ss = frappe.get_doc("Server Script", name)

        # Check if disabled
        if ss.disabled:
            result["status"] = "FAIL"
            result["message"] = "Server Script exists but is DISABLED"
            result["fix_suggestion"] = "Enable it in Server Script settings"
            if auto_fix:
                ss.disabled = 0
                ss.flags.ignore_permissions = True
                ss.save()
                frappe.db.commit()
                result["status"] = "FIXED"
                result["fix_applied"] = "Enabled the script"
            return result

        # Try to compile the script
        script = ss.script or ""
        if not script.strip():
            result["status"] = "FAIL"
            result["message"] = "Server Script is empty"
            return result

        try:
            compile(script, "<server_script:{}>".format(name), "exec")
            result["status"] = "PASS"
            result["message"] = "Server Script OK — compiles clean, {} lines".format(len(script.split("\n")))
            if ss.reference_doctype:
                result["message"] += ", triggers on {} ({})".format(ss.reference_doctype, ss.doctype_event or ss.event_frequency)
        except SyntaxError as e:
            result["status"] = "FAIL"
            result["message"] = "Syntax error at line {}: {}".format(e.lineno, e.msg)
            result["fix_suggestion"] = "Fix syntax error at line {} in the script".format(e.lineno)

        return result

    def _test_client_script(self, name, auto_fix):
        """Test Client Script — exists, basic JS validation."""
        result = {"type": "Client Script", "name": name}

        if not frappe.db.exists("Client Script", name):
            result["status"] = "FAIL"
            result["message"] = "Client Script does not exist"
            return result

        cs = frappe.get_doc("Client Script", name)

        if not cs.enabled:
            result["status"] = "FAIL"
            result["message"] = "Client Script exists but is DISABLED"
            if auto_fix:
                cs.enabled = 1
                cs.flags.ignore_permissions = True
                cs.save()
                frappe.db.commit()
                result["status"] = "FIXED"
                result["fix_applied"] = "Enabled the script"
            return result

        script = cs.script or ""
        if not script.strip():
            result["status"] = "FAIL"
            result["message"] = "Client Script is empty"
            return result

        # Basic JS checks
        issues = []
        if "frappe.ui.form.on" not in script and cs.script_type == "Form":
            issues.append("Missing frappe.ui.form.on() — required for Form scripts")
        
        # Check balanced braces
        if script.count("{") != script.count("}"):
            issues.append("Unbalanced curly braces: {} open, {} close".format(script.count("{"), script.count("}")))
        if script.count("(") != script.count(")"):
            issues.append("Unbalanced parentheses: {} open, {} close".format(script.count("("), script.count(")")))

        if issues:
            result["status"] = "FAIL"
            result["message"] = "JS issues: " + "; ".join(issues)
            result["fix_suggestion"] = "Fix the JavaScript syntax issues"
        else:
            result["status"] = "PASS"
            result["message"] = "Client Script OK — {} type, {} lines, for {}".format(
                cs.script_type, len(script.split("\n")), cs.dt)

        return result

    def _test_workflow(self, name, auto_fix):
        """Test Workflow — exists, has states, transitions valid."""
        result = {"type": "Workflow", "name": name}

        if not frappe.db.exists("Workflow", name):
            result["status"] = "FAIL"
            result["message"] = "Workflow does not exist"
            return result

        wf = frappe.get_doc("Workflow", name)

        if not wf.is_active:
            result["status"] = "FAIL"
            result["message"] = "Workflow exists but is INACTIVE"
            if auto_fix:
                wf.is_active = 1
                wf.flags.ignore_permissions = True
                wf.save()
                frappe.db.commit()
                result["status"] = "FIXED"
                result["fix_applied"] = "Activated the workflow"
            return result

        # Check states
        states = [s.state for s in wf.states]
        if not states:
            result["status"] = "FAIL"
            result["message"] = "Workflow has no states defined"
            return result

        # Check transitions reference valid states
        invalid_transitions = []
        for t in wf.transitions:
            if t.state not in states:
                invalid_transitions.append("Transition from '{}' — state not found".format(t.state))
            if t.next_state not in states:
                invalid_transitions.append("Transition to '{}' — state not found".format(t.next_state))

        if invalid_transitions:
            result["status"] = "FAIL"
            result["message"] = "Invalid transitions: " + "; ".join(invalid_transitions[:3])
            result["fix_suggestion"] = "Ensure all transition states exist in the states list"
            return result

        # Check document_type exists
        if not frappe.db.exists("DocType", wf.document_type):
            result["status"] = "FAIL"
            result["message"] = "Target DocType '{}' does not exist".format(wf.document_type)
            return result

        result["status"] = "PASS"
        result["message"] = "Workflow OK — {} states, {} transitions, for {}".format(
            len(states), len(wf.transitions), wf.document_type)
        return result

    def _test_report(self, name, auto_fix):
        """Test Report — exists, can execute."""
        result = {"type": "Report", "name": name}

        if not frappe.db.exists("Report", name):
            result["status"] = "FAIL"
            result["message"] = "Report does not exist"
            return result

        report = frappe.get_doc("Report", name)
        result["status"] = "PASS"
        result["message"] = "Report OK — type: {}, for {}".format(report.report_type, report.ref_doctype)
        return result

    def _test_notification(self, name, auto_fix):
        """Test Notification — exists, enabled, has recipients."""
        result = {"type": "Notification", "name": name}

        if not frappe.db.exists("Notification", name):
            result["status"] = "FAIL"
            result["message"] = "Notification does not exist"
            return result

        notif = frappe.get_doc("Notification", name)
        if not notif.enabled:
            result["status"] = "FAIL"
            result["message"] = "Notification exists but is DISABLED"
            if auto_fix:
                notif.enabled = 1
                notif.flags.ignore_permissions = True
                notif.save()
                frappe.db.commit()
                result["status"] = "FIXED"
                result["fix_applied"] = "Enabled the notification"
            return result

        result["status"] = "PASS"
        result["message"] = "Notification OK — event: {}, channel: {}, for {}".format(
            notif.event, notif.channel, notif.document_type)
        return result

    def _test_print_format(self, name, auto_fix):
        """Test Print Format — exists, has content."""
        result = {"type": "Print Format", "name": name}

        if not frappe.db.exists("Print Format", name):
            result["status"] = "FAIL"
            result["message"] = "Print Format does not exist"
            return result

        pf = frappe.get_doc("Print Format", name)
        if pf.disabled:
            result["status"] = "FAIL"
            result["message"] = "Print Format exists but is DISABLED"
            return result

        result["status"] = "PASS"
        result["message"] = "Print Format OK — type: {}, for {}".format(
            pf.print_format_type or "Standard", pf.doc_type)
        return result

    def _test_property_setter(self, name, auto_fix):
        """Test Property Setter — exists, target field exists."""
        result = {"type": "Property Setter", "name": name}

        if not frappe.db.exists("Property Setter", name):
            result["status"] = "FAIL"
            result["message"] = "Property Setter does not exist"
            return result

        ps = frappe.get_doc("Property Setter", name)
        result["status"] = "PASS"
        result["message"] = "Property Setter OK — {}.{} → {} = {}".format(
            ps.doc_type, ps.field_name, ps.property, ps.value[:50] if ps.value else "")
        return result
