Chromecast plugin for Domoticz, based on PyChromecast
============================================


Short summary
-------------
This plugin adds devices and an user variable to Domoticz to control your chromecasts, and to retrieve the current app, title, volume and playing mode.
Every chromecast (or chromecast group) gets its own set of devices.
The variable is used to send text to the chromecast to pronounce in a languague which can be set via the hardware options.
Just add a languague code like 'en-US' or 'nl-NL', type in any text in the auto-generated variable. The text will be spoken on the relevant chromecast.

Installation and setup
----------------------
1)  Install Plugin: 
```bash
cd domoticz/plugins
git clone https://github.com/Tsjippy/ChromecastPlugin
```
2) Install dependecies: 
```bash
sudo pip3 install pychromecast -t /home/pi/domoticz/plugins/ChromecastPlugin
```
3) Restart domoticz: 
```bash
sudo service domoticz.sh restart
```
4) Add hardware, fill in the required field, including a comma seperated list of chromecast names (or just one)
You can find the languague code relevant for you here: http://www.lingoes.net/en/translator/langcode.htm

Known issues
----------
* After playing a custom mesagge, your previous playback does not resume. (except for YouTube)
* Limited support for Netflix as they encrypt their data:
  * If you pause netflix from the web/an app, Domoticz doesn't know, if you pause it from Domoticz it works
  * Spotify cannot mad to resume because of this bug: https://github.com/balloob/pychromecast/issues/253

Known bugs
----------
* Does not work with the current stable of domoticz, you need the latest beta
* You can't just install pychromecast like this: sudo pip3 install pychromecast. It has to be installed in the plugin folder.
* In order to delete the hardware you need to disable it, then restart domoticz, then delete it.
* In order to change any hardware settings you have to disable the hardware, restart domoticz, change the hardware, then re-enable it.
