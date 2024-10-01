# pylint: disable=manifest-required-author
# pylint: disable=missing-readme
{
    'name': 'Automation',
    'version': '14.0.4.0.0',
    'summary': 'Simple Automation Framework',
    'category': 'Automation',
    'author': 'martin-reisenhofer',
    'maintainers': ['martin-reisenhofer'],
    'website': 'https://github.com/oerp-at',
    'license': 'LGPL-3',
    'depends': ['base',
                'mail',
                'oerp_util'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/automation_menu.xml',
        'views/task_log.xml',
        'views/stage_view.xml',
        'views/cron_view.xml',
        'views/task_view.xml',
        'views/task_example.xml',
        'data/example_task.xml'
    ],
    'installable': True
}
