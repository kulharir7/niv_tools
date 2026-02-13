"""Compatibility helpers for Frappe v14/v15+.

Keep version-specific checks in one place so tool code stays clean.
"""
from __future__ import annotations

import frappe


def get_frappe_major() -> int:
    """Return Frappe major version (14, 15, ...)."""
    try:
        # v14/v15 both expose this
        return int(frappe.__version__.split(".")[0])
    except Exception:
        # safest default for legacy environments
        return 14


def is_v14() -> bool:
    return get_frappe_major() == 14


def is_v15_plus() -> bool:
    return get_frappe_major() >= 15


def has_doctype(doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False
