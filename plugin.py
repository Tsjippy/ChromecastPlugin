#
# Author: Tsjippy
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="4.5.1" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://github.com/Tsjippy/ChromecastPlugin/">
    <description>
        <h2>Chromecast</h2><br/>
        This plugin adds devices and an user variable to Domoticz to control your chromecasts, and to retrieve its current app, title, volume and playing mode.<br/>
        Every chromecast gets its own set of devices.<br/><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Pause, play or stop the app on the chromecast, or go to the previous or next track.</li>
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
        Fill in your domoticz url and port.<br/>
        Fill in the name(s) of your chromecast(s). In case of multiple sepereate them with a comma.<br/>
        Fill in a directory to be used as downloads location for text.mp3, non existing directories will get created.<br/>
        Fill in a port on which the files in the directory will be available.<br/>
        Fill in the languague in which the text will be given.<br/>
    </description>
    <params>
    	<param field="Address" 	label="Domoticz IP Address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" 	label="Domoticz Port" width="100px" required="true" default="8080"/>
        <param field="Mode1" 	label="Chromecast name(s)" width="600px" required="true"/>
        <param field="Mode2" 	label="Directory for message files" width="400px" required="true" default="/tmp/"/>
        <param field="Mode3" 	label="Port for filesharing" width="50px" required="true" default="8000"/>
        <param field="Mode4" 	label="Message language" width="50px" required="true" default="en-US"/>
        <param field="Mode6" 	label="Adjust Volume" width="100px">
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

if (os.name == 'nt'):
    Domoticz.Error("Windows is currently not supported.")

from packaging import version
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
import threading
import pip
import time
import json
if int(pip.__version__.split(".")[0])>10:
    from pip._internal.utils.misc import get_installed_distributions
else:
    from pip import get_installed_distributions

	
#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
	def __init__(self, cast):
		try:
			self.Name 					= cast.name
			self.Cast 					= cast
			self.ChromecastId 			= _plugin.ConnectedChromecasts[self.Name]["Index"]
			self.AppDeviceId 			= 10*self.ChromecastId+4
			self.VolumeDeviceId 		= 10*self.ChromecastId+2
			self.AppLevels 				= {}
			self.AppLevels["Backdrop"] 	= 0
			self.AppLevels["None"] 		= 0
			self.CastType 				= self.Cast.cast_type

			if cast.status == None or cast.status.display_name == None :
				self.Appname 			= "None"
				self.Volume 			= ""
			else:
				self.Appname 			= cast.status.display_name

				#The app index is not yet stored in the array
				if not self.Appname in self.AppLevels:
					self.new_app()
				
				UpdateDevice(self.AppDeviceId,self.AppLevels[self.Appname],self.AppLevels[self.Appname])

				self.Volume 			= cast.status.volume_level
				Volume 					= int(self.Volume*100)
				UpdateDevice(self.VolumeDeviceId,2,Volume)
		except Exception as e:
			senderror(e)

	def new_cast_status(self, status):
		try:
			if status != None and self.Appname != str(status.display_name) and (self.CastType == 'audio' or (self.CastType == 'cast' and status.display_name != None)):
				self.Appname = str(status.display_name)
				Domoticz.Log("The app of '"+self.Name+"' has changed to '"+self.Appname+"'")
				
				if not self.Appname in self.AppLevels:
					self.new_app()
				elif self.AppLevels[self.Appname] == 0:
					Domoticz.Log("Will set the domoticz devices to off, as nothing is playing.")
					#Control
					AppDeviceID=10*self.ChromecastId+1
					UpdateDevice(AppDeviceID,0,0)
					#Title
					AppDeviceID=10*self.ChromecastId+3
					UpdateDevice(AppDeviceID,0,"")

				UpdateDevice(self.AppDeviceId,self.AppLevels[self.Appname],self.AppLevels[self.Appname])

			if status != None and self.Volume != status.volume_level:
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
				Domoticz.Log("Adding '"+self.Appname+"' to app device for chromecast '"+self.Name+"'")
				#Add the option to the domoticz device
				_plugin.AppOptions['LevelNames']=Devices[self.AppDeviceId].Options['LevelNames']+"|"+self.Appname
				Index = len(Devices[self.AppDeviceId].Options['LevelNames'].split("|"))*10
				Devices[self.AppDeviceId].Update(Index, str(Index),Options = _plugin.AppOptions)

			for i, level in enumerate(Devices[self.AppDeviceId].Options['LevelNames'].split("|")):
				if level == self.Appname:
					self.AppLevels[self.Appname] = i*10
					break

			return
		except Exception as e:
			senderror(e)

