---
name: 'Test Partner Defaults'
description: 'Default country and VAT for test partners/companies'
applyTo: '**/tests/**'
---

# Test Partner Defaults

When creating test partners or companies in tests, unless explicitly specified otherwise:

- **Country:** Use Austria (`cls.env.ref("base.at")` or `self.env.ref("base.at")`)
- **VAT:** Use a valid Austrian UID number (format: `ATU` + 8 digits, e.g. `ATU12345675`)

## Valid Austrian UID Numbers for Tests

Use these pre-validated numbers to avoid `base_vat` validation errors:

| VAT | Use case |
|---|---|
| `ATU12345675` | Default test partner |
| `ATU66994005` | Secondary test partner |

## Example

```python
cls.partner = cls.env["res.partner"].create({
    "name": "Test Partner",
    "vat": "ATU12345675",
    "country_id": cls.env.ref("base.at").id,
})
```

## Exception

When testing EC sales / cross-border scenarios, EU partner countries (e.g. `base.de`) and their respective VAT formats are required. Use valid VAT numbers for the target country (e.g. `DE123456788` for Germany).
