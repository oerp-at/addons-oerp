"""hr.contract.type is hr.employee.type in 20.0.

hr 20.0 defines its employee types under the 19.0 xml ids
``hr.contract_type_*`` (hr/data/hr_employee_type_data.xml); without the model
rename the data import fails on records of a different model.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if util.table_exists(cr, "hr_contract_type") and not util.table_exists(cr, "hr_employee_type"):
        util.rename_model(cr, "hr.contract.type", "hr.employee.type")
    for model, table in (("hr.version", "hr_version"), ("hr.job", "hr_job")):
        if util.column_exists(cr, table, "contract_type_id"):
            util.rename_field(cr, model, "contract_type_id", "employee_type_id")