class ConnectionListener:
	def __init__(self, cast):
		self.Cast = cast
		self.Name = cast.name
		self.Counter = 0

	def new_connection_status(self, new_status):
		try:
			global _plugin
			# new_status.status will be one of the CONNECTION_STATUS_ constants defined in the
			# socket_client module.
			if new_status.status == "CONNECTED":
				Domoticz.Status("Succesfully connected to '"+self.Name+"'")
				if self.Cast.status.volume_level == 1:
					self.Cast.set_volume(0.5)
				Domoticz.Status("Volume is '"+str(self.Cast.status.volume_level*100)+"%'")
				_plugin.ConnectedChromecasts[self.Name]["Status"]=new_status.status

				SetDeviceTimeOut(_plugin.ConnectedChromecasts[self.Name]["Index"],0)
			elif new_status.status == 'CONNECTING':
				if self.Counter == 0:
					Domoticz.Log("Trying to connect to '"+self.Name+"'")
			elif new_status.status == 'DISCONNECTED':
				Domoticz.Log("'"+self.Name+"' is disconnected.")
				SetDeviceTimeOut(_plugin.ConnectedChromecasts[self.Name]["Index"],1)
			elif new_status.status == 'FAILED':
				if self.Counter == 0:
					Domoticz.Log("Failed to connect to '"+self.Name+"'")
				elif self.Counter == 10:
					try:
						_plugin.ConnectedChromecasts[ChromecastName]["CC"] = ""
						self.Cast.disconnect()
					except:
						pass
					Domoticz.Status("Disconnecting '"+self.Name+"' as reconnecting did not succeed for 10 times.")
					self.Counter = -1
				self.Counter += 1
			elif new_status.status == 'LOST':
				Domoticz.Status("Connection with '"+self.Name+ "' is lost.")
				_plugin.ConnectedChromecasts[self.Name]["Status"]=new_status.status
				SetDeviceTimeOut(_plugin.ConnectedChromecasts[self.Name]["Index"],1)
			else:
				Domoticz.Error("Status of '"+self.Name+"'' is changed to "+str(new_status))
		except Exception as e:
			senderror(e)
		
class StatusMediaListener:
	def __init__(self, cast):
		self.Name 					= cast.name
		self.Cast 					= cast
		self.Mc 					= cast.media_controller
		self.Mode 					= ""
		self.Title 					= ""
		self.ChromecastId 			= _plugin.ConnectedChromecasts[self.Name]["Index"]
		self.ModeDeviceId 			= 10*self.ChromecastId+1
		self.TitleDeviceId 			= 10*self.ChromecastId+3
		self.ModeLevels 			= {}
		self.ModeLevels["PLAYING"] 	= 20
		self.ModeLevels["PAUSED"] 	= 30

		if cast.status != None and cast.status.display_name != None and cast.status.display_name !='Backdrop':
			self.Title 				= ""
			self.Mode 				= self.Cast.media_controller.status.player_state
			try:
				Level 				= self.ModeLevels[self.Mode]
			except:
				Level  				= 0
			UpdateDevice(self.ModeDeviceId,Level,Level)

			self.Title 				= self.Mc.status.title
			UpdateDevice(self.TitleDeviceId,0,self.Title)

	def new_media_status(self, status):
		try:
			global _plugin
			if _plugin.Internet == True:
				if self.Mode != status.player_state and status.player_state != "IDLE" and status.player_state != "BUFFERING":
					self.Mode = status.player_state

					Domoticz.Log("The playing mode of '"+self.Name+"' has changed to "+self.Mode)

					try:
						Level=self.ModeLevels[self.Mode]
					except:
						Level=0
					UpdateDevice(self.ModeDeviceId,Level, Level)

				if self.Title != status.title and status.title != None:
					self.Title = status.title

					if self.Cast.status.display_name == "YouTube":
						_plugin.ConnectedChromecasts[self.Name]["YouTube"]["Track"] = status.content_id

					Domoticz.Log("The title of '"+self.Name+"' has changed to  '"+self.Title+"'")
					UpdateDevice(self.TitleDeviceId,0,self.Title)
		except Exception as e:
			senderror(e)

