# -*- coding: utf-8 -*-
import kivy
kivy.require('1.0.6') # replace with your current kivy version !

from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.videoplayer import VideoPlayer
from kivy.uix.listview import ListView, ListItemButton
from kivy.adapters.listadapter import ListAdapter
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle

import RPi.GPIO as GPIO
import time, datetime
from functools import partial
import dht11
import os, subprocess
import mysql.connector
import smbus

#for now, use a global for blink speed (better implementation TBD):
ringing = False
ledOn = False
lastTouch = datetime.datetime.now()
sleepTime = 15
lastMotion = datetime.datetime.now()
lastLedButtonOn = datetime.datetime.now()
tempHumi =[0,0]
sleep = False
night = False

# Set up GPIO:
beepPin = 17
ledPin = 27
BellButton = 22
PIR = 4
Light = 0

GPIO.setmode(GPIO.BCM)
GPIO.setup(beepPin, GPIO.OUT)
GPIO.output(beepPin, GPIO.LOW)
GPIO.setup(ledPin, GPIO.OUT)
GPIO.output(ledPin, GPIO.LOW)
GPIO.setup(BellButton, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIR, GPIO.IN)
instance = dht11.DHT11(pin=14)




# Define some helper functions:

# This callback will be bound to the LED toggle button
def press_callback(obj):
        global ringing
        global ledOn
        global lastLedButtonOn
	if obj.text == 'LED':
		if obj.state == "down":
			GPIO.output(ledPin, GPIO.HIGH)
			ledOn=True
			lastLedButtonOn = datetime.datetime.now()
		else:
			ledOn=False
#Wake Up Display from sleep
def wakeUpDisplay():
        subprocess.call('xset dpms force on', shell=True)

#Sleep display
def sleepDisplay(dt):
        subprocess.call('xset dpms force off', shell=True)

def setDisplaySleepTime(sec,dt):
        string = 'xset dpms ' + str(sec) + ' ' + str(sec) + ' ' + str(sec)
        subprocess.call(string, shell=True)
        print 'time to sleep display was setted to: '+str(sec)+' seconds.'

#sleep button event /0.2 s delay for filter double click by mistake
def sleepDisplayButton(dt):
        global sleep
        Clock.schedule_once(sleepDisplay,0.2)
        sleep = True

#ring event making bell ringing and LED flashing,
#preventing from multiple ringing and logging event
# self param is ButtonImage instance represents bell icon /for flashing logo
def rg(self, dt):
        global ringing
        if not ringing:
                Clock.schedule_once(partial(flashIcon,self,20), 0.01)
                Clock.schedule_once(partial(ring,10), 0.01)
                logBell()

#This function recursively call's self (with decreased cnt param).
#In each iteration are switched GPIO ports for LED and BELL on or off
def ring(cnt,dt):
        global ringing
        global night
        if cnt>0:
                ringing = True
                GPIO.output(ledPin, not GPIO.input(ledPin))
                GPIO.output(beepPin, not GPIO.input(beepPin))
                Clock.schedule_once(partial(ring, cnt-1), 1)
        else:
                ringing = False
                #if LED was turned on manualy, turn it on again after ringing
                if ledOn or (((lastMotion+datetime.timedelta(seconds=30))-datetime.datetime.now()).total_seconds()>0 and night):
                        GPIO.output(ledPin,True)
                

#Blinking bell icon when ringing /speed is set by Clock.shcedule param (0.5)
#Used by rg() function
def flashIcon(self, cnt, dt):
        if cnt>0:
                if self.source=='Bell.png':
                        self.source='BellR.png'
                else:
                        self.source='Bell.png'
                Clock.schedule_once(partial(flashIcon,self,cnt-1), 0.5)

#polling GPIO pin state for bell push button. If button is pushed,
#display is waked up and ringing is scheduled for next frame
def bellImageRefresh(self, dt):
        global ringing
        if GPIO.input(BellButton) == False and not ringing: #If button is pressed
                wakeUpDisplay()
                Clock.schedule_once(partial(rg, self), 0)

#refreshing every second Time label with actual time
def timeRefresh(self,dt):
        self.text = datetime.datetime.now().strftime('%H:%M:%S')

#returns array of (timestamp, note) from MySql DB.
#you can specify count of entries by param count
#if count==0, count is setted to 50
def getBells(count):
        result = []
        conn = mysql.connector.connect(user='smarthome', password='1CJIxAWSEP74TbSh', host='127.0.0.1', database='smarthome')
        cursor = conn.cursor()
        
        data = count
        if count==0:
                data=50
        selectQuerry = "SELECT * FROM bells ORDER BY timestamp DESC LIMIT "+str(data)
        cursor.execute(selectQuerry)
        for timestamp in cursor:
                result.append(timestamp[0])
        cursor.close()
        conn.close()
        return result

