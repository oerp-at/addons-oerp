nginx-odoo
==========

Create an ngnix config for an Odoo server


Requirements
------------

Running Odoo server


Role Variables
--------------

| Variable                 | Description                                     | Default  |
|--------------------------|-------------------------------------------------|----------|
| instance                 | odoo instance name                              |          |
| backend                  | odoo server host                                |          |
| backend_port             | Internal odoo port                              | 8069     |
| backend_port_longpolling | Define database user for odoo service           | 8072     |
| aliases                  | Server aliases                                  |          |
| forwards                 | server forwards                                 |          |
| admin_email              | email of the server admin                       |          |


Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
        - odoo14: 
          instance: odoo
          frontend: erp.odoo.com
          backend: odoo.test.local
          ssl: true

          

License
-------

BSD