class BasePlugin:
	enabled = False
	def __init__(self):
		self.StatusOptions=  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off|Prev|Play|Pause|Stop|Next",
		"LevelOffHidden": "true",
		"SelectorStyle" : "0"
		}

		self.AppOptions =  {   "LevelActions"  : "|||||",
		"LevelNames"    : "Off",
		"LevelOffHidden": "false",
		"SelectorStyle" : "1"
		}

		self.pFileserver	= False

	def onStart(self):
		try:
			self.Debug 					= False
			self.ChromecastNames 		= Parameters["Mode1"].split(",")
			self.Filelocation 			= Parameters["Mode2"]
			self.Port 					= int(Parameters["Mode3"])		
			self.Languague 				= Parameters["Mode4"]
			self.Url 					= "http://"+Parameters["Address"]+":"+Parameters["Port"]
			self.GetVariableUrl 		= self.Url+"/json.htm?type=command&param=getuservariable&idx="
			self.Ip 					= GetIP()
			self.Error 					= False
			Octet2 						= self.Ip.split(".")
			Octet2 						= Octet2[0]+"."+Octet2[1]
			self.Recheck 				= False
			self.q 						= Queue()
			self.q2 					= Queue()
			self.Internet 				= True 

			if self.Filelocation[-1] != "/":
				self.Filelocation += "/"
				Domoticz.Log("Added the final '/' to the directory path as you seem to have forgotten, its ok for now, but you better check your hardware settings.")
			if self.Filelocation[-1] != "/":
				self.Filelocation += "/"
				Domoticz.Log("Added the final '/' to the directory path as you seem to have forgotten, its ok for now, but you better check your hardware settings.")
		except Exception as e:
			senderror(e)

		try:
			if Settings["WebUserName"] != "" and Settings["WebUserName"] != str(0) and "127.0" not in Settings["WebLocalNetworks"] and Octet2 not in Settings["WebLocalNetworks"]:
				Domoticz.Error("You have set a password, but have not excluded your local ip. Please do so, then restart domoticz.")
				self.Error = True
			elif CheckInternet() == False:
				Domoticz.Error("You do not have a working internet connection.")
				self.Internet = False
				#self.Error = True
		except:
			pass

		#Check dependicies
		try:
			if self.Debug == True:
				Domoticz.Log("Checking dependicies.")
			InstalledPackages = get_installed_distributions()
			for package in InstalledPackages:
				if self.Debug == True:
					Domoticz.Log("Processing " + package.key + " with version " + str(package.version))
				if package.key == "pychromecast" and version.parse(package.version) < version.parse("3.2.1"):
					Domoticz.Error(package.key + " is not up to date, it is currently version " + package.version + " it should be at least version 3.2.1. Please upgrade by using this command: 'sudo pip3 install " + package.key + " --upgrade' and restart this plugin.")
					self.Error = True
		except Exception as e:
			senderror(e)
		
		try:
			if self.Error == False:
				#Create temppath if it does not exist
				if not os.path.isdir(self.Filelocation):
					Domoticz.Status("Created folder "+self.Filelocation)
					os.makedirs(self.Filelocation, mode=0o777)
					
				# Check if images are in database
				Domoticz.Status("Checking if images are loaded")
				if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()

				self.ConnectedChromecasts={}
				for i, Chromecastname in enumerate(self.ChromecastNames):
					if Chromecastname != "":
						self.ConnectedChromecasts[Chromecastname.strip()]={
							"Index": i,
							"CC": "",
							"IDX": "",
							"Status": "disconnected",
							"ConnectionTime": 0,
							"YouTube": {"Track": "tAkB-qUL6SA", "Playlist": None}
						}
				
				if Settings["AcceptNewHardware"] != "1" and len(Devices) != len(self.ConnectedChromecasts)*4:
					Domoticz.Error("'Accept new Hardware Devices' is not enabled, please enable it to allow the creation of new devices. Then restart Domoticz.")
					self.Error = True
				else:
					# Check if devices need to be deleted
					self.updateDevices()
					
					# Check if devices need to be created
					createDevices(self.ConnectedChromecasts)

					getVariables()

					#Start FileServer
					if self.Debug == True:
						Domoticz.Log("Local ip address is "+str(self.Ip))
					
					#self.fileserver()

				self.ConnectChromeCast()

		except Exception as e:
			senderror(e)

	def onHeartbeat(self):
		try:
			if CheckInternet() == False:
				self.Error = "You do not have a working internet connection."
				self.Internet = False
				Domoticz.Error(self.Error)
			elif CheckInternet() == True and self.Internet == False:
				self.Internet = True
				Domoticz.Error("Your internet connection is back.")
				self.Error = False

			if self.Error == False:
				RecheckNeeded=False

				while self.q2.empty()==False:
					Result=self.q2.get()
					if "Error" in str(Result):
						Domoticz.Error(Result)
					else:
						Domoticz.Status(Result)
				#p.terminate()

				for ChromecastName in self.ConnectedChromecasts:
					cc=self.ConnectedChromecasts[ChromecastName]["CC"]
					#Check if chromecast is already connected
					if cc == "":
						Domoticz.Status("Will scan for available chromecasts, as " + ChromecastName + " is currently not connected.")
						RecheckNeeded=True

					self.PlayMessage(ChromecastName)

				if RecheckNeeded == True:
					#Check if a chromecast is available in a seperate process.
					#If available connect to it in this process.
					self.pRecheck = Process(target=ScanForChromecasts, args=(self.q,self.ConnectedChromecasts,))
					self.pRecheck.start()
					if self.q.empty() == False:
						self.Recheck = self.q.get()
					self.pRecheck.terminate()

					if self.Recheck == True:
						Domoticz.Log("Connecting to available chromecasts")
						self.ConnectChromeCast()
					else:
						Domoticz.Log(str(self.Recheck))
		except Exception as e:
			senderror(e)

	def onCommand(self, Unit, Command, Level, Hue):
		try:
			#get first number of the Unit
			if len(str(Unit)) == 1:
				ChromecastId=0
			else:
				ChromecastId=int(str(Unit)[-2])

			#Find the corresponding chromecast
			ChromecastName=next(Chromecast for Chromecast in self.ConnectedChromecasts if self.ConnectedChromecasts[Chromecast]["Index"] == ChromecastId)

			if self.ConnectedChromecasts[ChromecastName]["Status"] != "CONNECTED":
				Domoticz.Error("Chromecast '"+ChromecastName+"' is not connected, so I cannot issue a command to it. Reconnect '"+ChromecastName+"' and try again.")
				if self.ConnectedChromecasts[ChromecastName]["CC"] != "":
					self.ConnectedChromecasts[ChromecastName]["CC"].disconnect()
			else:
				try:
					cc=self.ConnectedChromecasts[ChromecastName]["CC"]
					Mc = cc.media_controller
					if cc != "" and (cc.status != None or Unit % 10 == 4):
						#Control device
						if Unit % 10 == 1:
							#Prev
							if Level == 10:
								#Previous
								Mc.rewind()
							#Play
							elif Level == 20:
								Domoticz.Log("Start playing on '"+cc.name+"'")
								Mc.play()
							#Pause
							elif Level == 30:
								Domoticz.Log("Pausing '"+cc.name+"'")
								Mc.pause()
							#Stop
							elif Level == 40:
								Domoticz.Log("Killing "+cc.app_display_name + " on '"+cc.name+"'")
								cc.quit_app()
							#Next
							elif Level == 50:
								Mc.skip()
							else:
								Domoticz.Log("Level is "+Level+" What should I do with it?")
						#Volume device
						elif Unit % 10 == 2:
							vl = float(Level)/100
							cc.set_volume(vl)
						#App name device
						elif Unit % 10 == 4:
							LevelNames = Devices[Unit].Options["LevelNames"].split("|")
							AppName = LevelNames[int(Level/10)]
							if AppName == "YouTube":
								Domoticz.Status("Starting Youtube on '"+cc.name+"'")
								q = Queue()
								self.pYouTube = Process(target=RestartYoutube, args=(q,cc.uri,self.ConnectedChromecasts[ChromecastName]["YouTube"]["Track"]))
								self.pYouTube.deamon=True
								self.pYouTube.start()
					elif (cc.status == None):
						Domoticz.Status("Cannot issue a command to '"+ChromecastName+"' when no app is connected.")
					else:
						Domoticz.Error("Cannot issue the command as the Chromecast '"+ChromecastName+"' is not connected.")
				except Exception as e:
					senderror(e)
		except Exception as e:
			senderror(e)

	def onStop(self):
		try:
			if hasattr(self,"pFileserver"):
				self.pFileserver.terminate()
				Domoticz.Status("Stopping fileserver process.")

			if hasattr(self,"pYouTube"):
				self.pYouTube.terminate()
				Domoticz.Status("Stopping YouTube process.")

			if hasattr(self,"pRecheck"):
				self.pRecheck.terminate()
				Domoticz.Status("Stopping recheck process.")

			for ChromecastName in self.ConnectedChromecasts:
				if self.ConnectedChromecasts[ChromecastName]["CC"] != "":
					cc=self.ConnectedChromecasts[ChromecastName]["CC"]
					Domoticz.Status("Disconnecting from '"+cc.name+"'")
					cc.disconnect()
		except Exception as e:
			senderror(e)

	def ConnectChromeCast(self):
		Domoticz.Status("Checking for available chromecasts")
		try:
			self.Chromecasts = pychromecast.get_chromecasts()[0]
			if len(self.Chromecasts) != 0:
				Names="Found these chromecasts: "
				for chromecast in self.Chromecasts:
					Names+="'"+chromecast.cast_info.friendly_name+"', "

				Domoticz.Status(Names[:-2])
			else:
				Domoticz.Status("No casting devices found, make sure they are online.")

				for ChromecastName in self.ConnectedChromecasts:
					SetDeviceTimeOut(self.ConnectedChromecasts[ChromecastName]["Index"], 1)
		except Exception as e:
			senderror(e)

		#Check if there any non-connected chromecast available
		try:
			if len(self.Chromecasts) != 0:
				for chromecast in self.Chromecasts:
					try:
						#Check if chromecast is already connected
						if self.ConnectedChromecasts[chromecast.name]["CC"] == "":
							chromecast.start()
							chromecast.wait()
							if chromecast.status is not None and chromecast.status.volume_level == 1:
								chromecast.set_volume(0.5)
								Domoticz.Status("Set volume of '" + chromecast.name +"' to 50%")
							self.ConnectedChromecasts[chromecast.name]["CC"]=chromecast
							Domoticz.Status("Connected to '" + chromecast.name+"'")
							self.ConnectedChromecasts[chromecast.name]["Status"]="CONNECTED"
							self.startListening(chromecast)
						else:
							Domoticz.Status("ALready connected to "+chromecast.name)
					except KeyError:
						#Disconnect from the chromecast as we don't need it
						#chromecast.disconnect()
						pass
					except StopIteration:
						#Chromecast is currently not available
						Domoticz.Status("Could not connect to '"+chromecast.name+"'")
						SetDeviceTimeOut(self.ConnectedChromecasts[chromecast.name]["Index"], 1)
					except Exception as e:
						senderror(e)
		except Exception as e:
			senderror(e)

	def startListening(self,chromecast):
		Domoticz.Status("Registering listeners for '" + chromecast.name+"'")
		listenerCast = StatusListener(chromecast)
		chromecast.register_status_listener(listenerCast)

		listenerMedia = StatusMediaListener(chromecast)
		chromecast.media_controller.register_status_listener(listenerMedia)
		
		connectioncast=ConnectionListener(chromecast)
		chromecast.register_connection_listener(connectioncast)

		Domoticz.Status("Done registering listeners for '"+ chromecast.name+"'")
		
	def fileserver(self, Port=0):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			if(Port == 0):
				Port = int(Parameters["Mode3"])

			Domoticz.Status("Starting file server on port "+str(Port))
			os.chdir(self.Filelocation)
			Handler = http.server.SimpleHTTPRequestHandler
			socketserver.TCPServer.allow_reuse_address = True
			server = socketserver.TCPServer(("", Port), Handler)
			self.pFileserver = Process(target=server.serve_forever)
			self.pFileserver.deamon = True
			self.pFileserver.start()
			Domoticz.Status("Files in the '"+self.Filelocation+"' directory are now available on port "+str(Port)+" PID is "+self.pFileserver.pid)
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
				Domoticz.Log("Port "+str(Port)+" is already in use")
				Port +=1
				self.fileserver(Port)
			else:
				senderror(e)
		except Exception as e:
			senderror(e)

	def updateDevices(self):
		try:
			result = requests.get(self.Url+"/json.htm?type=command&param=getuservariables").json()
			result['status']
			VariablesIDX=result.get('result')
		except:
			Domoticz.Error("Could not get all variables. Used this url: "+self.Url+"/json.htm?type=command&param=getuservariables")
			self.Error = True

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
							#Find the corresponding variable based on the chromecast name
							idx=next(var for var in VariablesIDX if var["Name"]==ChromecastName)
							result=requests.get(url=self.Url+"/json.htm?type=command&param=deleteuservariable&idx="+idx["idx"]).json()["status"]
							if result=="OK":
								Domoticz.Log("Removed uservariable for '"+ChromecastName+"'")
							else:
								Domoticz.Error("Could not remove user variable '"+ChromecastName+"', result was '"+result+"'. URL used is "+_plugin.Url+"/json.htm?type=command&param=deleteuservariable&idx="+Chromecasts[ChromecastName]["IDX"])
					except StopIteration:
						pass
					except Exception as e:
						senderror(e)

					#Delete devices
					for i in range(4):
						x=deviceid+i
						Domoticz.Log("Deleting '"+Devices[x].Name+"' with id "+str(x))
						Devices[x].Delete()
				elif self.ConnectedChromecasts.get(ChromecastName)["Index"] != ChromecastId:
					Currentid=self.ConnectedChromecasts[ChromecastName]["Index"]
					#Check if there is already a chromecast with this id
					try:
						Chromecast = next(Chromecast for Chromecast in self.ConnectedChromecasts if self.ConnectedChromecasts[Chromecast]["Index"]==ChromecastId)
						self.ConnectedChromecasts[Chromecast]["Index"] = Currentid
					except StopIteration:
						pass
					except Exception as e:
						senderror(e)
					self.ConnectedChromecasts[Chromecast]["Index"] = Currentid
		except Exception as e:
			senderror(e)

	def PlayMessage(self, ChromecastName, messageUrl=''):
		#Check if text needs to be spoken
		try:
			Text = requests.get(url=self.GetVariableUrl+self.ConnectedChromecasts[ChromecastName]["IDX"]).json()['result'][0]['Value']
		except:
			Text = ""
			Domoticz.Error(self.GetVariableUrl+self.ConnectedChromecasts[ChromecastName]["IDX"] + " did not return any results. ("+str(self.ConnectedChromecasts[ChromecastName])+")")

		try:
			cc = self.ConnectedChromecasts[ChromecastName]["CC"]
			#Speak the text
			if Text != "" and cc != "":
				#if not self.pFileserver:
					#self.fileserver()

				#Reset the variable to empty
				requests.get(url=self.Url+"/json.htm?type=command&param=updateuservariable&vname="+ChromecastName+"&vtype=2&vvalue=")
				if self.ConnectedChromecasts[ChromecastName]["Status"] == "CONNECTED":
					cc.wait()
					
					broken	= False

					#Create mp3
					#os.system('curl -s -G "http://translate.google.com/translate_tts" --data "ie=UTF-8&total=1&idx=0&client=tw-ob&&tl='+self.Languague+'" --data-urlencode "q='+Text+'" -A "Mozilla" --compressed -o '+self.Filelocation+'/message.mp3')
					#messageUrl	= 'http://'+str(self.Ip)+':'+str(self.Port)+'/message.mp3'
					
					if messageUrl == '':
						url = 'https://api.ttsmaker.com/v1/create-tts-order'
						headers = {'Content-Type': 'application/json; charset=utf-8'}
						params = {
							'token': 'ttsmaker_demo_token',
							'text': Text,
							'voice_id': 778,
							'audio_format': 'mp3',
							'audio_speed': 1.0,
							'audio_volume': 0,
							'text_paragraph_pause_time': 0
						}
						response = requests.post(url, headers=headers, data=json.dumps(params))
						messageUrl	= response.json()['audio_file_url']

					try:
						Domoticz.Status('Will pronounce "'+Text+'" on chromecast '+ChromecastName+" from "+messageUrl)
						Mc=cc.media_controller

						#Store player session
						if cc.status.display_name is not None and Mc.status.player_state == 'PLAYING':
							Currenttime = Mc.status.current_time
							MediaId = Mc.status.content_id
							PreviousApp = cc.status.display_name
						else:
							PreviousApp 			= False
						
						if Parameters["Mode6"] == "True":
							PreviousVolume 			= int(cc.status.volume_level*100)
							Domoticz.Log("Current volume is "+str(PreviousVolume))
							cc.quit_app()

							i = 0
							while Mc.status.player_state == 'PLAYING' and i <50:
								time.sleep(0.1)
								i += 1

							Domoticz.Log("Maximizing volume")
							cc.set_volume(.95)
						else:
							cc.quit_app()
						
						#Play on chromecast
						Mc.play_media(messageUrl, 'music/mp3')
					except Exception as e:
						Domoticz.Log("Message is broken")
						broken	= True

					if not broken:
						count	= 0
						while Mc.status.player_state != 'PLAYING' or cc.status.display_name != 'Default Media Receiver':
							Domoticz.Log("Sleeping while waiting for playing")
							time.sleep(0.1)
							count += 1
							if count == 100:
								broken	= True
								break

						count	= 0

						if not broken:
							while Mc.status.player_state == 'PLAYING':
								Domoticz.Log("Sleeping while playing")
								time.sleep(0.1)
								count += 1
								if count == 100:
									broken	= True
									break

					if broken:
						time.sleep(3)
						Domoticz.Log("Retrying")
						self.PlayMessage(ChromecastName, messageUrl)
						requests.get(url=self.Url+"/json.htm?type=command&param=updateuservariable&vname="+ChromecastName+"&vtype=2&vvalue="+Text)
					else:
						Domoticz.Log("Message is played.")
						
						if Parameters["Mode6"]=="True" and PreviousVolume != 0 and PreviousVolume != 100:
							#Reset Volume
							Domoticz.Log("Restoring original volume of "+str(PreviousVolume))
							cc.set_volume(PreviousVolume/100)
						
						#Restart previous session
						if PreviousApp == "Youtube":
							Domoticz.Status("Restarting video with id:"+str(MediaId)+" on YouTube.")
							q = Queue()
							self.p_YouTube 			= Process(target=RestartYoutube, args=(q,cc.uri,MediaId,CurrentTime))
							self.p_YouTube.deamon 	= True
							self.p_YouTube.start()
							while q.empty() 		== True:
								time.sleep(1)
							Domoticz.Log(q.get())
							self.p_YouTube.terminate()
						else:
							cc.quit_app()
				else:
					Domoticz.Error("Cannot play '"+Text+"' on '"+ChromecastName+"' as the chromecast is not connected.")
					time.sleep(3)
					self.PlayMessage(ChromecastName, messageUrl)
		except Exception as e:
			senderror(e)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    while CheckInternet() == False:
        print("You do not have a working internet connection.")
        time.sleep(100)
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
			result=requests.get(_plugin.Url+"/json.htm?type=command&param=adduservariable&vname="+Chromecast+"&vtype=2&vvalue=").json()
			if result["status"] == "OK":
				Domoticz.Log("Created uservariable for '"+Chromecast+"'")
			elif result["status"] =="ERR":
				result=requests.get(_plugin.Url+"/json.htm?type=command&param=saveuservariable&vname="+Chromecast+"&vtype=2&vvalue=").json()
				if result["status"] == "OK":
					Domoticz.Log("Created uservariable for '"+Chromecast+"'")
			elif result["message"] == "Variable name already exists!" or result["message"] == "Variable with the same Name already exists!":
				#Domoticz.Log("Variable for "+Chromecast+" already exists.")
				pass
			else:
				Domoticz.Error("Could not create '"+Chromecast+"', result was "+result+". Url used is "+_plugin.Url+"/json.htm?type=command&param=saveuservariable&vname="+Chromecast+"&vtype=2&vvalue=")

			x=Chromecasts[Chromecast]["Index"]*10
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
		VariablesIDX=(requests.get(_plugin.Url+"/json.htm?type=command&param=getuservariables").json())['result']

		#Retrieve the Domoticz IDX of the variables
		for chromecast in _plugin.ConnectedChromecasts:
			try:
				variable=next(var for var in VariablesIDX if var["Name"]==chromecast)
				_plugin.ConnectedChromecasts[chromecast]["IDX"]=variable["idx"]
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
		if Devices[Unit].nValue != nValue or Devices[Unit].sValue != str(sValue) or AlwaysUpdate == True:
			Devices[Unit].Update(nValue, str(sValue))
			#Domoticz.Log("Update " + Devices[Unit].Name + ": " + str(nValue) + " - '" + str(sValue) + "'")
	return

