import json
from odoo import fields


class Json(fields.Field):
    """Provide a json field type
    """

    type = "json"
    column_type = ("json", "json")

    def __init__(self,
                 string=fields.Default,
                 base_type=fields.Default,
                 **kwargs):
        super().__init__(string=string, _base_type=base_type, **kwargs)

    def loads(value):
        if value is None or value is False:
            return False
        if isinstance(value, str):
            return json.loads(value)
        return value

    def dumpflat(value):
        if not value:
            return ""
        if not isinstance(value, str):
            return json.dumps(value)
        return value

    def dumps(value):
        if not value:
            return None
        if not isinstance(value, str):
            return json.dumps(value, indent=4)
        return value

    def convert_to_cache(self, value, record, validate=True):
        return Json.dumps(value)

    def convert_to_write(self, value, record):
        return Json.dumps(value)

    def convert_to_column(self, value, record, values=None, validate=True):
        return Json.dumps(value)

    def convert_to_record(self, value, record):
        return Json.dumps(value)

    def convert_to_read(self, value, record, use_name_get=True):
        return Json.dumps(value)

    def convert_to_export(self, value, record):
        return Json.dumpflat(value)

    def convert_to_display_name(self, value, record):
        return Json.dumpflat(value)
