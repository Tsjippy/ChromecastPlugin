#
# Author: Tsjippy
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="3.3.0" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://github.com/Tsjippy/ChromecastPlugin/">
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
		<param field="Mode5" label="Domoticz url and port" width="200px" required="true" default="http://127.0.0.1:8080"/>
        <param field="Mode6" label="Adjust Volume" width="100px">
            <options>
                <option label="True" value="True" default="true" />
                <option label="False" value="False"/>
            </options>
        </param>
    </params>
</plugin>
"""
#############################################################################
#                      Imports                                              #
#############################################################################
try:
	import Domoticz
	debug = False
except ImportError:
	import fakeDomoticz as Domoticz
	debug = True
import sys
import os

major,minor,x,y,z = sys.version_info
if (os.name == 'nt'):
    Domoticz.Error("Windows is currently not supported.")
else:
    sys.path.append('/usr/lib/python3/dist-packages')
    sys.path.append('/usr/local/lib/python'+str(major)+'.'+str(minor)+'/dist-packages')

import queue
import requests
import socket
import http.server
import socketserver
import errno
import time
import datetime
import pychromecast
from pychromecast.controllers.youtube import YouTubeController
from multiprocessing import Process, Queue
	
#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
	def __init__(self, cast):
		try:
			self.name = cast.name
			self.cast = cast
			self.ChromecastId =_plugin.ConnectedChromecasts[self.name][0]
			self.AppDeviceId = 10*self.ChromecastId+4
			self.VolumeDeviceId = 10*self.ChromecastId+2
			self.appLevels={}
			self.appLevels["Backdrop"] = 0
			self.appLevels["None"] = 0

			if cast.status == None or cast.status.display_name == None :
				self.Appname = "None"
				self.Volume = ""
			else:
				self.Appname = cast.status.display_name

				#The app index is not yet stored in the array
				if not self.Appname in self.appLevels:
					self.new_app()
				
				UpdateDevice(self.AppDeviceId,self.appLevels[self.Appname],self.appLevels[self.Appname])

				self.Volume = cast.status.volume_level
				Volume = int(self.Volume*100)
				UpdateDevice(self.VolumeDeviceId,2,Volume)
		except Exception as e:
			senderror(e)

	def new_cast_status(self, status):
		try:
			if self.Appname != str(status.display_name):
				self.Appname = str(status.display_name)
				Domoticz.Log("The app of '"+self.name+"' has changed to '"+self.Appname+"'")
				
				if not self.Appname in self.appLevels:
					self.new_app()
				elif self.appLevels[self.Appname] == 0:
					Domoticz.Log("Will set the domoticz devices to off.")
					#Control
					AppDeviceID=10*self.ChromecastId+1
					UpdateDevice(AppDeviceID,0,0)
					#Title
					AppDeviceID=10*self.ChromecastId+3
					UpdateDevice(AppDeviceID,0,"")

				UpdateDevice(self.AppDeviceId,self.appLevels[self.Appname],self.appLevels[self.Appname])

			if self.Volume != status.volume_level:
				self.Volume = status.volume_level
				Volume = int(self.Volume*100)
				Domoticz.Log("Updated volume to "+str(Volume))
				UpdateDevice(self.VolumeDeviceId,2,Volume)
		except Exception as e:
			senderror(e)

	def new_app(self):
		try:
			#The appname is not yet an option in the domoticz device
			if Devices[self.AppDeviceId].Options['LevelNames'].find(self.Appname) == -1:
				Domoticz.Log("Adding '"+self.Appname+"' to app device for chromecast '"+self.name+"'")
				#Add the option to the domoticz device
				_plugin.AppOptions['LevelNames']=Devices[self.AppDeviceId].Options['LevelNames']+"|"+self.Appname
				index = len(Devices[self.AppDeviceId].Options['LevelNames'].split("|"))*10
				Devices[self.AppDeviceId].Update(index, str(index),Options = _plugin.AppOptions)

			for i, level in enumerate(Devices[self.AppDeviceId].Options['LevelNames'].split("|")):
				if level == self.Appname:
					self.appLevels[self.Appname] = i*10
					break

			return
		except Exception as e:
			senderror(e)

class ConnectionListener:
	def __init__(self, cast):
		self.cast = cast
		self.name = cast.name
		self.counter = 0

	def new_connection_status(self, new_status):
		try:
			global _plugin
			# new_status.status will be one of the CONNECTION_STATUS_ constants defined in the
			# socket_client module.
			if new_status.status == "CONNECTED":
				Domoticz.Status("Succesfully connected to '"+self.name+"'")
				if self.cast.status.volume_level == 1:
					self.cast.set_volume(0.5)
				Domoticz.Status("Volume is '"+str(self.cast.status.volume_level*100)+"%'")
				_plugin.ConnectedChromecasts[self.name][3]=new_status.status
			elif new_status.status == 'CONNECTING':
				if self.counter == 0:
					Domoticz.Log("Trying to connect to '"+self.name+"'")
			elif new_status.status == 'FAILED':
				if self.counter == 0:
					Domoticz.Log("Failed to connect to '"+self.name+"'")
				elif self.counter == 10:
					self.cast.disconnect()
					Domoticz.Status("Disconnecting '"+self.name+"' as reconnecting did not succeed for 10 times.")
					self.counter = -1
				self.counter += 1
			elif new_status.status == 'LOST':
				Domoticz.Error("Connection with '"+self.name+ "'' is lost.")
				_plugin.ConnectedChromecasts[self.name][3]=new_status.status
			else:
				Domoticz.Error("Status of '"+self.name+"'' is changed to "+str(new_status))
		except Exception as e:
			senderror(e)
		
class StatusMediaListener:
	def __init__(self, cast):
		self.name = cast.name
		self.cast= cast
		self.Mode=""
		self.Title=""
		self.ChromecastId =_plugin.ConnectedChromecasts[self.name][0]
		self.ModeDeviceId = 10*self.ChromecastId+1
		self.TitleDeviceId = 10*self.ChromecastId+3
		self.ModeLevels={}
		self.ModeLevels["PLAYING"] = 10
		self.ModeLevels["PAUSED"] = 20

		if cast.status != None and cast.status.display_name != None and cast.status.display_name !='Backdrop':
			self.Title=""
			self.Mode = self.cast.media_controller.status.player_state
			try:
				level=self.ModeLevels[self.Mode]
			except:
				level=0
			UpdateDevice(self.ModeDeviceId,level,level)

			self.Title = self.cast.media_controller.status.title
			UpdateDevice(self.TitleDeviceId,0,self.Title)

	def new_media_status(self, status):
		try:
			if self.Mode != status.player_state and status.player_state != "IDLE" and status.player_state != "BUFFERING":
				self.Mode = status.player_state
				Domoticz.Log("The playing mode of "+self.name+" has changed to "+self.Mode)

				try:
					level=self.ModeLevels[self.Mode]
				except:
					level=0
				UpdateDevice(self.ModeDeviceId,level,level)

			if self.Title != status.title and status.title != None:
				self.Title = status.title
				Domoticz.Log("The title of "+self.name+" has changed to  "+self.Title)
				UpdateDevice(self.TitleDeviceId,0,self.Title)
		except Exception as e:
			senderror(e)

class BasePlugin:
	enabled = False
	def __init__(self):
		self.StatusOptions=  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off|Play|Pause|Stop",
		"LevelOffHidden": "true",
		"SelectorStyle" : "0"
		}

		self.AppOptions =  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off",
		"LevelOffHidden": "false",
		"SelectorStyle" : "1"
		}

	def onStart(self):

		try:
			self.Filelocation=Parameters["Mode2"]
			self.Port = int(Parameters["Mode3"])
			self.Languague = Parameters["Mode4"]
			self.url = Parameters["Mode5"]
			if self.url == "":
				self.url="http://127.0.0.1:8080"
			self.getvariableurl = self.url+"/json.htm?type=command&param=getuservariable&idx="
			self.ip=get_ip()
			self.error=False
			octet2=self.ip.split(".")
			octet2=octet2[0]+"."+octet2[1]
		except Exception as e:
			senderror(e)

		try:
			if Settings["WebUserName"] != "" and Settings["WebUserName"] != str(0) and "127.0" not in Settings["WebLocalNetworks"] and octet2 not in Settings["WebLocalNetworks"]:
				Domoticz.Error("You have set a password, but have not excluded your local ip. Please do so, then restart domoticz.")
				self.error=True
		except:
			pass
		
		try:
			if self.error==False:
				#Create temppath if it does not exist
				if not os.path.isdir(self.Filelocation):
					Domoticz.Status("Created folder "+self.Filelocation)
					os.makedirs(self.Filelocation, mode=0o777)
					
				# Check if images are in database
				Domoticz.Status("Checking if images are loaded")
				if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()

				DumpConfigToLog()

				Domoticz.Status("Starting up")

			#ConnectedChromecasts[Chromecastname] has 5 values in the end: index, chromecast object, variable IDX, chromecast status and hours since last connection
			self.ConnectedChromecasts={}
			for i, chromecastname in enumerate(Parameters["Mode1"].split(",")):
				if chromecastname != "":
					self.ConnectedChromecasts[chromecastname.strip()]=[i,"","","disconnected",0]
			
			if Settings["AcceptNewHardware"] != "1":
				if len(Devices) != len(self.ConnectedChromecasts)*4:
					Domoticz.Error("'Accept new Hardware Devices' is not enabled, please enable it to allow the creation of new devices. Then restart Domoticz.")
					self.error=True
			else:
				# Check if devices need to be deleted
				self.updateDevices()
				
				# Check if devices need to be created
				createDevices(self.ConnectedChromecasts)

				getVariables()

				#Start FileServer
				Domoticz.Log("Local ip address is "+self.ip)
				self.fileserver()


			self.ConnectChromeCast()
		except Exception as e:
			senderror(e)

	def onHeartbeat(self):
		if self.error == False:
			RecheckNeeded=False
			for ChromecastName in self.ConnectedChromecasts:
				cc=self.ConnectedChromecasts[ChromecastName][1]
				#Check if chromecast is already connected
				if cc == "":
					RecheckNeeded=True

				#Check if text needs to be spoken
				try:
					Text = requests.get(url=self.getvariableurl+self.ConnectedChromecasts[ChromecastName][2]).json()['result'][0]['Value']
				except:
					Domoticz.Error(self.getvariableurl+self.ConnectedChromecasts[ChromecastName][2] + " did not return any results. ("+str(self.ConnectedChromecasts[ChromecastName])+")")
					Text = ""

				try:
					if Text != "" and cc != "":
						#Reset the variable to empty
						requests.get(url=self.url+"/json.htm?type=command&param=updateuservariable&vname="+ChromecastName+"&vtype=2&vvalue=")
						if self.ConnectedChromecasts[ChromecastName][3] == "CONNECTED":
							#Create mp3
							os.system('curl -s -G "http://translate.google.com/translate_tts" --data "ie=UTF-8&total=1&idx=0&client=tw-ob&&tl='+self.Languague+'" --data-urlencode "q='+Text+'" -A "Mozilla" --compressed -o '+self.Filelocation+'/message.mp3')
							
							Domoticz.Status('Will pronounce "'+Text+'" on chromecast '+ChromecastName)
							mc=cc.media_controller
							
							#Store YouTube session
							if cc.status.display_name is not None and cc.status.display_name=="YouTube":
								mc.pause()
								while mc.status.player_state != 'PAUSED':
									time.sleep(0.1)
								currenttime=mc.status.current_time
								videoid=mc.status.content_id
								previousapp=True
							else:
								previousapp=False
							
							if Parameters["Mode6"]=="True":
								previousvolume=int(cc.status.volume_level*100)
								Domoticz.Status("Current volume is "+str(previousvolume))
								cc.quit_app()
								time.sleep(0.5)
								Domoticz.Log("Maximizing volume")
								cc.set_volume(1)
							else:
								cc.quit_app()
							
							#Play on chromecast
							mc.play_media('http://'+str(self.ip)+':'+str(self.Port)+'/message.mp3', 'music/mp3')
							while mc.status.player_state != 'PLAYING' or cc.status.display_name != 'Default Media Receiver':
								#Domoticz.Log("Sleeping while waiting for playing")
								time.sleep(0.1)
							while mc.status.player_state == 'PLAYING':
								#Domoticz.Log("Sleeping while playing")
								time.sleep(0.1)

							Domoticz.Log("Message is played.")
							
							if Parameters["Mode6"]=="True" and previousvolume != 0 and previousvolume != 100:
								#Reset Volume
								Domoticz.Log("Restoring original volume of "+str(previousvolume))
								cc.set_volume(previousvolume/100)
							
							#Restart Youtube session
							if previousapp==True:
								Domoticz.Status("Restarting video with id:"+str(videoid)+" on YouTube.")
								uri=cc.uri
								q = Queue()
								p = Process(target=RestartYoutube, args=(q,uri,videoid,currenttime))
								p.deamon=True
								p.start()
								Domoticz.Log(q.get())
								p.terminate()
							else:
								cc.quit_app()
						else:
							Domoticz.Error("Cannot play '"+Text+"' on '"+ChromecastName+"' as the chromecast is not connected.")
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
					self.ConnectChromeCast()

	def onCommand(self, Unit, Command, Level, Hue):
		#get first number of the Unit
		if len(str(Unit)) == 1:
			ChromecastId=0
		else:
			ChromecastId=int(str(Unit)[-2])

		#Find the corresponding chromecast
		Chromecast=next(Chromecast for Chromecast in self.ConnectedChromecasts if self.ConnectedChromecasts[Chromecast][0] == ChromecastId)

		if self.ConnectedChromecasts[Chromecast][3] != "CONNECTED":
			Domoticz.Error("Chromecast '"+Chromecast+"' is not connected, so I cannot issue a command to it. Reconnect '"+Chromecast+"' and try again.")
			self.ConnectedChromecasts[Chromecast][1].disconnect()
		else:
			try:
				cc=self.ConnectedChromecasts[Chromecast][1]
				if cc != "" and cc.status != None:
					if Unit % 10 == 1:
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
					elif Unit % 10 == 2:
						vl = float(Level)/100
						cc.set_volume(vl)
					elif Unit % 10 == 4:
						if Level == 30:
							Domoticz.Log("Starting Youtube on chromecast")
							yt = YouTubeController()
							cc.register_handler(yt)
				elif (cc.status == None):
					Domoticz.Status("Cannot issue a command to '"+Chromecast+"' when no app is connected.")
				else:
					Domoticz.Error("Cannot issue the command as the Chromecast '"+Chromecast+"' is not connected.")
			except Exception as e:
				senderror(e)

	def onStop(self):
		global p
		for chromecast in self.ConnectedChromecasts:
			if self.ConnectedChromecasts[chromecast][1] != "":
				cc=self.ConnectedChromecasts[chromecast][1]
				Domoticz.Status("Disconnected from "+cc.name)
				cc.disconnect()

	def ConnectChromeCast(self):
		Domoticz.Status("Checking for available chromecasts")
		try:
			self.chromecasts = pychromecast.get_chromecasts()
			if len(self.chromecasts) != 0:
				Names="Found these chromecasts: "
				for chromecast in self.chromecasts:
					if Names != "Found these chromecasts: ":
						Names+=", "
					Names+="'"+chromecast.device.friendly_name+"'"

				Domoticz.Log(Names)
			else:
				Domoticz.Status("No casting devices found, make sure they are online.")
		except Exception as e:
			senderror(e)

	    #Check if there any non-connected chromecast available
		if len(self.chromecasts) != 0:
			for chromecast in self.chromecasts:
				try:
					#Check if chromecast is already connected
					if self.ConnectedChromecasts[chromecast.name][1] == "":
						if chromecast.status is not None and chromecast.status.volume_level == 1:
							chromecast.set_volume(0.5)
							Domoticz.Status("Set volume of '" + chromecast.name +"' to 50%")
						self.ConnectedChromecasts[chromecast.name][1]=chromecast
						Domoticz.Status("Connected to '" + chromecast.name+"'")
						self.ConnectedChromecasts[chromecast.name][3]="CONNECTED"
						self.startListening(chromecast)
				except KeyError:
					#Disconnect from the chromecast as we don't need it
					chromecast.disconnect()
				except StopIteration:
					#Chromecast is currently not available
					Domoticz.Status("Could not connect to '"+chromecast.name+"'")
				except Exception as e:
					senderror(e)

	def startListening(self,chromecast):
		Domoticz.Log("Registering listeners for '" + chromecast.name+"'")
		listenerCast = StatusListener(chromecast)
		chromecast.register_status_listener(listenerCast)

		listenerMedia = StatusMediaListener(chromecast)
		chromecast.media_controller.register_status_listener(listenerMedia)
		
		connectioncast=ConnectionListener(chromecast)
		chromecast.register_connection_listener(connectioncast)

		Domoticz.Log("Done registering listeners for '"+ chromecast.name+"'")
		
	def fileserver(self):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			Port = int(Parameters["Mode3"])
			Domoticz.Log("Starting file server on port "+str(Port))
			Filelocation=Parameters["Mode2"]
			os.chdir(Filelocation)
			Handler = http.server.SimpleHTTPRequestHandler
			socketserver.TCPServer.allow_reuse_address = True
			server = socketserver.TCPServer(("", Port), Handler)
			p = Process(target=server.serve_forever)
			p.deamon = True
			p.start()
			Domoticz.Log("Files in the '"+Filelocation+"' directory are now available on port "+str(Port))
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
				Domoticz.Log("Port "+str(Port)+" is already in use")
			else:
				senderror(e)

	def updateDevices(self):
		try:
			result=requests.get(self.url+"/json.htm?type=command&param=getuservariables").json()
			result['status']
			VariablesIDX=result.get('result')
		except:
			Domoticz.Error("Could not get all variables. Used this url: "+self.url+"/json.htm?type=command&param=getuservariables")
			self.error=True

		try:
			#Find the device id's
			DeviceList=[]

			for deviceid in Devices:
				if deviceid % 10 == 1:
					DeviceList+=[deviceid]

			for deviceid in DeviceList:
				if len(str(deviceid)) == 1:
					ChromecastId=0
				else:
					ChromecastId=int(str(deviceid)[-2])

				#Find the chromecast name in the device name
				ChromecastName = ""
				for Name in self.ConnectedChromecasts:
					if Name in Devices[deviceid].Name:
						ChromecastName = Name

				#Referred chromecast does no longer exist
				if ChromecastName == "":
					ChromecastName = Devices[deviceid].Name.split("-")[-1]
					try:
						if VariablesIDX != None:
							idx=next(var for var in VariablesIDX if var["Name"]==ChromecastName)
							result=requests.get(url=self.url+"/json.htm?type=command&param=deleteuservariable&idx="+idx["idx"]).json()["status"]
							if result=="OK":
								Domoticz.Log("Removed uservariable for '"+ChromecastName+"'")
							else:
								Domoticz.Error("Could not remove user variable '"+ChromecastName+"', result was '"+result+"'. URL used is "+_plugin.url+"/json.htm?type=command&param=deleteuservariable&idx="+Chromecasts[ChromecastName][2])
					except StopIteration:
						pass
					except Exception as e:
						senderror(e)

					#Delete devices
					for i in range(4):
						x=deviceid+i
						Domoticz.Log("Deleting '"+Devices[x].Name+"' with id "+str(x))
						Devices[x].Delete()
				elif self.ConnectedChromecasts.get(ChromecastName)[0] != ChromecastId:
					currentid=self.ConnectedChromecasts[ChromecastName][0]
					#Check if there is already a chromecast with this id
					try:
						Chromecast = next(Chromecast for Chromecast in self.ConnectedChromecasts if self.ConnectedChromecasts[Chromecast][0]==ChromecastId)
						self.ConnectedChromecasts[Chromecast][0] = currentid
					except StopIteration:
						pass
					except Exception as e:
						senderror(e)
					self.ConnectedChromecasts[ChromecastName][0] = ChromecastId
		except Exception as e:
			senderror(e)
		


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

def onStop():
	global _plugin
	_plugin.onStop()

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

def senderror(e):
	Domoticz.Error('Error on line {}'.format(sys.exc_info()[-1].tb_lineno)+" Error is "+str(e))
	return

def createDevices(Chromecasts):
	global _plugin
	for Chromecast in Chromecasts:
		Domoticz.Log("Checking devices for '"+Chromecast+"'")
		#Check if variable needs to be created
		try:
			result=requests.get(_plugin.url+"/json.htm?type=command&param=adduservariable&vname="+Chromecast+"&vtype=2&vvalue=").json()["status"]
			
			if result !="OK" and result != "Variable name already exists!":
				result=requests.get(_plugin.url+"/json.htm?type=command&param=saveuservariable&vname="+Chromecast+"&vtype=2&vvalue=").json()["status"]

			if result=="OK":
				Domoticz.Log("Created uservariable for '"+Chromecast+"'")
			elif result=="Variable name already exists!":
				#Domoticz.Log("Variable for "+Chromecast+" already exists.")
				pass
			else:
				Domoticz.Error("Could not create '"+Chromecast+"', result was "+result+". Url used is "+_plugin.url+"/json.htm?type=command&param=saveuservariable&vname="+Chromecast+"&vtype=2&vvalue=")

			x=Chromecasts[Chromecast][0]*10
			if x+1 not in Devices:
				Domoticz.Log("Created 'Status' device for chromecast '"+Chromecast+"'")
				Domoticz.Device(Name="Control-"+Chromecast, Unit=x+1, TypeName="Selector Switch", Switchtype=18, Options=_plugin.StatusOptions, Used=1).Create()
				UpdateImage(x+1, 'ChromecastLogo')

			if x+2 not in Devices:
				Domoticz.Log("Created 'Volume' device for chromecast '"+Chromecast+"'")
				Domoticz.Device(Name="Volume-"+Chromecast, Unit=x+2, Type=244, Subtype=73, Switchtype=7, Used=1).Create()
				UpdateImage(x+2, 'ChromecastLogo')

			if x+3 not in Devices:
				Domoticz.Log("Created 'Title' device for chromecast '"+Chromecast+"'")
				Domoticz.Device(Name="Title-"+Chromecast, Unit=x+3, Type=243, Subtype=19, Used=1).Create()
				UpdateImage(x+3, 'ChromecastLogo')

			if x+4 not in Devices:
				Domoticz.Log("Created 'App' device for chromecast '"+Chromecast+"'")
				Domoticz.Device(Name="App name-"+Chromecast, Unit=x+4, TypeName="Selector Switch", Switchtype=18, Options=_plugin.AppOptions, Used=1).Create()
				UpdateImage(x+4, 'ChromecastLogo')

		except Exception as e:
			senderror(e)

	Domoticz.Log("Devices check done")
	return

def getVariables():
	try:
		global _plugin
		#Get variables
		VariablesIDX=(requests.get(_plugin.url+"/json.htm?type=command&param=getuservariables").json())['result']

		#Retrieve the Domoticz IDX of the variables
		for chromecast in _plugin.ConnectedChromecasts:
			try:
				variable=next(var for var in VariablesIDX if var["Name"]==chromecast)
				_plugin.ConnectedChromecasts[chromecast][2]=variable["idx"]
				Domoticz.Log("Found uservariable for '"+chromecast+"'")
			except:
				Domoticz.Error("Somehow the uservariable for "+chromecast+" does not exist, please create it.")
	except Exception as e:
		senderror(e)

# Synchronise images to match parameter in hardware page
def UpdateImage(Unit, Logo):
	if Unit in Devices and Logo in Images:
		if Devices[Unit].Image != Images[Logo].ID:
			Domoticz.Log("Device Image update: 'Chromecast', Currently " + str(Devices[Unit].Image) + ", should be " + str(Images[Logo].ID))
			Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=str(Devices[Unit].sValue), Image=Images[Logo].ID)
	return

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
		
def RestartYoutube(q,uri,videoid,seektime):
	ip=uri.split(":")[0]
	port=int(uri.split(":")[1])
	cc = pychromecast.Chromecast(ip,port)
	mc=cc.media_controller
	cc.wait()
	yt = YouTubeController()
	cc.register_handler(yt)
	yt.play_video(videoid)
	mc.block_until_active()
	while mc.status.player_state != 'PLAYING':
		time.sleep(0.1)
	mc.seek(seektime)
	time.sleep(2)
	cc.disconnect()
	q.put("Done")

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
					cc=next(cc for cc in chromecasts if cc.device.friendly_name == ChromecastName)
					Recheck=True
				except Exception as e:
					pass
		for Chromecast in chromecasts:
			Chromecast.disconnect()

	q.put(Recheck)
