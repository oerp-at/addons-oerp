# post/pre-migration.py
def migrate(cr, version):
    cr.execute('DELETE FROM automation_task_token')