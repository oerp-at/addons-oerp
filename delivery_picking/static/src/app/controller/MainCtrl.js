/* global Ext:false, ViewManager:false, Core: false, console: false */

Ext.define('DeliveryPicking.controller.MainCtrl', {
    extend: 'Ext.app.Controller',
    requires:[
         'Ext.ux.Deferred',         
         'Ext.util.BarcodeScanner',
         'Ext.dataview.List',
         'Ext.form.Panel',
         'Ext.form.FieldSet',
         'Ext.field.Number',
         'Ext.field.Spinner',
         'Ext.view.ViewManager',         
         'Ext.view.NumberInputView',
         'Ext.Menu',
         'DeliveryPicking.store.OpStore',
         'DeliveryPicking.core.Core'
    ],
    config: {
         refs: {
            mainView: '#mainView',
            refreshButton: '#refreshButton',
            saveButton: '#saveButton',
            packButton: '#packButton',
            mainMenuButton: '#mainMenuButton'
         },
         control: {
            mainView: {
                initialize: 'prepare',
                activeitemchange : 'onActiveItemChange'
            },             
            'button[action=saveRecord]': {
                tap: 'onSaveRecord'
            },
            'button[action=pack]': {
                tap: 'onPack' 
            },
            'button[action=createDelivery]': {
                tap: 'onCreateDelivery' 
            },
            'button[action=reprintDelivery]': {
                tap: 'onReprintDelivery' 
            },
            mainMenuButton: {
                tap: 'onShowMainMenu'                
            }
         }
    },

    prepare: function() {
        var self = this;
        ViewManager.startLoading("Setup...");
        
        // setup         
        Core.getClient().then(function() {
            try {
                ViewManager.stopLoading();
                self.loadMainView();                
            } catch (err) {
                console.error(err);
            }
        }, function(err) {
            ViewManager.stopLoading();
            Ext.Msg.alert('Verbindungsfehler','Keine Verbindung zum Server möglich', function() {
                self.restart();
            });            
        });
        
        //barcode scanner
        self.barcodeScanner = Ext.create('Ext.util.BarcodeScanner', {
                keyListener : function(keycode) { self.onKeyCode(keycode); },
                barcodeListener : function(code) { self.onBarcode(code); }
        });
        
        // activate keyboard listener
        ViewManager.pushKeyboardListener(self);
    },
    
    restart: function() {
        ViewManager.startLoading("Neustart...");
        Core.restart();  
    },

    loadMainView: function() {
        var self = this;
        if ( !self.basePanel ) {
        
            // setup menu
            var menu = Ext.create('Ext.Menu', {
                    cls: 'MainMenu',
                    xtype: 'menu',
                    defaults: {
                        xtype: 'button',
                        flex: 1,
                        cls: 'MenuButton',
                        ui: 'posInputButtonBlack'
                    },
                    items: [
                        {
                            text: 'Paketliste erstellen',
                            action: 'createDelivery',
                            ui: 'posInputButtonOrange'
                        },
                        {
                            text: 'Paketliste erneut drucken',
                            action: 'reprintDelivery'
                        }
                    ]
            });
            
            // load main view
            self.basePanel = Ext.create('Ext.Panel', {
                barcodeEnabled: true,
                layout: 'vbox',
                menu: menu,
                items: [
                    {
                        flex: 1                         
                    },
                    {
                        flex: 1,  
                        html: '<div class="StatusDisplay"></div>'                
                    },
                    {
                        flex: 1                    
                    }
                ],
                title: Core.getStatus().company
            });               
                     
            self.getMainView().push(self.basePanel);
        }
    },
    
    getActiveItem: function() {
        return this.getMainView().getActiveItem();
    },
    
    onActiveItemChange: function() {
        var self = this;
        var view = self.getActiveItem();
        
        // check barcode enabled
        if ( ViewManager.hasViewOption(view, 'barcodeEnabled') ) {
            self.onKeyDown = function(event) {
                self.barcodeScanner.detectBarcode(event);
            };
        } else {
            self.onKeyDown = function(event) {
            };
        }
        
        // packable
        self.getPackButton().setHidden(!ViewManager.hasViewOption(view, 'packable'));
        
        // update button        
        ViewManager.updateButtonState(view, {
            saveButton: self.getSaveButton(),
            menuButton: self.getMainMenuButton()     
        });
    },
    
    onReloadData: function() {
        this.getActiveItem().fireEvent('reloadData');
    },
    
    onSaveRecord: function() {
        ViewManager.saveRecord(this.getMainView());
    },
    
    onKeyCode: function(keycode) {
    
    },
    
    onKeyDown: function(e) {
    
    },
    
    onBarcode: function(code) {
        var self = this;
        if ( !self.barcodeActive ) {   
            self.barcodeActive = true;       
            ViewManager.startLoading('Suche Lieferschein');
            Core.call('stock.picking','picking_app_scan', [code]).then(function(picking) {
                ViewManager.stopLoading();
                try {
                    // check picking
                    if ( picking.found_picking_id && picking.found_picking_id != picking.id ) {
                        var msgView = Ext.Msg.confirm(picking.found_picking_name,'Sollen die Lieferdokumente nochmal gedruckt werden?', function(buttonId) {
                            msgView.hide();
                            setTimeout(function() {                     
                                if ( buttonId == 'yes' ) {
                                    // notify
                                    Core.call('stock.picking','picking_app_pack_notify', [picking.found_picking_id]).then(function() {
                                        self.showPicking(picking); 
                                        self.barcodeActive = false;              
                                    }, function(err) {
                                        self.barcodeActive = false;
                                        ViewManager.handleError(err, {name:'Packen', message: 'Benachrichtigung fehlgeschlagen'});
                                    });
                                } else {
                                    self.barcodeActive = false;
                                    self.showPicking(picking); 
                                }
                            }, 0);
                        });                    
                    } else {
                        self.barcodeActive = false;
                        self.showPicking(picking);
                    }
                } catch (err) {
                    self.barcodeActive = false;
                    ViewManager.handleError(err, {name:'Unerwarteter Fehler', message: 'Scan fehlgeschlagen'});
                }
            }, function(err) {
                self.barcodeActive = false;
                ViewManager.handleError(err, {name:'Scan', message: 'Scan fehlgeschlagen'});
            });
        }
    },
    
    onPack: function() {
        var self = this;
        var activeView = self.getActiveItem();
        
        // check if picking
        var picking_id = activeView.picking_id;
        if ( !picking_id ) return;
        
        // get store
        var opStore = activeView.getStore();
        
        var preparePack = function(weight, add_picking_id) {                
            // set all for packing if no quantity 
            // was set
            var qty_done = 0;
            opStore.each(function(op) {
                qty_done += op.get('qty_done') || 0;
            });
            
            var pack = function() {
                // pack
                ViewManager.startLoading('Packvorgang');
                Core.call('stock.picking','picking_app_pack',[picking_id, weight, add_picking_id]).then(function(next_picking) {            
                    ViewManager.stopLoading();
                    self.getMainView().pop();
                    
                    // notify
                    Core.call('stock.picking','picking_app_pack_notify', [picking_id]).then(function() {
                        self.showPicking(next_picking);
                    }, function(err) {
                        ViewManager.handleError(err, {name:'Packen', message: 'Benachrichtigung fehlgeschlagen'});
                    });
                    
                }, function(err) {            
                    ViewManager.handleError(err, {name:'Packen', message: 'Packvorgang konnte nicht abgeschlossen werden'});
                });
            };
            
            if ( !qty_done && opStore.getCount() ) {
                var updateOps = [];
                var updateOpsIndex = 0;
                
                ViewManager.startLoading('Aktualisiere Daten');
                
                opStore.each(function(op) {
                    op.set('qty_done', op.get('qty'));
                    updateOps.push(op);
                });
                
                var updateNext = function() {
                    self.updateOp(updateOps[updateOpsIndex]).then(function() {
                        if ( ++updateOpsIndex < updateOps.length ) {
                            updateNext();
                        } else {
                            pack();
                        }
                    }, function(err) {
                        ViewManager.handleError(err, {name:'Fehler', message: 'Fehler beim synchronisieren der Daten'});
                    });
                };
                updateNext();
                 
            } else {
                pack();
            }
        };
        
        // create weight input        
        if ( !self.weightInput ) {
            // create
            self.weightInput = Ext.create('Ext.view.NumberInputView', {
                xtype: 'numberinput',
                centered : true,
                autoRemoveHandler: true,
                title: 'Gewicht in Kg'
            });
            
            // override keydown
            self.weightInput.onKeyDown = function(e) {
              if ( !self.weightInput.barcodeScanner ) {
                  self.weightInput.barcodeScanner = Ext.create('Ext.util.BarcodeScanner', {
                          keyListener : function(keycode) {
                              self.weightInput.onKeyCode(keycode);
                          },
                          barcodeListener : function(code) { 
                              ViewManager.startLoading("Lade Lieferschein...");
                              Core.call('stock.picking','picking_app_scan', [code, picking_id]).then(function(picking) {
                                  ViewManager.stopLoading();
                                  try {
                                      // check picking
                                      if ( picking.found_picking_id && picking.found_picking_id != picking.id ) {
                                          self.addToPickingId = picking.found_picking_id;
                                          self.weightInput.setTitle('Gewicht in Kg</br>dazupacken zu <larger>'+picking.found_picking_name+'</larger>');                                                               
                                      } else {
                                          ViewManager.handleError({name:'not_finished', message: 'Der Lieferschein wo hinzugefügt werden soll wurde noch nicht gepackt!'});
                                      }
                                  } catch (err) {
                                      ViewManager.handleError(err, {name:'scan_failed', message: 'Scan fehlgeschlagen'});
                                  }
                              }, function(err) {
                                  ViewManager.handleError(err, {name:'scan_failed', message: 'Scan fehlgeschlagen'});
                              });
                      }
                  });
              }
              
              // detect barcode
              self.weightInput.barcodeScanner.detectBarcode(e);
            };
             
            self.getMainView().add(self.weightInput);           
        }
        
        // show weight input
        self.addToPickingId = 0;
        self.weightInput.setTitle('Gewicht in Kg');
        self.weightInput.setHandler(function(view, value) {
            preparePack(value, self.addToPickingId);
        });        
        self.weightInput.show();       
    },

    showPicking: function(picking) {
        if ( !picking || !picking.name ) return;
        
        var self = this;

        // update data       
        var opStore = Ext.create("DeliveryPicking.store.OpStore");
        opStore.setData(picking.ops);
        
       
        if ( !self.opTmpl ) {
            self.opTmpl =  Ext.create('Ext.XTemplate',
                '<div class="{[this.getTableClass(values)]}">',
                    '<div class="OpItemName">',
                        '{name}',
                    '</div>',
                    '<tpl if="qty != qty_done && !package_count">',
                        '<div class="OpItemActionCell"><div class="OpItemActionOne x-button x-button-posInputButtonOrange x-layout-box-item x-sized">+1</div></div>',
                        '<div class="OpItemActionCell"><div class="OpItemActionAll x-button x-button-posInputButtonGreen x-layout-box-item x-sized">++</div></div>',
                    '</tpl>',
                    '<tpl if="package_count &gt; 0">',                   
                        '<div class="OpItemAmountCell">',
                            '<div class="OpItemLabel">Pakete</div>',
                            '<div class="OpItemAmount">+{package_count}</div>',                        
                        '</div>',
                    '<tpl else>',
                        '<div class="OpItemAmountCell">',
                            '<div class="OpItemLabel">{uom}</div>',
                            '<div class="OpItemAmount">{qty_done} / {qty}</div>',                        
                        '</div>',
                    '</tpl>',
                '</div>',
                {
                    getTableClass: function(values) {
                        if ( values.qty == values.qty_done || values.package_count ) {
                            return 'OpItemTableAll';
                        } else if ( values.qty_done > 0 ) {
                            return 'OpItemTableQty';
                        } else {
                            return 'OpItemTable';
                        }
                    }
                }
            );
        }        
        
        // create view
        var mainView = self.getMainView();   
        var pickingView = Ext.create('Ext.dataview.DataView', {
                scrollable: 'vertical',
                cls: 'OpItemView',
                itemTpl: self.opTmpl,
                flex: 1,
                store: opStore,
                title: picking.name,
                packable: true,
                listeners: {
                    itemtap: function(view, index, target, data, e, opts) {
                        var element = Ext.get(e.target);
                        var record = opStore.getAt(index);
                        if ( element.hasCls("OpItemActionAll") ) {
                            record.set('qty_done', record.get('qty'));
                            self.updateOp(record);
                        } else if ( element.hasCls("OpItemActionOne") )  {
                            record.set('qty_done', record.get('qty_done')+1);
                            self.updateOp(record);
                        } else {
                            self.editOp(record);
                        }
                    }
                }
        });
        
        pickingView.picking_id = picking.id;        
        mainView.push(pickingView);
    },
    
    updateOp: function(record) {
        var deferred = Ext.create('Ext.ux.Deferred');
        ViewManager.startLoading('Aktualisiere Zeile');
        var data = record.getData();
        Core.call('stock.picking','picking_app_update',[data]).then(function(result) {
            ViewManager.stopLoading();            
            try {
                record.setData(result);
                record.commit();
                deferred.resolve();            
            } catch (err) {
                ViewManager.handleError(err, {name:'Unerwarteter Fehler', message: 'Update fehlgeschlagen'});
                deferred.reject(err);
            }
        }, function(err) {            
            ViewManager.handleError(err, {name:'Scan', message: 'Update fehlgeschlagen'});
            record.rollack();
            deferred.reject(err);
        });
        
        return deferred.promise();
    },
    
    editOp: function(record) {
        // create view
        var self = this;
        var mainView = self.getMainView();        
        var formPanel = Ext.create('Ext.form.Panel', {
                title: record.get('name'),
                fullscreen: true,
                saveable: true,       
                savedHandler: function() {
                    return self.updateOp(record);
                },     
                items: [{
                    xtype: 'fieldset',
                    items: [                   
                        {
                            xtype: 'spinnerfield',
                            label: record.get('uom'),
                            name: 'qty_done',
                            stepValue: 1,
                            minValue: 0                            
                        },
                        {
                            xtype: 'spinnerfield',
                            stepValue: 1,
                            minValue: 0,
                            maxValue: 10,
                            label: 'Pakete',
                            name: 'package_count'
                        }                    
                    ]  
                }]   
            }
        );
                
        formPanel.setRecord(record);
        mainView.push(formPanel);
    },
    
    onShowMainMenu: function() {
       var menu = Ext.Viewport.getMenus().right;
       if ( menu ) {
           if ( menu.isHidden() ) {
                Ext.Viewport.showMenu("right");
           } else {
                Ext.Viewport.hideMenu("right");
           }
       }
    },
    
    onCreateDelivery: function() {
        ViewManager.startLoading('Erstelle Paketliste');
        Core.call('stock.picking','picking_app_create_delivery',[]).then(function(result) {
            ViewManager.stopLoading();
        }, function(err) {            
            ViewManager.handleError(err, {name:'Paketliste', message: 'Paketliste konnte nicht erstellt werden'});
        });        
    },
    
    onReprintDelivery: function() {
        ViewManager.startLoading('Drucke Paketliste erneut');
        Core.call('stock.picking','picking_app_reprint_delivery',[]).then(function(result) {
            ViewManager.stopLoading();
        }, function(err) {            
            ViewManager.handleError(err, {name:'Paketliste', message: 'Wiederholter Druck der Paketliste fehlgeschlagen'});
        });        
    }   
});