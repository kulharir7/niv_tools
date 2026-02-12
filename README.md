# 🛠️ Niv Tools

**7 AI Developer Tools for ERPNext** — Extends [Frappe Assistant Core (FAC)](https://github.com/buildswithpaul/Frappe_Assistant_Core) with powerful MCP tools.

These tools give your AI chatbot deep understanding of ERPNext — search across all DocTypes, map relationships, explore fields, test documents, monitor errors, rollback changes, and introspect the entire system.

---

## 🔧 Tools

| # | Tool | What It Does |
|---|------|-------------|
| 1 | **universal_search** | Search ALL fields across ALL DocTypes — names, amounts, status, dates, anything |
| 2 | **explore_fields** | Show field data lineage — where data comes from, how fields connect |
| 3 | **map_relationships** | Map DocType connections — links TO, links FROM, child tables, workflows, reverse links |
| 4 | **test_created_item** | Verify documents exist and work — creates/validates/deletes test records |
| 5 | **monitor_errors** | Fetch Error Log, group by type, detect error patterns |
| 6 | **rollback_changes** | Safely disable/delete Custom Fields, Scripts, Property Setters |
| 7 | **introspect_system** | Full system overview — apps, modules, doctypes, customizations, links |

---

## 📦 Installation

### Prerequisites
- Frappe v14+ or v15+
- [Frappe Assistant Core (FAC)](https://github.com/buildswithpaul/Frappe_Assistant_Core) installed

### Step 1: Install FAC (if not already installed)
```bash
bench get-app https://github.com/buildswithpaul/Frappe_Assistant_Core.git
bench --site your-site.localhost install-app frappe_assistant_core
```

### Step 2: Install Niv Tools
```bash
bench get-app https://github.com/kulharir7/niv_tools
bench --site your-site.localhost install-app niv_tools
```

### Step 3: Restart bench
```bash
bench restart
```

**That's it!** ✅ FAC automatically discovers the tools via hooks. No manual configuration needed.

### Docker Installation
```bash
# Inside your Docker container
docker exec -it <backend-container> bash
cd /home/frappe/frappe-bench
bench get-app https://github.com/kulharir7/niv_tools
bench --site <site-name> install-app niv_tools
bench restart
```

---

## 🔍 How It Works

Niv Tools uses Frappe's **hooks system** to register tools with FAC:

```python
# niv_tools/hooks.py
assistant_tools = [
    "niv_tools.tools.universal_search.UniversalSearch",
    "niv_tools.tools.field_explorer.FieldExplorer",
    "niv_tools.tools.test_created_item.TestCreatedItem",
    "niv_tools.tools.monitor_errors.MonitorErrors",
    "niv_tools.tools.rollback_changes.RollbackChanges",
    "niv_tools.tools.introspect_system.IntrospectSystem",
    "niv_tools.tools.map_relationships.MapRelationships",
]
```

FAC scans all installed apps for `assistant_tools` in hooks → discovers these tools → serves them via MCP protocol → your AI chatbot can use them.

**No manual registration. No config changes. Just install and go.**

---

## 📖 Tool Details

### 1. Universal Search
```
Input: {"query": "7500", "limit": 10}
→ Searches ALL fields across ALL DocTypes
→ Finds: Sales Invoice with amount 7500, Payment Entry with 7500, etc.
```

### 2. Explore Fields
```
Input: {"doctype": "Sales Order", "fieldname": "customer_name"}
→ Shows: field type, options, fetch_from, where data comes from
→ Traces: Customer → customer_name → auto-fetched into Sales Order
```

### 3. Map Relationships
```
Input: {"doctype": "Sales Order", "depth": 2}
→ Links TO: Customer, Item, Warehouse, Price List (31 DocTypes)
→ Links FROM: Sales Invoice, Delivery Note, Work Order (16 DocTypes)
→ Child Tables: Sales Order Item, Sales Taxes, Payment Schedule
→ Workflow: if any active workflow exists
→ Server Scripts, Print Formats, Notifications
```

### 4. Test Created Item
```
Input: {"doctype": "Customer", "test_data": {"customer_name": "Test"}}
→ Creates test record → Validates it exists → Deletes it
→ Returns: PASS/FAIL with details
```

### 5. Monitor Errors
```
Input: {"hours": 24, "limit": 50}
→ Fetches Error Log from last 24 hours
→ Groups by error type
→ Detects patterns (e.g., "ValidationError increasing")
```

### 6. Rollback Changes
```
Input: {"action": "list", "doctype": "Sales Order"}
→ Lists all customizations: Custom Fields, Client Scripts, Server Scripts
Input: {"action": "disable", "type": "Custom Field", "name": "Sales Order-custom_x"}
→ Safely disables the customization (can re-enable later)
```

### 7. Introspect System
```
Input: {"scope": "all"}
→ Installed apps + versions
→ All modules + DocType counts
→ Custom DocTypes, Custom Fields, Custom Scripts
→ Link field mapping across entire system
```

---

## 🤝 Works With

- [**Niv AI**](https://github.com/kulharir7/niv_ai) — AI chatbot for ERPNext (recommended)
- **Any FAC-compatible chatbot** — tools work with any app that uses FAC's MCP protocol
- **Frappe v14 & v15** — fully compatible with both versions

---

## 🏗️ Create Your Own Tools

Want to add custom tools? Create a new Frappe app:

```python
# your_app/hooks.py
assistant_tools = [
    "your_app.tools.my_tool.MyTool",
]

# your_app/tools/my_tool.py
from frappe_assistant_core.core.base_tool import BaseTool

class MyTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "my_tool"
        self.description = "What this tool does"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."}
            },
            "required": ["param1"]
        }

    def execute(self, arguments):
        # Your logic here
        return {"result": "done"}
```

Install your app → FAC auto-discovers it → AI can use it. That simple.

---

## 📄 License

MIT

## 👨‍💻 Author

**Ravindra Kulhari** — [GitHub](https://github.com/kulharir7)
