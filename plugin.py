# Basic Python Plugin Example
#
# Author: GizMoCuz
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="1.0.0" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://www.google.com/">
    <description>
        <h2>Plugin Title</h2><br/>
        Overview...
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Feature one...</li>
            <li>Feature two...</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Device Type - What it does...</li>
        </ul>
        <h3>Configuration</h3>
        Configuration options...
    </description>
    <params>
        <param field="Mode1" label="Comma seperated Chromecast name(s). " width="200px" required="true"/>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true" />
                <option label="Logging" value="File"/>
            </options>
        </param>
    </params>
</plugin>
"""
#############################################################################
#                      Imports                                              #
#############################################################################
import sys
try:
    import Domoticz
    debug = False 
except ImportError:
    import fakeDomoticz as Domoticz
    debug = True

import pychromecast

#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast
        self.Appnaam=""
        self.Volume=0

    def new_cast_status(self, status):
        if self.Appnaam != status.display_name:
            self.Appnaam = status.display_name
            Domoticz.Log("De app is veranderd naar "+status.display_name)
            UpdateDevice(4,0,str(self.Appnaam))

        if self.Volume != status.volume_level:
            self.Volume = status.volume_level
            Volume = int(self.Volume*100)
            Domoticz.Log("Updated Volume to "+str(Volume))
            UpdateDevice(2,Volume,str(Volume))

            
class StatusMediaListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast
        self.Mode=""
        self.Title=""

    def new_media_status(self, status):
        #Domoticz.Log("Mediastatus "+str(status))
        if self.Mode != status.player_state:
            self.Mode = status.player_state
            
            if(self.Mode) == "PLAYING":
                self.Mode="Play"
            elif(self.Mode) == "PAUSED":
                self.Mode="Pause"
            elif(self.Mode) == "STOPPED":
                self.Mode="Stop"

            Domoticz.Log("De afspeelmodus is veranderd naar "+status.player_state)
            UpdateDevice(1,0,self.Mode)
        if self.Title != status.title:
            self.Title = status.title
            Domoticz.Log("De titel is veranderd naar "+status.title)
            UpdateDevice(3,0,self.Title)

class BasePlugin:
    enabled = False
    def __init__(self):
        #self.var = 123
        return

    def onStart(self):
        # Check if images are in database
        Domoticz.Status("Checking if images are loaded")
        import pychromecast
        if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()
        
        # Check if devices need to be created
        createDevices()

        DumpConfigToLog()

        Domoticz.Heartbeat(30)

        Domoticz.Status("Starting up")

        self.chromecast=ConnectChromeCast()
        
        if self.chromecast != "":
            Domoticz.Status("Registering listeners")
            startListening(self.chromecast)

        return True

    def onHeartbeat(self):
        if self.chromecast == "":
            self.chromecast=ConnectChromeCast()

        Domoticz.Log("onHeartbeat called")

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

#############################################################################
#                       Device specific functions                           #
#############################################################################

def senderror(e):
    Domoticz.Error('Error on line {}'.format(sys.exc_info()[-1].tb_lineno)+" Error is "+str(e))
    return

def createDevices():
    # Are there any devices?
    ###if len(Devices) != 0:
        # Could be the user deleted some devices, so do nothing
        ###return

    # Give the devices a unique unit number. This makes updating them more easy.
    # UpdateDevice() checks if the device exists before trying to update it.

    # Add the barometer device
    if 1 not in Devices:
        OPTIONS1 =  {   "LevelActions"  : "|||||", 
                        "LevelNames"    : "Off|Playing|Stop|Paused",
                        "LevelOffHidden": "true",
                        "SelectorStyle" : "0"
                    }
        Domoticz.Log("Created 'Status' device")
        #Domoticz.Device(Name="Status", Unit=1, Type=244, Subtype=73, Switchtype=17, Used=1).Create()
        Domoticz.Device(Name="Control", Unit=1, TypeName="Selector Switch", Switchtype=18, Image=2, Options=OPTIONS1, Used=1).Create()
        UpdateImage(1, 'ChromecastLogo')

    if  1 in Devices: UpdateImage(1, 'ChromecastLogo')

    if 2 not in Devices:
        Domoticz.Log("Created 'Volume' device")
        Domoticz.Device(Name="Volume", Unit=2, Type=244, Subtype=73, Switchtype=7, Image=8, Used=1).Create()
        UpdateImage(1, 'ChromecastLogo')

    if 3 not in Devices:
        Domoticz.Log("Created 'Title' device")
        Domoticz.Device(Name="Title", Unit=3, Type=243, Subtype=19, Used=1).Create()
        UpdateImage(1, 'ChromecastLogo')

    if 4 not in Devices:
        OPTIONS4 =  {   "LevelActions"  : "|||||", 
                        "LevelNames"    : "Off|Spotify|Netflix|Youtube|Other",
                        "LevelOffHidden": "true",
                        "SelectorStyle" : "0"
                    }
        Domoticz.Log("Created 'App' device")
        Domoticz.Device(Name="App name", Unit=4, TypeName="Selector Switch", Switchtype=18, Options=OPTIONS4, Used=1).Create()
        UpdateImage(4, 'ChromecastLogo')

    Domoticz.Log("Devices check done")
    return

# Synchronise images to match parameter in hardware page
def UpdateImage(Unit, Logo):
    if Unit in Devices and Logo in Images:
        if Devices[Unit].Image != Images[Logo].ID:
            Domoticz.Log("Device Image update: 'Chromecast', Currently " + str(Devices[Unit].Image) + ", should be " + str(Images[Logo].ID))
            Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=str(Devices[Unit].sValue), Image=Images[Logo].ID)
    return

def ConnectChromeCast():
    #global debug
    #if debug==True:
    #    Domoticz.Status("Debug is tru")
    #    Parameters = {}
    #    Parameters["Mode1"]="Home mini Harmsen"

    Domoticz.Status("Checking for available chromecasts")
    try:
        chromecasts = pychromecast.get_chromecasts()
        Domoticz.Log(str(chromecasts))
    except Exception as e: 
        senderror(e)

    Domoticz.Status("Trying to connect to "+Parameters["Mode1"])
    try:
        chromecast = next(cc for cc in chromecasts if cc.device.friendly_name == Parameters["Mode1"])
        Domoticz.Status("Connected to " + Parameters["Mode1"])
    except StopIteration:
        chromecast = ""
        Domoticz.Error("Could not connect to "+Parameters["Mode1"])
    except Exception as e: 
        chromecast = ""
        senderror(e)

    return chromecast

def startListening(chromecast):
    Domoticz.Log("Registering listeners")
    listenerCast = StatusListener(chromecast.name, chromecast)
    chromecast.register_status_listener(listenerCast)

    listenerMedia = StatusMediaListener(chromecast.name, chromecast)
    chromecast.media_controller.register_status_listener(listenerMedia)
    Domoticz.Log("Done registering listeners")
    return chromecast

# Update Device into database
def UpdateDevice(Unit, nValue, sValue, AlwaysUpdate=False):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it
    if Unit in Devices:
        if Devices[Unit].nValue != nValue or Devices[Unit].sValue != sValue or AlwaysUpdate == True:
            Devices[Unit].Update(nValue, str(sValue))
            Domoticz.Log("Update " + Devices[Unit].Name + ": " + str(nValue) + " - '" + str(sValue) + "'")
    return

if debug==True:
    ConnectChromeCast()




