Chromecast plugin for Domoticz, based on PyChromecast
============================================


Short summary
-------------
This plugin add devices to Domoticz to control your chromecast, and to retrieve its current app, title, playing mode.

Installation and setup
----------------------
1)  Install Plugin: 
```bash
cd domoticz/plugins
git clone https://github.com/Tsjippy/ChromecastPlugin
```
2) Install PyChromecast: 
```bash
sudo pip3 install pychromecast -t /home/pi/domoticz/plugins/ChromecastPlugin
```
3) Restart domoticz: 
```bash
sudo service domoticz.sh restart
```
4) Add hardware, supply a chromecast name as well


Known bugs
----------
* Does not work with the current stable of domoticz, you need the latest beta
* The created devices are read-only.
* You can't just install pychromecast like this: sudo pip3 install pychromecast. It has to be installed in the plugin folder.
