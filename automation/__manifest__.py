# pylint: disable=manifest-required-author
# pylint: disable=missing-readme
{
    'name': 'Automation',
    'version': '18.0.1.0.0',
    'summary': 'Simple Automation Framework',
    'category': 'Automation',
    'author': 'martin-reisenhofer',
    'maintainers': ['martin-reisenhofer'],
    'website': 'https://github.com/oerp-at',
    'license': 'LGPL-3',
    'depends': ['base',
                'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/example_task.xml',
        'data/ir_cron.xml',
        'views/automation_menu.xml',
        'views/task_log_views.xml',
        'views/task_views.xml',
        'views/task_example.xml'
    ],
    'installable': True
}
