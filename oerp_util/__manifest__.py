# pylint: disable=manifest-required-author
# pylint: disable=missing-readme
# pylint: disable=license-allowed
{
    'name': 'Utils',
    'version': '17.0.1.0.0',
    'summary': 'Base Utils for Testing, Development and Deployment',
    'category': 'Base',
    'author': 'martin-reisenhofer',
    'maintainers': ['martin-reisenhofer'],
    'website': 'https://github.com/oerp-at',
    'license': 'LGPL-3',
    'depends': ['base',
                'mail'],
    'data': [
    ],
    'python':[
        'azure-core',
        'azure-ai-formrecognizer'
    ]
    'installable': True
}
