/*global Ext:false, openerp:false*/

Ext.define('DeliveryPicking.core.Core', {
    extend: 'Ext.core.Odoo',
    singleton : true,
    alternateClassName: 'Core',

    config : {
         version : '3.0.0',
         profileName: 'Picking'
    }    
});
