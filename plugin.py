#
# Author: Tsjippy
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="1.1.5" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://github.com/Tsjippy/ChromecastPlugin/">
    <description>
        <h2>Chromecast</h2><br/>
        This plugin adds devices and an user variable to Domoticz to control your chromecasts, and to retrieve its current app, title, volume and playing mode.<br/>
        Every chromecast gets its own set of devices.<br/><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Pause, Play or stop the app on the chromecast.</li>
            <li>See current connected app, title and playing mode.</li>
            <li>See or set the volume on the chromecast.</li>
            <li>Use a variable as an input for text to be spoken on the chromecast.</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Switch device - Playing mode</li>
            <li>Switch device - Connected app</li>
            <li>Volume device - See or adjust the current volume</li>
            <li>Text device - See current title</li>
            <li>Variable - Input field for text to be spoken on the chromecast</li> 
        </ul>
        <h3>Configuration</h3>
        Fill in the name(s) of your chromecast(s). In case of multiple sepereate them with a comma.<br/>
        Fill in a directory to be used as downloads location for text.mp3, non existing directories will get created.<br/>
        Fill in a port on which the files in the directory will be available.<br/>
        Fill in the languague in which the text will be given.<br/><br/>
    </description>
    <params>
        <param field="Mode1" label="Chromecast name(s)" width="600px" required="true"/>
        <param field="Mode2" label="Directory for message files" width="400px" required="true" default="/tmp/"/>
        <param field="Mode3" label="Port for filesharing" width="50px" required="true" default="8000"/>
        <param field="Mode4" label="Message language" width="50px" required="true" default="en-US"/>
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
import requests
import socket
import http.server
import socketserver
import os
import time
import pychromecast
from pychromecast.controllers.youtube import YouTubeController
from multiprocessing import Process, Queue
from mutagen.mp3 import MP3

try:
	import Domoticz
	debug = False
except ImportError:
	import fakeDomoticz as Domoticz
	debug = True

#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
	def __init__(self, name, cast):
		self.name = name
		self.cast = cast
		self.Appname =""
		self.Volume =0
		self.ChromecastID =_plugin.ConnectedChromecasts[self.name][0]

	def new_cast_status(self, status):
		#Domoticz.Status(str(status))

		if self.Appname != str(status.display_name):
			self.Appname = str(status.display_name)
			DeviceID=10*self.ChromecastID+4
			
			Domoticz.Log("The app of "+self.name+" has changed to "+self.Appname)
			
			if str(self.Appname) == "Spotify":
				Level=10
			elif str(self.Appname) == "Netflix":
				Level=20
			elif str(self.Appname) == "YouTube":
				Level=30
			elif str(self.Appname) == "Default Media Receiver":
				Level=40
			elif str(self.Appname) == "Backdrop" or str(self.Appname) == "None":
				Level=0
				Domoticz.Log("Will set the domoitcz devices to off.")
				#Control
				AppDeviceID=10*self.ChromecastID+1
				UpdateDevice(AppDeviceID,0,0)
				#Volume
				AppDeviceID=10*self.ChromecastID+2
				UpdateDevice(AppDeviceID,2,0)
				#Title
				AppDeviceID=10*self.ChromecastID+3
				UpdateDevice(AppDeviceID,0,"")
			else:
				Level=40
			UpdateDevice(DeviceID,Level,Level)

		if self.Volume != status.volume_level:
			self.Volume = status.volume_level
			DeviceID=10*self.ChromecastID+2
			Volume = int(self.Volume*100)
			Domoticz.Log("Updated volume to "+str(Volume))
			UpdateDevice(DeviceID,2,Volume)

class StatusMediaListener:
	def __init__(self, name, cast):
		self.name = name
		self.cast= cast
		self.Mode=""
		self.Title=""
		self.ChromecastID =_plugin.ConnectedChromecasts[self.name][0]

	def new_media_status(self, status):
		if self.Mode != status.player_state and status.player_state != "IDLE" and status.player_state != "BUFFERING":
			self.Mode = status.player_state
			DeviceID=10*self.ChromecastID+1
			Domoticz.Log("The playing mode of "+self.name+" has changed to "+self.Mode)

			if self.Mode == "PLAYING":
				level=10
			elif self.Mode == "PAUSED":
				level=20
			else:
				level=0

			UpdateDevice(DeviceID,level,level)

		if self.Title != status.title:
			self.Title = status.title
			DeviceID=10*self.ChromecastID+3
			Domoticz.Log("The title of "+self.name+" has changed to  "+self.Title)
			UpdateDevice(DeviceID,0,self.Title)