#Log timestamp and note for bell into the MySql DB
def logBell():
        conn = mysql.connector.connect(user='smarthome', password='1CJIxAWSEP74TbSh', host='127.0.0.1', database='smarthome')
        cursor = conn.cursor()
        insertQuerry = ("INSERT INTO bells (timestamp, note)"
                        "VALUES (%s, %s)")
        data = (datetime.datetime.now(),'n')
        cursor.execute(insertQuerry,data)
        conn.commit()
        cursor.close()
        conn.close()

#Log timestamp, temp, humi and note into the MySql DB
def logTempAndHumi(th):
        conn = mysql.connector.connect(user='smarthome', password='1CJIxAWSEP74TbSh', host='127.0.0.1', database='smarthome')
        cursor = conn.cursor()
        insertQuerry = ("INSERT INTO temperatures (timestamp, temperature, humidity, note)"
                        "VALUES (%s, %s, %s, %s)")
        data = (datetime.datetime.now(),th[0],th[1],'chodba_vstup')
        cursor.execute(insertQuerry,data)
        conn.commit()
        cursor.close()
        conn.close()

#Get temp and humi from sensor (DHT11), fill global variable temphumi (array)
#log data
def tempHumiMeasure(dt):
        global tempHumi
        result = instance.read()
        if result.is_valid():
                tempHumi[0]=result.temperature
                tempHumi[1]=result.humidity
                logTempAndHumi(tempHumi)
        else:
                Clock.schedule_once(tempHumiMeasure, 1)

#refreshing Temp label with actual temperature
def tempRefresh(self, dt):
        global tempHumi
        self.text = "Teplota: "+str(tempHumi[0])+" °C"

#refreshing Humi label with actual humidity              
def humiRefresh(self, dt):
        global tempHumi
        self.text = "Vlhkosť: "+str(tempHumi[1])+" %"

#manually turn off LED
def ledOff(self, dt):
        global ledOn
        #GPIO.output(ledPin,False)
        self.state='normal'
        ledOn=False



#class for Image with Button behavior
class ImageButton(ButtonBehavior, Image):
    pass

#Gets last 5 entries from MySql DB and show it in popup
def showLastBells(self):
        data = getBells(5)
        txt = ''
        for timestamp in data:
                txt += str(timestamp.strftime('%d. %b - %H:%M:%S'))+ "\n"
        layout = BoxLayout(orientation='vertical')
        lb1 = Label(text=txt, font_size='20sp')
        btn = Button(text='Zatvoriť', size_hint_y=0.2)
        layout.add_widget(lb1)
        layout.add_widget(btn)
        popup = Popup(title='Posledné zvonenia',
                    content=layout,
                    size_hint=(None, None), size=(400, 400))
        btn.bind(on_press=popup.dismiss)
        popup.open()

def videoArchiveItemSelected(player,popup,self):
        id = self.selection[0].text.split("  ")[0]
        data = getVideoList()
        video = next(v for v in  data if v.id==id)
        player.source=video.path
        player.state='play'
        popup.title='Video archív  -  ' + video.time.strftime('%d. %b - %H:%M:%S')

class VideoListItemButton(ListItemButton):
        deselected_color=[0, 0, 0, 1]

def videoArchiveBtnCallback(self):
        setDisplaySleepTime(9999,1)
        data = getVideoList()
        listData = []
        for d in data:
                listData.append(d.id + "  " + d.time.strftime('%d. %b - %H:%M:%S'))

        list_adapter = ListAdapter(data=listData,
                           cls=VideoListItemButton,
                           selection_mode='single',
                           allow_empty_selection=False)
        player = VideoPlayer(source=data[0].path, state='play', options={'allow_stretch': True})
        root = GridLayout(cols=2)
        popup = Popup(title='Video archív  -  '+data[0].time.strftime('%d. %b - %H:%M:%S'),
                    content=root,
                    size_hint=(1, 1))
        list_adapter.bind(on_selection_change=partial(videoArchiveItemSelected,player, popup))
        
        
        layout1 = BoxLayout(orientation='vertical')
        layout2 = BoxLayout(orientation='vertical')
        videoList = ListView(adapter=list_adapter)
        btn = Button(text='Zatvoriť', size_hint_y=0.2)
        layout1.add_widget(videoList)
        layout2.add_widget(player)
        layout2.add_widget(btn)
        root.add_widget(layout1)
        root.add_widget(layout2)
        
        btn.bind(on_press=partial(videoArchiveExitBtnCallback,popup))
        popup.open()

def videoArchiveExitBtnCallback(popup,self):
        popup.dismiss()
        setDisplaySleepTime(15,1)

class VideoFile:
        def __init__(self, id, time, path):
                self.id=id
                self.time=time
                self.path=path

