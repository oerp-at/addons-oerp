/* global Ext:false */

Ext.define('DeliveryPicking.view.Main', {
    extend: 'Ext.navigation.View',
    xtype: 'main',
    id: 'mainView',
    requires: [
    ],    
    config: {
        defaultBackButtonText: 'Zurück',
        layout: {
            type: 'card',
            animation: false            
        },
        navigationBar: {            
            items: [
                {
                    xtype: 'button',
                    id: 'saveButton',
                    text: 'Speichern',                                  
                    align: 'right',
                    action: 'saveRecord',
                    hidden: true
                },                
                {
                    xtype: 'button',
                    id: 'packButton',
                    text: 'Packen',                                  
                    align: 'right',
                    action: 'pack',
                    hidden: true
                },
                {
                    xtype: 'button',
                    iconCls: 'list',
                    id: 'mainMenuButton',
                    ui: 'plain',
                    align: 'right',
                    hidden: true
                }
            ]
        }    
    }
});
