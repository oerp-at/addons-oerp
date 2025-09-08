# pylint: disable=manifest-required-author
# pylint: disable=missing-readme
{
    'name': 'Automation',

    'summary': 'Simple Automation Framework',

    'author': 'martin-reisenhofer',
    'maintainers': ['martin-reisenhofer'],
    'website': 'https://github.com/oerp-at',
    'version': '18.0.2.0.2',
    'license': 'LGPL-3',
    'category': 'Automation',

    'depends': [
        'base',
        'mail'
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/example_task.xml',
        'data/ir_cron.xml',
        'views/automation_menu.xml',
        'views/task_log_views.xml',
        'views/task_views.xml',
        'views/task_example.xml',
        'wizard/res_config_settings_views.xml'
    ],
}