def getVideoList():
        path = "/mnt/motionvideos"
        result=[]
        for file in os.listdir(path):
            if file.endswith(".avi"):
                result.append(VideoFile(file.split('-')[0],datetime.datetime.strptime(file.split('-')[1].split('.')[0],'%Y%m%d%H%M%S%f'), os.path.join(path, file)))
        return sorted(result, key=lambda x: x.time, reverse=True)        

def Night(dt):
          global night
          DEVICE = 0x23 # I2C device address
          bus = smbus.SMBus(1)  # RconvertToNumber
          data = convertToNumber(bus.read_i2c_block_data(DEVICE,0x11))
          if not(data > 1):
                night=True
          else:
                night=False

def convertToNumber(data):
          return ((data[1] + (256 * data[0])) / 1.2)

def motion():
        return GPIO.input(PIR)


def ledAuto(dt):
        global night
        global ledOn
        global lastMotion
        global ringing
        time = 7
        if motion():
                lastMotion = datetime.datetime.now()
                if night and not GPIO.input(ledPin) and not ringing:
                        GPIO.output(ledPin, True)
                        print "On"
        else:
                if not ledOn and GPIO.input(ledPin) and not ringing:
                        if ((lastMotion+datetime.timedelta(seconds=time))-datetime.datetime.now()).total_seconds()<0:
                                GPIO.output(ledPin,False)
                                print "Off" 
def refreshLedButton(btn,dt):
        global lastLedButtonOn
        if ((lastLedButtonOn+datetime.timedelta(seconds=120))-datetime.datetime.now()).total_seconds()<0 and GPIO.input(ledPin) and not ringing:
                ledOff(btn,1)

class MyGridLayout(GridLayout):
        def on_touch_down(self, touch):
                global lastTouch
                global sleepTime
                global sleep
                print touch
                print str(lastTouch) + "ontouch"
                if ((lastTouch+datetime.timedelta(seconds=sleepTime))-datetime.datetime.now()).total_seconds()<0 or sleep:
                        wakeUpDisplay()
                        lastTouch = datetime.datetime.now()
                        sleep = False
                else:
                        super(MyGridLayout,self).on_touch_down(touch)
                        lastTouch = datetime.datetime.now()

#main class
class MyApp(App): 
	def build(self):              
		# Set up the layout:
		layout = MyGridLayout(cols=4, spacing=30, padding=30, row_default_height=150)

		# Make the background gray:
		with layout.canvas.before:
			Color(.2,.2,.2,1)
			self.rect = Rectangle(size=(800,600), pos=layout.pos)
                #Start Temp adn Humidity measurment
		Clock.schedule_interval(tempHumiMeasure,900)
                Clock.schedule_once(tempHumiMeasure,5)

                Clock.schedule_interval(Night,1)

                Clock.schedule_interval(ledAuto,0)
                Clock.schedule_once(partial(setDisplaySleepTime,15),1)

		# Instantiate the first UI object (the GPIO input indicator):
                bellImage = ImageButton(source='Bell.png')
                bellImage.bind(on_press=showLastBells)
		# Schedule the update of the state of the GPIO input button:
		Clock.schedule_interval(partial(bellImageRefresh,bellImage), 1.0/10.0)
		# Create the rest of the UI objects (and bind them to callbacks, if necessary):
		outputControl = ToggleButton(text="LED",font_size='25sp')
		outputControl.bind(on_press=press_callback)
		Clock.schedule_interval(partial(refreshLedButton,outputControl),0.5)
	
		timeLabel = Label(text='time',font_size='50sp')
		Clock.schedule_interval(partial(timeRefresh,timeLabel), 1)
		
		# Add the UI elements to the layout:
                layout1 = BoxLayout(orientation='vertical')
                l1 = Label(text="temp",font_size='25sp')
                Clock.schedule_interval(partial(tempRefresh,l1), 60)
                Clock.schedule_once(partial(tempRefresh,l1), 5)
                l2 = Label(text="humi",font_size='25sp')
                Clock.schedule_interval(partial(humiRefresh,l2), 60)
                Clock.schedule_once(partial(humiRefresh,l2), 5)
                l3 = Label(text=" ",font_size='25sp')
                videoArchiveBtn = Button(text='Video archív')
                videoArchiveBtn.bind(on_press=videoArchiveBtnCallback)
                layout1.add_widget(timeLabel)
                layout1.add_widget(l1)
                layout1.add_widget(l2)
                layout1.add_widget(l3)
                layout1.add_widget(videoArchiveBtn)

                layout2 = FloatLayout()
                sleepBtn = ImageButton(source='sleep.png', pos=(670,405))
                sleepBtn.bind(on_press=sleepDisplayButton)
                layout2.add_widget(sleepBtn)
                layout1.add_widget(layout2)
                
		layout.add_widget(layout1)
		layout.add_widget(bellImage)
		layout.add_widget(outputControl)
		


		return layout

if __name__ == '__main__':
	MyApp().run()