def SetDeviceTimeOut(Unit, Value):
	try:
		Names = ""
		for x in range(Unit*10+1, Unit*10+5):
			Names += "'" + Devices[x].Name + "', "
			Devices[x].Update(nValue=Devices[Unit+1].nValue, sValue=str(Devices[Unit+1].sValue), TimedOut=Value)

		if Value == 0:
			Domoticz.Log("Setting devices "+ Names[:-2] +" as not timed out, as the chromecast is connected.")
		else:
			Domoticz.Log("Setting devices "+ Names[:-2] +" as timed out, as the chromecast is not connected.")
	except Exception as e:
		senderror(e)

def CheckInternet():
	try:
		requests.get(url='http://www.google.com/', timeout=30)
		return True
	except requests.ConnectionError:
		return False

def GetIP():
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
		
def RestartYoutube(q,uri,videoid,seektime = None):
	try:
		ip=uri.split(":")[0]
		port=int(uri.split(":")[1])
		cc = pychromecast.Chromecast(ip,port)
		Mc=cc.media_controller
		cc.wait()
		yt = YouTubeController()
		cc.register_handler(yt)
		yt.play_video(videoid)
		Mc.block_until_active()
		while Mc.status.player_state != 'PLAYING':
			time.sleep(0.1)
		Mc.seek(seektime)
		time.sleep(2)
		cc.disconnect()
		q.put("Done")
	except Exception as e:
		q.put('Error on line {}'.format(sys.exc_info()[-1].tb_lineno)+" Error is: " +str(e))

def ScanForChromecasts(q,ConnectedChromecasts):
	Recheck=False
	try:
		chromecasts = pychromecast.get_chromecasts()[0]
	except Exception as e:
		print(e)

	q.put("Found these chromecasts: " + str(chromecasts))
	#Check if there are any non-connected chromecast available
	if len(chromecasts) != 0:
		for ChromecastName in ConnectedChromecasts:
			#Check if chrmecast is already connected
			if ConnectedChromecasts[ChromecastName]["CC"] == "":
				#Try to find the chromecast in the available chromecasts
				try:
					cc=next(cc for cc in chromecasts if cc.cast_info.friendly_name == ChromecastName)
					q.put("Found " + str(cc))
					Recheck=True
				except Exception as e:
					pass
		for Chromecast in chromecasts:
			Chromecast.disconnect()

	q.put(Recheck)
