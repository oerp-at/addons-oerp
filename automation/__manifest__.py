# pylint: disable=manifest-required-author
{
    'name': 'Automation',
    'version': '14.0.1.0.0',
    'summary': 'Provide an automation framework',
    'category': 'Automation',
    'author': 'Martin Reisenhofer',
    'maintainers': ['mreisenhofer'],
    'website': 'https://github.com/oerp-at',
    'license': 'LGPL-3',
    'depends': ['base',
                'util_time',
                'util_json',
                'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/automation_menu.xml',
        'views/task_log.xml',
        'views/stage_view.xml',
        'views/cron_view.xml',
        'views/task_view.xml',
        'data/cron.xml'
    ],
    'installable': True
}
