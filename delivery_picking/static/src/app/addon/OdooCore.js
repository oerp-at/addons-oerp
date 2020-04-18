/*global Ext:false, openerp:false, ViewManager:false, openerplib:false, Ext.Viewport:false, URI:false*/

Ext.define('Ext.core.Odoo', {
    
    requires: [
        'Ext.ux.Deferred',
        'Ext.Panel',
        'Ext.Toolbar',
        'Ext.Spacer',
        'Ext.Button',
        'Ext.form.Panel',
        'Ext.form.FieldSet',
        'Ext.field.Text',
        'Ext.field.Password',
        'Ext.client.OdooClient'
    ],
    
    config : {
      context: null,
      profile: null,
      status: null,
      url: null,
      profileName: 'OdooCore'
    },
    
    constructor: function(config) {
      this.initConfig(config);
      this.loadProfile();  
    },
    
    resetProfile: function() {
      var profileName = this.getProfileName();
      var profileStr = window.localStorage.getItem(profileName);
      if ( profileStr ) {
         window.localStorage.removeItem(profileName);
      }
      this.setProfile(null);
    },
    
    loadProfile: function() {
      var profileName = this.getProfileName();
      var profileStr = window.localStorage.getItem(profileName);
      if ( profileStr ) {
        this.setProfile(JSON.parse(profileStr));
      }     
    },
    
    saveProfile: function(profile) {      
      if ( !profile ) {
        profile = this.getProfile();
      }      
      var profileName = this.getProfileName();
      window.localStorage.setItem(profileName, JSON.stringify(profile));
      this.setProfile(profile);      
    },
    
    restart: function() {
      var url = this.getUrl();
      setTimeout(function() {
          if (url) window.location.href = url;
          window.location.reload();
      }, 1000);
    },
 
    getClient: function(profile) {
        var self = this;
        var deferred = Ext.create('Ext.ux.Deferred');
        var forwardError = false;
        if ( !self.client ) {
        
            // ist test
            if ( !profile ) {            
              profile = this.getProfile();
              forwardError = true;
            }
            
            if ( !profile ) {
              openerplib.json_rpc("/web/database/get_list", null, [], function(err, res) {
                  profile = {};
                  if ( err === null ) {
                  
                    // set database
                    if ( res.length == 1 ) { 
                      profile.database = res[0];
                    }
                    
                    // get connection form url
                    var url = URI(document.URL);
                    
                    // get port
                    var port;
                    try {
                      port = url.port();
                    } catch(url_err) {                      
                    }
                    
                    // set defaults if no port
                    if ( !port ) {
                      if ( "https" === url.protocol() ) {
                        port = 443;
                      } else {
                        port = 80;
                      }
                    }
                                        
                    profile.port = port; 
                    profile.host = url.hostname();                      
                  }
                  
                  var items = [];
                  
                  if ( !profile.host ) {
                  
                    // host
                    items.push({
                      xtype: 'textfield',
                      name: 'host',
                      label: 'Server',
                      placeHolder: 'fpos.oerp.at',
                      required: true,
                      autoComplete: false,
                      autoCorrect: false,
                      autoCapitalize: false
                    });
                    
                    // port
                    items.push({
                      xtype: 'textfield',
                      name: 'port',
                      label: 'Port',
                      placeHolder: '443',
                      required: true,
                      autoComplete: false,
                      autoCorrect: false,
                      autoCapitalize: false
                    });
                    
                  }
                  
                  
                  if ( !profile.database ) {
                    
                    // add database
                    items.push({
                      xtype: 'textfield',
                      name: 'database',
                      label: 'Datenbank',
                      placeHolder: 'odoo_fpos_xxx',
                      required: true,
                      autoComplete: false,
                      autoCorrect: false,
                      autoCapitalize: false
                    });
                    
                  }
                  
                  // add login
                  items.push({
                      xtype: 'textfield',
                      name: 'login',
                      label: 'Benutzer',
                      required: true,
                      autocomplete: false,
                      autoComplete: false,
                      autoCorrect: false,
                      autoCapitalize: false
                  });
                  
                  // add password
                  items.push({
                      xtype: 'passwordfield',
                      name: 'password',
                      label: 'Passwort',
                      required: true,
                      autoComplete: false,
                      autoCorrect: false,
                      autoCapitalize: false
                  });
                  
                  var panel = Ext.create('Ext.form.Panel', {
                    layout: 'vbox',
                    flex: 1,   
                    items: [
                      {
                        xtype: 'toolbar',
                        ui: 'light',
                        docked: 'top',
                        items: [
                          {
                            xtype: 'spacer'
                          },
                          {
                            text: 'Speichern',
                            listeners: {
                              tap: function() {
                                if ( ViewManager.validateView(panel) ) {
                                  // merge profile
                                  var values = panel.getValues();
                                  Ext.each(items, function(item) {
                                    profile[item.name] = values[item.name];
                                  });
                                  
                                  ViewManager.startLoading("Verbinde...");
                                  self.getClient(profile).then(function(client) {
                                    // stop
                                    ViewManager.stopLoading();
                                    // save profile
                                    self.saveProfile(profile);
                                    // hide and return result
                                    panel.hide();
                                    deferred.resolve(client);                                      
                                  }, function(err) {
                                    ViewManager.handleError(err, {
                                      name: 'connect_failed',
                                      message: 'Verbindung ist Fehlgeschlagen'
                                    });
                                  });
                                }
                              }                              
                            }
                          }
                        ]                 
                      },
                      {
                        xtype: 'panel',
                        flex: 1,
                        scrollable: {
                          direction: 'vertical',
                          indicators: false
                        },
                        items: [
                          {                        
                            xtype: 'fieldset',
                            title: 'Cloud',
                            items: items
                          }                        
                        ]
                      }
                      
                    ]                                      
                  });
                  
                  ViewManager.stopLoading();
                  Ext.Viewport.add(panel);
                  panel.show();
              }); 
            } else {
            
              var client = Ext.create('Ext.client.OdooClient', {
                  host : profile.host,
                  port : profile.port,
                  database : profile.database,
                  login : profile.login,
                  password : profile.password            
              });
              
              client.connect()['catch'](function(err) {
                deferred.reject(err);
                if ( !forwardError ) {
                  deferred.reject(err);
                } else {
                  ViewManager.stopLoading();
                  Ext.Msg.show({
                    title: err.name || 'Verbindungsfehler',
                    message: err.message || 'Keine Verbindung möglich',
                    buttons: [{text: 'Neustart', itemId:'restart', ui:'action'}, {text:'Profil löschen', itemId:'reset'}],
                    fn: function(res) {                     
                      if ( res == 'reset') {
                        Ext.Msg.show({
                          title: 'Profil löschen',
                          message: 'Zugangsdaten wirklich löschen?',
                          buttons: [{text: 'Ja', itemId:'yes'}, {text:'Nein', itemId:'no', ui:'action'}],
                          fn: function(res) {
                            ViewManager.startLoading("Neustart...");
                            if ( res == 'yes' ) {
                              self.resetProfile();      
                            }
                            self.restart();
                          }
                        });                        
                      } else {
                        ViewManager.startLoading("Neustart...");
                        self.restart();
                      }
                    }                  
                  });           
                }
              }).then(function() {
                
                // resolve status
                client.invoke("res.users", "read", [client.getClient().user_id, ["company_id"]]).then(function(res) {                  
                  // set company info
                  self.setStatus({
                    company_id: res.company_id[0],
                    company: res.company_id[1]       
                  });
                  
                  /*
                  // override client function
                  Ext.define('Override.data.proxy.Odoo', {
                      override: 'Ext.data.proxy.Odoo',
                      getClient: function() {
                        return self.client.getClient();
                      }
                  });*/
                  
                  // set client
                  self.client = client;
                  deferred.resolve(self.client);
                  
                }, function(err) {
                  deferred.reject(err); 
                });     
                     
              });              
            }
        } else {
            setTimeout(function() {
                deferred.resolve(self.client); 
            },0);
        }
        return deferred.promise();
    },
    
    call: function(model, method, args, kwargs) {
        var self = this;
        var deferred = Ext.create('Ext.ux.Deferred');

        self.getClient().then(function(client) {
          client.invoke(model, method, args, kwargs).then(function(res) {
            deferred.resolve(res);
          }, function(err) {
            deferred.reject(err);
          });
        }, function(err) {
          deferred.reject(err);
        });
        
        return deferred.promise();
    }
});