#
# Author: Tsjippy
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="1.0.0" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://github.com/Tsjippy/ChromecastPlugin/">
    <description>
        <h2>Chromecast</h2><br/>
        This plugin add devices to Domoticz to control your chromecast, and to retrieve its current app, title, playing mode.<br/><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Pause, Play or stop the app on the chromecast</li>
            <li>See current connected app, title and playing mode.</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Switch device - Playing mode</li>
            <li>Switch device - Connected app</li>
            <li>Volume device - See or adjust the current volume</li>
            <li>Text device - See current title</li>
        </ul>
        <h3>Configuration</h3>
        Just add your chromecast name
    </description>
    <params>
        <param field="Mode1" label="Chromecast name " width="200px" required="true"/>
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
import queue
from multiprocessing import Process, Queue

try:
    import Domoticz
    debug = False
except ImportError:
    import fakeDomoticz as Domoticz
    debug = True

import pychromecast
from pychromecast.controllers.youtube import YouTubeController

#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast
        self.Appname=""
        self.Volume=0

    def new_cast_status(self, status):
        if self.Appname != status.display_name:
            self.Appname = status.display_name
            Domoticz.Log("The app changed to "+status.display_name)
            UpdateDevice(4,0,str(self.Appname))

        if self.Volume != status.volume_level:
            self.Volume = status.volume_level
            Volume = int(self.Volume*100)
            Domoticz.Log("Updated volume to "+str(Volume))
            UpdateDevice(2,Volume,str(Volume))


class StatusMediaListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast
        self.Mode=""
        self.Title=""

    def new_media_status(self, status):
        #Domoticz.Log("Mediastatus "+str(status))
        if self.Mode != status.player_state and status.player_state != "IDLE" and status.player_state != "BUFFERING":
            self.Mode = status.player_state
            Domoticz.Log("The playing mode has changed to "+self.Mode)
            UpdateDevice(1,0,self.Mode)
        if self.Title != status.title:
            self.Title = status.title
            Domoticz.Log("The title is changed to  "+self.Title)
            UpdateDevice(3,0,self.Title)

class BasePlugin:
    enabled = False
    def __init__(self):
        self.heartbeatcounter=0

    def onStart(self):
        # Check if images are in database
        Domoticz.Status("Checking if images are loaded")
        if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()

        if Parameters["Mode6"]=="Debug":
            DumpConfigToLog()

        Domoticz.Status("Starting up")
        self.ConnectedChromecasts={}

        for i, chromecastname in enumerate(Parameters["Mode1"].split(",")): 
            self.ConnectedChromecasts[chromecastname.strip()]=[i,""]

        self.ConnectedChromecasts=ConnectChromeCast(self.ConnectedChromecasts)

        # Check if devices need to be created
        createDevices(self.ConnectedChromecasts)

        return True

    def onHeartbeat(self):
        RecheckNeeded=False
        self.heartbeatcounter += 1

        for ChromecastName in self.ConnectedChromecasts:
            #Check if chromecast is already connected
            if self.ConnectedChromecasts[ChromecastName][1] == "":
                RecheckNeeded=True

        if RecheckNeeded==True:
            q = Queue()
            p = Process(target=ScanForChromecasts, args=(q,self.ConnectedChromecasts,))
            p.start()
            self.Recheck=q.get()
            p.terminate()
            if self.Recheck == True:
                self.ConnectedChromecasts=ConnectChromeCast(self.ConnectedChromecasts)

    def onCommand(self, Unit, Command, Level, Hue):
        #Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

        #get first number of the Unit
        if len(str(Unit))==1:
            ChromecastID=0
        else:
            ChromecastID=int(str(Unit)[:1])
        #Find the corresponding chromecast
        Chromecast=next(Chromecast for Chromecast in self.ConnectedChromecasts if self.ConnectedChromecasts[Chromecast][0] == ChromecastID)


        if self.ConnectedChromecasts[Chromecast][1] == "":
            Domoticz.Error("Chromecast "+Chromecast+" is not connected!")
        else:
            cc=self.ConnectedChromecasts[Chromecast][1]
            if Unit-10*ChromecastID == 1:
                if Level == 10:
                    Domoticz.Log("Start playing on chromecast")
                    cc.media_controller.play()
                elif Level == 20:
                    Domoticz.Log("Pausing chromecast")
                    cc.media_controller.pause()
                elif Level == 30:
                    Domoticz.Log("Killing "+self.chromecast.app_display_name)
                    cc.quit_app()
            elif Unit-10*ChromecastID == 2:
                vl = float(Level)/100
                cc.set_volume(vl)
            elif Unit-10*ChromecastID == 4:
                if Level == 30:
                    Domoticz.Log("Starting Youtube on chromecast")
                    yt = YouTubeController()
                    cc.register_handler(yt)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

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

