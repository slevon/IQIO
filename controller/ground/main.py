############
#Set working dir
import json
import os
from socket import timeout
from time import sleep

from ground.plotWidget import Plotwindow

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)
#############

import datetime
import random
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

##########
##Serial
import serial


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


class StatIo:
    def __init__(self):
        self.ser = serial.Serial('/dev/ttyUSB0',timeout=0.5)  # open serial port NON-Blocking read
        print(self.ser.name)  # check which port was really used
        self.ser.write(b'1030 Startup')  # write a string

    def __del__(self):
        self.ser.close()  # close port
    def send(self,data):
        self.ser.write(bytearray((data+"\n").encode()))
    def receive_pending(self):
        data=self.ser.readline()
        return data
    def receive_blocking(self):
        to = self.ser.timeout
        self.ser.timeout = 20
        data=self.ser.readline()
        self.ser.timeout = to
        return data

class GUI():
    def __init__(self,is_master=True):
        ###############
        #Variables
        ###############
        self.bad = 0 #mon has a bad state if >0 (number of checks*bad states)
        self.row_count = 8 #widgets rows
        '''
        We have two options here:
            - Master:   - Creates a set of widgets from the constuctor
                        - Runs on the node that is doing the work
                        - Creates a josn opject, that is send using the StatIo Class
            - No Master:- Creates a set of Widgets by requeisting them from the master:
                        - Runs on any Other Machine
                        - retrieves the States to update from the StatIo Class, does not Perform any Checks
                        
        '''
        self.is_master =is_master
        self.io = StatIo()
        self.s_last_results={}
        self.check_names=[]
        self.elements = []

        #######################
        #Logger:
        ######################
        logging.basicConfig(level="DEBUG")
        logging.getLogger('matplotlib.font_manager').disabled = True
        formatter=logging.Formatter('%(asctime)s %(levelname)-6s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        self.logger = logging.getLogger('piMon')
        self.handler = RotatingFileHandler('piMon.log', maxBytes=2000, backupCount=10)
        self.handler.setFormatter(formatter)
        self.logger.addHandler(self.handler)
        self.logger.info('Application: startup')

        self.window = Tk()
        Grid.rowconfigure(self.window, 0, weight=1)
        Grid.columnconfigure(self.window, 0, weight=1)
        #self.window.attributes('-zoomed', True)
        self.window.bind("<F11>", self.toggleFullScreen)
        self.window.bind("<Escape>", self.quitFullScreen)

        self.mainFrame = Frame(self.window)

        self.mainFrame.grid(row=0, column=0, sticky=N+S+E+W)

        #############
        # Settings:
        ############
        self.path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../reader/beastReader/')
        ##############
        #Checks
        if self.is_master:
            #self.checks.append({"name": "port_in_use", "function": self.check_port_in_use})
            self.elements.append({"type": "label", "name": "internet", "function": self.check_internet})
            self.elements.append({"type": "label", "name": "check_dump1090", "function": self.check_processrunning, "parameter": ["dump1090"]})
            self.elements.append({"type": "label", "name": "check_sim", "function": self.check_processrunning, "parameter": ["sim.py"]})
            self.elements.append({"type": "label", "name": "media", "function": self.check_df, "parameter": ["media", "label"]})
            self.elements.append({"type": "plot", "name": "media_plot", "history":30, "function": self.check_df, "parameter": ["media", "plot"]})
            self.elements.append({"type": "label", "name": "check_reader", "function": self.check_processrunning, "parameter": ["beast_reader.py"]})
            self.elements.append({"type": "label", "name": "file_written", "function": self.check_file_write, })
            self.elements.append({"type": "label", "name": "check_messages", "function": self.check_received_messages})
            self.elements.append({"type": "button","name":"Wifi-Setup","function":self.set_wifi})
            self.elements.append({"type": "button","name":"Show Plot","function":self.set_show_plot})
        else: #Slave
            self.elements = self.get_elements() #Gets the Elements from Master
            #Now Add the functions, that must be called by the "Slave"
            for itm in self.elements:
                if itm["type"] in  ["label","plot"]:
                    itm["function"] = lambda n=itm['name']: self.get_state_from_received_data(n) #This n=itm["name" see: https://stackoverflow.com/questions/19837486/lambda-in-a-loop
                elif itm["type"] == "button":
                    itm["function"]=lambda  n=itm['name']: self.request_command(n)
                else:
                    raise ValueError("SLAVE-Mode: Unkown Type >{}< in widget list".format(itm["type"]))
        self.labels = []  # creates an empty list for your labels
        self.plots = []
        self.buttons = []
        for i,itm in enumerate(self.elements):  # iterates over your nums
            r = (i)%self.row_count +1
            c = (i)//self.row_count
            if itm["name"] not in self.check_names:
                self.check_names.append(itm["name"])
            else:
                raise ValueError("Duplicate Name for check! Please create individaul names")
            if itm["type"] == "label":
                label = Label(self.mainFrame, text=itm['name'],anchor="center")  # set your text
                itm['widget'] = label
                label.grid(row=r,column=c, sticky='nswe', padx=5, pady=1)
                self.labels.append(label)  # appends the label to the list for further use
            elif itm["type"] == "plot":
                plot=Plotwindow(self.mainFrame, itm.get('history',10), (10, 10))
                itm['widget'] = plot
                plot.widget.grid(row=r, column=c, sticky='nswe', padx=5, pady=1)
                self.plots.append(plot)
            elif itm['type'] == "button":
                button = Button(self.mainFrame, text=itm['name'],
                                command=itm['function']) #fisrt-case: master , second slave
                itm['widget'] = button
                button.grid(row=r, column=c, sticky='nswe', padx=5, pady=5, ipady=20)
                self.buttons.append(button)

            else:
                print("Error, unkown check type")

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
        self.textLog.grid(row=1, column=1+len(self.elements)//self.row_count, rowspan=self.row_count, columnspan=2, sticky="nsew",
                                     padx=5, pady=1)

        self.text_handler = TextHandler(self.textLog)
        self.text_handler.setFormatter(formatter)
        self.logger.addHandler(self.text_handler)
        #######
        #Plot in Layout:
        #######
        #self.panel.grid(row=len(self.buttons), column=2, rowspan=len(self.labels) - len(self.buttons), sticky="we",
        #                padx=5, pady=1)

        for i in range(0,self.row_count+1):
            self.mainFrame.rowconfigure(i,weight=1)
        for i in range(0,1+len(self.elements)//self.row_count):
            self.mainFrame.columnconfigure(i,weight=1)
        self.mainFrame.columnconfigure(1+len(self.elements)//self.row_count,weight=3)#The textbox
        #######
        #Start
        #######
        self.send_elements()
        self.sys_check()
        #############

        ###########################
        ### Fullscreen
        ############################
        self.window.geometry("1024x768")
        #self.fullScreenState = True
        #self.window.attributes("-fullscreen", self.fullScreenState)

        self.window.mainloop()

    def toggleFullScreen(self, event):
        self.fullScreenState = not self.fullScreenState
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen {}".format(self.fullScreenState))

    def quitFullScreen(self, event):
        self.fullScreenState = False
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen quit")

    def stingify_elements(self):
        data={"elements":[]}
        export = self.elements.copy()
        for item in export:
            itm=item.copy()
            del itm["function"]
            del itm["widget"]
            try:
                del itm["parameter"]
            except Exception:
                pass
            data['elements'].append(itm)
        return json.dumps(data)
    def get_elements(self):
        i=0
        while True:
            i+=1
            self.logger.info("Requesting Masters Config. This may take a while....")
            try:
                self.request_command("init")
                sleep(5)
                obj = json.loads(self.receive_blocking())
            except:
                self.logger.error("Error retrieving Masters Config. Retrying. {}".format(i))
                sleep(5)

        return obj["elements"]
    def send_elements(self):
        '''
        Sends the GUI Elements over IO
        This function is only called in the Master mode.
        :return:
        '''
        self.io.send(self.stingify_elements())


    def request_command(self,command_name):
        '''
        This function is only called in the Slave mode.
        :param button_name:
        :return:
        '''
        print("REQUESTING Command {}".format(command_name))
        self.logger.info("Transmitting Command Request: {}".format(command_name))
        self.io.send(json.dumps({"command":command_name}))

    def get_state_from_received_data(self,widget_name):
        '''
              This function is only called in the Slave mode.
        '''
        #print("Getting Data from the Masters Data >{}".format(widget_name))
        if widget_name not in self.s_last_results:
            return False,"N/A"
        return  self.s_last_results[widget_name]["state"],self.s_last_results[widget_name]["result"]


    def do_IO(self):
        '''
        Dependent on self.is_master This funktion either sends the current state, or receives from the master.
        Secondly, in case of Master ifd handels requests from the slave:
        :return:
        '''

        if self.is_master:
            #Gather the current UI state
            ui_state={}
            for itm in self.elements:
                if itm["type"] == "label":
                    if "green" in str(itm["widget"].cget('background'))  :
                        state=True
                    else:
                        state=False
                    ui_state[itm["name"]]={"state":state
                                            ,"result":itm["widget"].cget("text")}

                elif itm["type"] == "plot":
                    ui_state[itm["name"]] = {"state": True
                                            , "result": itm["widget"].getLast()}
            #TODO: hier noch mehr zusammen sammeln und dan versenden
            self.io.send(json.dumps(ui_state))

            ###################
            ##Handle Incomming Commands
            rcv=self.io.receive_pending()
            try:
                obj=json.loads(rcv)
                if obj["command"] == "init":
                    self.send_elements()
                else:
                    for itm in self.buttons:
                        if itm["name"]== obj["command"]:
                            itm["function"]() #Call the Funktions
            except:
                self.logger.error("Bad formatted incomming command {}".format(rcv))

        else:
            #TODO, hier ggf. ein subelement, für die GUI Sachen .
            data=self.io.receive_pending()
            try:
                self.s_last_results=json.loads(data)
            except:
                print("Non Parseable Serial string",data)
                self.s_last_results={}



    def sys_check(self):
        '''
        In case of MAster, the class functions are called.
        In Case of slve the get_state_from_received_data funcktion is called.
        :return:
        '''
        for itm in self.elements:
            if itm['type'] in ["label","plot"]:
                state, result = itm['function'](*itm.get('parameter', []))
                self.update_widget_state(itm['widget'],itm['type'], state, result)

        ###
        #Execute IO Things
        self.do_IO()

        self.window.after(10000, self.sys_check)


    def update_widget_state(self,widget,type, state, result_value):
        result = False
        if type == "label":
            color = ('green3' if state else 'orange red')
            if str(widget.cget('background')) != color:
                if state:
                    self.logger.info("{}".format(result_value))
                    result=True
                else:
                    self.logger.error("{}".format(result_value))
                    result=False
            widget['background'] = color
            widget['text'] = result_value
        elif type == "plot":
            if state == True:
                widget.append(result_value)
        else:
            self.logger.error("Unknown widget type could not be updated")
        return result_value
#################################################################################################################
#################################################################################################################
#################################################################################################################
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

    def check_df(self,grep_filter="media",return_type="label"):
        #result=subprocess.check_output(['df', '-h','|','grep',grep_filter])
        cmd="df -BG | grep {}".format(grep_filter)
        ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = ps.communicate()[0]
        #Parse:
        elements=output.split()
        if len(elements) != 6:
            print("Error DF!",len(elements),return_type)
            print(elements)
            return False, "DF Check failed!"

        #If less than 10GB left, turn into red...
        freeGb=int(elements[3].decode()[:-1])
        if freeGb < 10:
            result=False
        else:
            result=True

        if return_type == "label":
            return result, "{} {}:\n  use: {} {},".format(elements[0].decode(),elements[1].decode(),elements[2].decode(),elements[4].decode())
        elif return_type == "plot":
            #return True,  #free GB
            return True, int(random.randint(0,22)) #free GB
        return False, "Error"

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
                                                (time.time() - proc.create_time()) / (3600 *24))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False, f"{processName} not running"



    def take_screenshot(self):
        path="/run/shm/scrot2.png"
        process = subprocess.Popen("scrot {}".format(path), shell=True, stdout=subprocess.PIPE)
        process.wait()
        return path

if __name__ == '__main__':
    app = GUI(is_master=True)