class BasePlugin:
	enabled = False
	def __init__(self):
		self.url= "http://127.0.0.1:8080"
		self.getvariableurl = self.url+"/json.htm?type=command&param=getuservariable&idx="

		self.StatusOptions=  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off|Play|Pause|Stop",
		"LevelOffHidden": "true",
		"SelectorStyle" : "0"
		}

		self.AppOptions =  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off|Spotify|Netflix|Youtube|Other",
		"LevelOffHidden": "true",
		"SelectorStyle" : "0"
		}

	def onStart(self):
		self.Filelocation=Parameters["Mode2"]
		self.Port = int(Parameters["Mode3"])
		self.Languague = Parameters["Mode4"]
		self.ip=get_ip()
		self.error=False
		octet2=self.ip.split(".")
		octet2=octet2[0]+"."+octet2[1]
		try:
			if Settings["WebUserName"] != "" and "127.0" not in Settings["WebLocalNetworks"] and octet2 not in Settings["WebLocalNetworks"]:
				Domoticz.Error("You have set a password, but have not excluded your local ip. Please do so, then restart domoticz.")
				self.error=True
		except:
			pass
		
		if self.error==False:
			#Create temppath if it does not exist
			if not os.path.isdir(self.Filelocation):
				Domoticz.Status("Created folder "+self.Filelocation)
				os.makedirs(self.Filelocation)

			# Check if images are in database
			Domoticz.Status("Checking if images are loaded")
			if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()

			if Parameters["Mode6"]=="Debug":
				DumpConfigToLog()

			Domoticz.Status("Starting up")

			#ConnectedChromecasts[Chromecastname] has 3 values in the end: index, chromecast object, and variable IDX
			self.ConnectedChromecasts={}
			for i, chromecastname in enumerate(Parameters["Mode1"].split(",")): 
				self.ConnectedChromecasts[chromecastname.strip()]=[i,""]

			self.ConnectedChromecasts=ConnectChromeCast(self.ConnectedChromecasts)

			if Settings["AcceptNewHardware"] != "1":
				if len(Devices) < len(self.ConnectedChromecasts)*4:
					Domoticz.Error("'Accept new Hardware Devices' is not enabled, please enable it to allow the creation of new devices. Then restart Domoticz.")
					self.error=True
			else:
				# Check if devices need to be created
				createDevices(self.ConnectedChromecasts)

				#Get variables
				self.VariablesIDX=(requests.get(url=self.url+"/json.htm?type=command&param=getuservariables").json())['result']

				#Retrieve the Domoticz IDX of the variables
				for chromecast in self.ConnectedChromecasts:
					try:
						variable=next(var for var in self.VariablesIDX if var["Name"]==chromecast)
						self.ConnectedChromecasts[chromecast]+=[variable["idx"]]
					except StopIteration:
						Domoticz.Error("Somehow the uservariable for "+chromecast+" does not exist")

				#Start FileServer
				Domoticz.Log("Local ip address is "+self.ip)
				fileserver()

		return True

	def onHeartbeat(self):
		if self.error == False:
			RecheckNeeded=False

			for ChromecastName in self.ConnectedChromecasts:

				#Check if chromecast is already connected
				if self.ConnectedChromecasts[ChromecastName][1] == "":
					RecheckNeeded=True
				elif self.ConnectedChromecasts[ChromecastName][1].media_controller.status.player_state == "UNKNOWN":
					DeviceID=10*self.ConnectedChromecasts[ChromecastName][0]+1
					#UpdateDevice(DeviceID,0,0)

				#Check if text needs to be spoken
				try:
					Text = requests.get(url=self.getvariableurl+self.ConnectedChromecasts[ChromecastName][2]).json()['result'][0]['Value']
					if Text != "":
						#Reset the variable to empty
						requests.get(url=self.url+"/json.htm?type=command&param=updateuservariable&vname="+ChromecastName+"&vtype=2&vvalue=")
						if self.ConnectedChromecasts[ChromecastName][1] != "":
							#Create mp3
							os.system('curl -s -G "http://translate.google.com/translate_tts" --data "ie=UTF-8&total=1&idx=0&client=tw-ob&&tl='+self.Languague+'" --data-urlencode "q='+Text+'" -A "Mozilla" --compressed -o '+self.Filelocation+'/message.mp3')
							Domoticz.Log('Will pronounce "'+Text+'" on chromecast '+ChromecastName)
							cc=self.ConnectedChromecasts[ChromecastName][1]
							mc=cc.media_controller
							#Play on chromecast
							mc.play_media('http://'+str(self.ip)+':'+str(self.Port)+'/message.mp3', 'music/mp3')
							time.sleep((MP3(self.Filelocation+'/message.mp3')).info.length)
							cc.quit_app()
							Domoticz.Log("Message is played.")
						else:
							Domoticz.Error("Cannot play '"+Text+"' on '"+ChromecastName+"' as the chromecast is not connected")
				except Exception as e:
					senderror(e)

			if RecheckNeeded==True:
				#Check if a chromecast is available in a seperate process.
				#If available connect to it in this process.
				q = Queue()
				p = Process(target=ScanForChromecasts, args=(q,self.ConnectedChromecasts,))
				p.start()
				self.Recheck=q.get()
				p.terminate()

				if self.Recheck == True:
					Domoticz.Log("Connecting to available chromecasts")
					self.ConnectedChromecasts=ConnectChromeCast(self.ConnectedChromecasts)

	def onCommand(self, Unit, Command, Level, Hue):
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
					Domoticz.Log("Killing "+cc.app_display_name)
					cc.quit_app()
				else:
					Domoticz.Log("Level is "+Level+" What should I do with it?")
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
	global _plugin
	for Chromecast in ConnectedChromecasts:
		#Check if variable needs to be created
		try:
			result=requests.get(url=_plugin.url+"/json.htm?type=command&param=saveuservariable&vname="+Chromecast+"&vtype=2&vvalue=").json()["status"]
		except Exception as e:
			senderror(e)

		if result=="OK":
			Domoticz.Log("Created uservariable for '"+Chromecast+"'")
		elif result=="Variable name already exists!":
			Domoticz.Log("Variable for "+Chromecast+" already exists.")
		else:
			Domoticz.Error("Could not create '"+Chromecast+"', result was "+result)

		x=ConnectedChromecasts[Chromecast][0]*10
		if x+1 not in Devices:
			Domoticz.Log("Created 'Status' device for chromecast "+Chromecast)
			Domoticz.Device(Name="Control-"+Chromecast, Unit=x+1, TypeName="Selector Switch", Switchtype=18, Options=_plugin.StatusOptions, Used=1).Create()
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
			Domoticz.Log("Created 'App' device for chromecast "+Chromecast)
			Domoticz.Device(Name="App name-"+Chromecast, Unit=x+4, TypeName="Selector Switch", Switchtype=18, Options=_plugin.AppOptions, Used=1).Create()
			UpdateImage(x+4, 'ChromecastLogo')

		UpdateDevice(x+1,0,0)
		UpdateDevice(x+2,0,0)
		UpdateDevice(x+3,0,"")
		UpdateDevice(x+4,2,0)

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
	Recheck=False
	try:
		chromecasts = pychromecast.get_chromecasts()
	except Exception as e:
		pass

	#Check if there any non-connected chromecast available
	if len(chromecasts) != 0:
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

def get_ip():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		# doesn't even have to be reachable
		s.connect(('10.255.255.255', 1))
		IP = s.getsockname()[0]
	except:
		IP = '127.0.0.1'
	finally:
		s.close()
	return IP

def fileserver():
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		Port = int(Parameters["Mode3"])
		Domoticz.Log("Starting file server on port "+str(Port))
		Filelocation=Parameters["Mode2"]
		os.chdir(Filelocation)
		Handler = http.server.SimpleHTTPRequestHandler
		httpd = socketserver.TCPServer(("", Port), Handler)
		p = Process(target=httpd.serve_forever)
		p.deamon=True
		p.start()
		Domoticz.Log("Files in the '"+Filelocation+"' directory are now available on port "+str(Port))
	except Exception as e:
		senderror(e)

	if debug==True:
		ConnectChromeCast()
