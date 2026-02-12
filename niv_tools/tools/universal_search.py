# Universal Search Tool - searches ALL fields across ALL accessible DocTypes
# Registered via FAC hooks, served via MCP to Niv AI

from typing import Any, Dict
import frappe
from frappe_assistant_core.core.base_tool import BaseTool


class UniversalSearch(BaseTool):
    """Universal search across all DocTypes and all fields including numbers/amounts"""

    # DocTypes to prioritize (searched first)
    PRIORITY_DOCTYPES = [
        "Sales Order", "Sales Invoice", "Purchase Order", "Purchase Invoice",
        "Quotation", "Customer", "Supplier", "Item", "Employee", "Lead",
        "Opportunity", "Delivery Note", "Purchase Receipt", "Journal Entry",
        "Payment Entry", "Stock Entry", "Material Request", "Project", "Task",
        "Contact", "Address", "User", "Company",
    ]

    def __init__(self):
        super().__init__()
        self.name = "universal_search"
        self.description = (
            "Universal search across ALL accessible documents and ALL fields "
            "(name, text, numbers, amounts, status). Type anything - customer name, "
            "amount like 7500, status, date - it finds matching records across the entire system. "
            "Use this instead of search_documents for comprehensive multi-field search."
        )
        self.category = "Search"
        self.source_app = "niv_tools"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search anything - name, text, number, amount, status"
                },
                "doctype": {
                    "type": "string",
                    "description": "Optional: limit search to specific DocType"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20)"
                },
            },
            "required": ["query"],
        }

    def execute(self, arguments):
        query = (arguments.get("query") or "").strip()
        if not query:
            return {"success": False, "error": "Empty search query"}

        doctype = arguments.get("doctype")
        limit = arguments.get("limit", 20)

        if doctype:
            return self._search_single_doctype_full(doctype, query, limit)
        else:
            return self._global_search(query, limit)

    @staticmethod
    def _is_numeric(query):
        cleaned = query.replace(",", "").replace(" ", "")
        try:
            return True, float(cleaned)
        except (ValueError, TypeError):
            return False, None

    @staticmethod
    def _get_searchable_fields(meta, include_numeric=False):
        text_types = {"Data", "Text", "Small Text", "Text Editor", "Long Text", "Select", "Link"}
        numeric_types = {"Currency", "Float", "Int", "Percent"}
        text_fields = []
        numeric_fields = []

        for field in meta.fields:
            if field.hidden:
                continue
            if field.fieldtype in text_types:
                text_fields.append(field.fieldname)
            if include_numeric and field.fieldtype in numeric_types:
                numeric_fields.append(field.fieldname)

        if "name" not in text_fields:
            text_fields.insert(0, "name")
        if meta.title_field and meta.title_field not in text_fields:
            text_fields.insert(1, meta.title_field)

        return text_fields[:8], numeric_fields[:5]

    @staticmethod
    def _get_display_fields(meta):
        display = ["name"]
        if meta.title_field and meta.title_field != "name":
            display.append(meta.title_field)

        for field in meta.fields:
            if field.hidden or field.fieldtype in ("Section Break", "Column Break", "Tab Break"):
                continue
            if field.fieldname in ("status", "docstatus", "grand_total", "total",
                                   "net_total", "customer_name", "supplier_name",
                                   "item_name", "employee_name", "posting_date",
                                   "transaction_date", "company"):
                if field.fieldname not in display:
                    display.append(field.fieldname)
        if "modified" not in display:
            display.append("modified")
        return display[:8]

    def _search_dt(self, doctype, query, is_numeric, numeric_val, limit=5):
        try:
            if not frappe.db.exists("DocType", doctype):
                return []
            if not frappe.has_permission(doctype, "read"):
                return []

            meta = frappe.get_meta(doctype)
            text_fields, numeric_fields = self._get_searchable_fields(meta, include_numeric=is_numeric)
            display_fields = self._get_display_fields(meta)

            or_filters = []
            for f in text_fields:
                or_filters.append([doctype, f, "like", "%%%s%%" % query])

            if is_numeric and numeric_val is not None:
                for f in numeric_fields:
                    or_filters.append([doctype, f, "=", numeric_val])

            if not or_filters:
                return []

            results = frappe.get_all(
                doctype, or_filters=or_filters, fields=display_fields,
                limit=limit, order_by="modified desc",
            )
            for r in results:
                r["doctype"] = doctype
            return results
        except Exception:
            return []

    def _global_search(self, query, limit=20):
        is_numeric, numeric_val = self._is_numeric(query)
        results = []
        searched = []

        per_dt_limit = max(3, limit // 6)
        for dt in self.PRIORITY_DOCTYPES:
            dt_results = self._search_dt(dt, query, is_numeric, numeric_val, per_dt_limit)
            if dt_results:
                results.extend(dt_results)
                searched.append(dt)

        if len(results) < limit:
            all_dts = frappe.get_all("DocType", filters={"istable": 0, "issingle": 0},
                                     fields=["name"], limit=200)
            remaining = [d.name for d in all_dts if d.name not in self.PRIORITY_DOCTYPES]
            for dt in remaining[:30]:
                if len(results) >= limit:
                    break
                dt_results = self._search_dt(dt, query, is_numeric, numeric_val, 3)
                if dt_results:
                    results.extend(dt_results)
                    searched.append(dt)

        seen = set()
        unique = []
        for r in results:
            key = "%s:%s" % (r.get("doctype"), r.get("name"))
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return {
            "success": True, "query": query, "is_numeric_search": is_numeric,
            "results": unique[:limit], "count": min(len(unique), limit),
            "total_found": len(unique), "searched_doctypes": searched,
        }

    def _search_single_doctype_full(self, doctype, query, limit=20):
        if not frappe.db.exists("DocType", doctype):
            return {"success": False, "error": "DocType '%s' not found" % doctype}
        if not frappe.has_permission(doctype, "read"):
            return {"success": False, "error": "No read permission for '%s'" % doctype}

        is_numeric, numeric_val = self._is_numeric(query)
        meta = frappe.get_meta(doctype)
        text_fields, numeric_fields = self._get_searchable_fields(meta, include_numeric=is_numeric)
        display_fields = self._get_display_fields(meta)

        or_filters = []
        for f in text_fields:
            or_filters.append([doctype, f, "like", "%%%s%%" % query])
        if is_numeric and numeric_val is not None:
            for f in numeric_fields:
                or_filters.append([doctype, f, "=", numeric_val])

        results = frappe.get_all(
            doctype, or_filters=or_filters, fields=display_fields,
            limit=limit, order_by="modified desc",
        )

        return {
            "success": True, "doctype": doctype, "query": query,
            "is_numeric_search": is_numeric, "results": results,
            "count": len(results), "search_fields": text_fields + numeric_fields,
        }
