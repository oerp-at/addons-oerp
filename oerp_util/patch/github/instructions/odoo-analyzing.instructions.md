---
name: 'Odoo External API – Use JSON-2'
description: 'Use the Odoo JSON-2 API instead of XML-RPC when analyzing or querying the running Odoo instance'
---

# Odoo External API – Use JSON-2

When querying a running Odoo instance for analysis, debugging, or data inspection, use the **JSON-2 API** (`/json/2`) instead of XML-RPC (`xmlrpc/2`).

XML-RPC and JSON-RPC are deprecated and scheduled for removal in Odoo 22.

## Authentication

Use a **bearer API key** in the `Authorization` header. Create a key via the admin user's Preferences > Account Security > New API Key. Plain passwords do **not** work as bearer tokens – a real API key is always required.

## Python Pattern

```python
import requests

URL = "http://localhost:8069"
DB = "mydb"
API_KEY = "..."  # create via Preferences > Account Security > New API Key
HEADERS = {
    "Authorization": f"bearer {API_KEY}",
    "X-Odoo-Database": DB,
    "Content-Type": "application/json; charset=utf-8",
}

# search_read – single call, single transaction
res = requests.post(
    f"{URL}/json/2/account.move/search_read",
    headers=HEADERS,
    json={
        "domain": [["name", "ilike", "ER/2026"]],
        "fields": ["id", "name", "state", "amount_total"],
        "limit": 10,
    },
)
res.raise_for_status()
records = res.json()

# read with explicit IDs
res = requests.post(
    f"{URL}/json/2/account.move/read",
    headers=HEADERS,
    json={
        "ids": [42, 43],
        "fields": ["name", "date", "partner_id"],
    },
)
res.raise_for_status()
data = res.json()
```

## Key Differences to XML-RPC

| XML-RPC | JSON-2 |
|---------|--------|
| `models.execute_kw(db, uid, pwd, model, method, [args], {kwargs})` | `requests.post(URL/json/2/model/method, json={...})` |
| Auth via `uid` + password per call | Auth via `Authorization: bearer <key>` header |
| `search_read` args: `[[domain]], {fields, limit, ...}` | `search_read` body: `{"domain": [...], "fields": [...]}` |
| Positional args list + keyword dict | Named parameters in JSON body |
| Returns via XML-RPC deserialization | Returns plain JSON (use `res.json()`) |

## Rules

- Prefer `search_read` over separate `search` + `read` calls (single transaction).
- Always call `res.raise_for_status()` to catch HTTP errors.
- Set `X-Odoo-Database` header when the server hosts multiple databases.
- Plain passwords do **not** work as bearer tokens; always use a real API key.
