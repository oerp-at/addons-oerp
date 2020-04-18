/*global Ext:false*/

Ext.define('DeliveryPicking.store.OpStore', {
    extend: 'Ext.data.Store',
    requires: [
       'DeliveryPicking.model.Op'
    ],      
    config: {
        model: 'DeliveryPicking.model.Op'
    }
});