def createDevices(ConnectedChromecasts):
    for Chromecast in ConnectedChromecasts:
        x=ConnectedChromecasts[Chromecast][0]*10
        if x+1 not in Devices:
            OPTIONS1 =  {   "LevelActions"  : "|||||",
                            "LevelNames"    : "Off|Play|Pause|Stop",
                            "LevelOffHidden": "true",
                            "SelectorStyle" : "0"
                        }
            Domoticz.Log("Created 'Status' device for chromecast "+Chromecast)
            Domoticz.Device(Name="Control-"+Chromecast, Unit=x+1, TypeName="Selector Switch", Switchtype=18, Options=OPTIONS1, Used=1).Create()
            UpdateImage(x+1, 'ChromecastLogo')

        if x+2 not in Devices:
            Domoticz.Log("Created 'Volume' device for chromecast "+Chromecast)
            Domoticz.Device(Name="Volume-"+Chromecast, Unit=x+2, Type=244, Subtype=73, Switchtype=7, Used=1).Create()
            UpdateImage(x+2, 'ChromecastLogo')

        if x+3 not in Devices:
            Domoticz.Log("Created 'Title' device for chromecast "+Chromecast)
            Domoticz.Device(Name="Title-"+Chromecast, Unit=x+3, Type=243, Subtype=19, Used=1).Create()
            UpdateImage(x+3, 'ChromecastLogo')

        if x+4 not in Devices:
            OPTIONS4 =  {   "LevelActions"  : "|||||",
                            "LevelNames"    : "Off|Spotify|Netflix|Youtube|Other",
                            "LevelOffHidden": "true",
                            "SelectorStyle" : "0"
                        }
            Domoticz.Log("Created 'App' device for chromecast "+Chromecast)
            Domoticz.Device(Name="App name-"+Chromecast, Unit=x+4, TypeName="Selector Switch", Switchtype=18, Options=OPTIONS4, Used=1).Create()
            UpdateImage(x+4, 'ChromecastLogo')

    Domoticz.Log("Devices check done")
    return

# Synchronise images to match parameter in hardware page
def UpdateImage(Unit, Logo):
    if Unit in Devices and Logo in Images:
        if Devices[Unit].Image != Images[Logo].ID:
            Domoticz.Log("Device Image update: 'Chromecast', Currently " + str(Devices[Unit].Image) + ", should be " + str(Images[Logo].ID))
            Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=str(Devices[Unit].sValue), Image=Images[Logo].ID)
    return

def ScanForChromecasts(q,ConnectedChromecasts):
    Domoticz.Status("Checking for available chromecasts")
    try:
        chromecasts = pychromecast.get_chromecasts()
    except Exception as e:
        senderror(e)

    #Check if there any non-connected chromecast available
    if len(chromecasts) != 0:
        Recheck=False
        for ChromecastName in ConnectedChromecasts:
            #Check if chrmecast is already connected
            if ConnectedChromecasts[ChromecastName][1] == "":
                #Try to find the chromecast in the available chromecasts
                try:
                    #Create a chromecast instance.
                    cc=next(cc for cc in chromecasts if cc.device.friendly_name == ChromecastName)
                    Recheck=True
                except Exception as e:
                    pass
    q.put(Recheck)

def ConnectChromeCast(ConnectedChromecasts):
    Domoticz.Status("Checking for available chromecasts")
    try:
        chromecasts = pychromecast.get_chromecasts()
        if len(chromecasts) != 0:
            Names="Found these chromecasts: "
            for chromecast in chromecasts:
                if Names != "Found these chromecasts: ":
                    Names+=", "
                Names+=chromecast.device.friendly_name
            Domoticz.Log(Names)
        else:
            Domoticz.Status("No casting devices found, make sure they are online.")
    except Exception as e:
        senderror(e)

    #Check if there any non-connected chromecast available
    if len(chromecasts) != 0:
        for ChromecastName in ConnectedChromecasts:
            #Check if chrmecast is already connected
            if ConnectedChromecasts[ChromecastName][1] == "":
                #Try to find the chromecast in the available chromecasts
                try:
                    #Create a chromecast instance.
                    cc=next(cc for cc in chromecasts if cc.device.friendly_name == ChromecastName)
                    ConnectedChromecasts[ChromecastName][1]=cc
                    Domoticz.Status("Connected to " + ChromecastName)
                    startListening(cc)
                except StopIteration:
                    Domoticz.Status("Could not connect to "+ChromecastName)
                except Exception as e:
                    senderror(e)
            else:
                Domoticz.Log("Already connected to "+ChromecastName)

    return ConnectedChromecasts

def startListening(chromecast):
    Domoticz.Log("Registering listeners for " + chromecast.name)
    listenerCast = StatusListener(chromecast.name, chromecast)
    chromecast.register_status_listener(listenerCast)

    listenerMedia = StatusMediaListener(chromecast.name, chromecast)
    chromecast.media_controller.register_status_listener(listenerMedia)

    Domoticz.Log("Done registering listeners for "+ chromecast.name)

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