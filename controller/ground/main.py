############
#Set working dir
import os
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)
#############

import datetime
import subprocess
import time

from collections import OrderedDict
import tkinter as tk
from tkinter import *
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import *
from PIL import ImageTk, Image
import glob
import os
import psutil

import logging
from logging.handlers import RotatingFileHandler

try:
    import httplib
except:
    import http.client as httplib


class TextHandler(logging.Handler):
    """This class allows you to log to a Tkinter Text or ScrolledText widget"""
    def __init__(self, text):
        # run the regular Handler __init__
        logging.Handler.__init__(self)
        # Store a reference to the Text it will log to
        self.text = text

    def emit(self, record):
        msg = self.format(record)
        def append():
            ##Try to get Tag:
            tag=""
            try:
                tag=msg.split(" ")[2]
            except:
                pass
            self.text.configure(state='normal')
            self.text.insert(END, msg + '\n',tag)
            self.text.configure(state='disabled')
            # Autoscroll to the bottom
            self.text.yview(END)
        # This is necessary because we can't modify the Text from other threads
        self.text.after(0, append)



class GUI:
    def __init__(self):
        ###############
        #Variables
        ###############
        self.bad = 0 #mon has a bad state if >0 (number of checks*bad states)

        #######################
        #Logger:
        ######################
        logging.basicConfig(level="DEBUG")
        formatter=logging.Formatter('%(asctime)s %(levelname)-6s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        self.logger = logging.getLogger('piMon')
        self.handler = RotatingFileHandler('piMon.log', maxBytes=2000, backupCount=10)
        self.handler.setFormatter(formatter)
        self.logger.addHandler(self.handler)
        self.logger.info('Application: startup')

        self.window = Tk()
        #self.window.attributes('-zoomed', True)
        self.window.bind("<F11>", self.toggleFullScreen)
        self.window.bind("<Escape>", self.quitFullScreen)

        self.mainFrame = Frame(self.window)

        self.mainFrame.pack(side=TOP, fill=BOTH)

        ###########
        # Show Plot:
        ##########
        #self.panel = Label(self.window)
        #self.panel.place(x=0, y=0, relwidth=1, relheight=1)


        #############
        #Settings:
        ############
        self.path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'../reader/beastReader/')
        ##############
        #Checks

        self.checks = []
        #self.checks.append({"name": "port_in_use", "function": self.check_port_in_use})
        self.checks.append({"name": "internet", "function": self.check_internet})
        self.checks.append({"name": "check_dump1090", "function": self.check_processrunning, "parameter": ["dump1090"]})
        self.checks.append({"name": "check_sim", "function": self.check_processrunning, "parameter": ["sim.py"]})
        self.checks.append({"name": "check_reader", "function": self.check_processrunning, "parameter": ["beast_reader.py"]})
        self.checks.append({"name": "file_written", "function": self.check_file_write, })
        self.checks.append({"name": "check_messages", "function": self.check_received_messages})

        self.labels = []  # creates an empty list for your labels
        for i,itm in enumerate(self.checks):  # iterates over your nums
            label = Label(self.mainFrame, text=itm['name'],anchor="center")  # set your text
            itm['label'] = label
            label.grid(row=i,column=0, sticky='nswe', padx=5, pady=1)
            self.labels.append(label)  # appends the label to the list for further use

        self.options =[]
        self.options.append({"name":"Wifi-Setup","function":self.set_wifi})
        self.options.append({"name":"Show Plot","function":self.set_show_plot})
        self.buttons = []
        for i, itm in enumerate(self.options):
            button = Button(self.mainFrame,text=itm['name'],command=itm['function'])
            itm['button'] = button
            button.grid(row=0, column=i+1, sticky='nswe', padx=5, pady=5,ipady=20 )
            self.buttons.append(button)


        ######
        #Logger GUI:
        #######
        self.textLog=ScrolledText(self.mainFrame,state="disabled")
        self.textLog.configure(font='TkFixedFont')
        self.textLog.tag_config('INFO', foreground='black')
        self.textLog.tag_config('DEBUG', foreground='gray')
        self.textLog.tag_config('WARNING', foreground='orange')
        self.textLog.tag_config('ERROR', foreground='red')
        self.textLog.tag_config('CRITICAL', foreground='red', underline=1)
        self.textLog.grid(row=1, column=1, rowspan=len(self.labels),columnspan=len(self.buttons), sticky="nsew",
                                     padx=5, pady=1)

        self.text_handler = TextHandler(self.textLog)
        self.text_handler.setFormatter(formatter)
        self.logger.addHandler(self.text_handler)
        #######
        #Plot in Layout:
        #######
        #self.panel.grid(row=len(self.buttons), column=2, rowspan=len(self.labels) - len(self.buttons), sticky="we",
        #                padx=5, pady=1)

        for i in range(0,len(self.labels)):
            self.mainFrame.rowconfigure(i,weight=1)
        for i in range(0,len(self.buttons)):
            self.mainFrame.columnconfigure(1+i,weight=1)
        #self.mainFrame.columnconfigure(0,weight=0)

        #######
        #Start
        #######
        self.sys_check()
        #############

        self.window.geometry("800x400")
        self.fullScreenState = True
        self.window.attributes("-fullscreen", self.fullScreenState)
   
        self.window.mainloop()

    def toggleFullScreen(self, event):
        self.fullScreenState = not self.fullScreenState
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen {}".format(self.fullScreenState))

    def quitFullScreen(self, event):
        self.fullScreenState = False
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen quit")

    def set_label_state(self,label, state, message):
        result=False
        color = ('green3' if state else 'orange red')
        if str(label.cget('background')) != color:
            if state:
                self.logger.info("{}".format(message))
                result=True
            else:
                self.logger.error("{}".format(message))
                result=False
        label['background'] = color
        label['text'] = message
        return result

    def set_wifi(self):
        #todo:https://raspberrypi.stackexchange.com/questions/104887/information-about-network-gui-in-raspbian
        self.logger.debug("Wifi Setup called")


    def set_show_plot(self):
        self.logger.debug("Showing Plot")
        plotw = Tk()
        plotw.attributes("-fullscreen", True)
        label = Label(plotw)
        #######
        # The Plot
        #######
        try:
            img = ImageTk.PhotoImage(Image.open("/run/shm/beast_plot.png"),master=plotw) ##resize ??
            label.config(image=img)
            label.img = img
        except Exception as e:
            print("No Plot",e)
        label.pack(side=TOP, pady=10)

        btn = Button(plotw,
                     text="Close",command=plotw.destroy)
        btn.pack(fill=tk.BOTH, ipady=10)
        # mainloop, runs infinitely
        plotw.mainloop()

    def check_internet(self,):
        conn = httplib.HTTPConnection("www.google.com", timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True, "Internet available"
        except:
            conn.close()
            return False, "Internet not available"

    def check_file_write(self,max_time_diff=600):
        path_s = self.path + '*.csv'
        list_of_files = glob.glob(path_s)  # * means all if need specific format then *.csv
        if not list_of_files:
            return False, "No Files found"
        latest_file = max(list_of_files, key=os.path.getctime)
        stat = os.stat(latest_file)
        size = stat.st_size / (1024 * 1024)
        last_write = time.time() - stat.st_mtime
        if last_write > max_time_diff:
            return False, "File {} ist stale ({:.1}MB)".format(os.path.basename(latest_file), size)
        return True, "File {} is written ({:.1}MB)".format(os.path.basename(latest_file), size)

    def check_port_in_use(self,port=8012):
        # result=subprocess.check_output(['lsof', '-i','-P','-n','|','grep',':443'])
        # print(result)
        return True, "Port check Todo"

    def check_received_messages(self):
        path_s = self.path + 'log*.csv'
        list_of_files = glob.glob(path_s)  # * means all if need specific format then *.csv
        if not list_of_files:
            return False, "No message files found"
        latest_file = max(list_of_files, key=os.path.getctime)
        with open(latest_file, 'rb') as f:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
            last_line = f.readline().decode()

        cols = last_line.split(";")
        if int(cols[5]) > 0:
            return True, "Rx Messages: {}".format(cols[5])
        else:
            return False, "No Messages received"

    def check_processrunning(self,processName):
        '''
        Check if there is any running process that contains the given name processName.
        '''
        # Iterate over the all the running process
        for proc in psutil.process_iter():
            try:
                # Check if process name contains the given name string.
                if any(processName in ext for ext in proc.cmdline()) or processName in proc.name():
                    return True, "{} is running {:.1f} days".format(processName,
                                                                                  (time.time() - proc.create_time()) / (
                                                                                              3600 *24))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False, f"{processName} not running"

    def sys_check(self):
        for itm in self.checks:
            state, message = itm['function'](*itm.get('parameter', []))
            self.set_label_state(itm['label'], state, message)
            if state == False:
                self.bad += 1
            else:
                self.bad =0

        if self.bad > 10:
            img=self.take_screenshot()
            with open('piMon.log','r') as f:
                output = f.read()
        self.window.after(10000, self.sys_check)

    def take_screenshot(self):
        path="/run/shm/scrot2.png"
        process = subprocess.Popen("scrot {}".format(path), shell=True, stdout=subprocess.PIPE)
        process.wait()
        return path

if __name__ == '__main__':
    app = GUI()  


