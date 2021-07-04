#!/usr/bin/env python

############
# Set working dir
import argparse
import json
import os
from socket import timeout
from time import sleep
from tkinter import ttk

from plotWidget import Plotwindow

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
import serial.tools.list_ports
import zlib  # used for crc32

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
            tag = ""
            try:
                tag = msg.split(" ")[2]
            except:
                pass
            self.text.configure(state='normal')
            self.text.insert(END, msg + '\n', tag)
            self.text.configure(state='disabled')
            # Autoscroll to the bottom
            self.text.yview(END)

        # This is necessary because we can't modify the Text from other threads
        self.text.after(0, append)


##################################################################################################################
##################################################################################################################
##################################################################################################################
class StatIo:
    def __init__(self, port, crc=True):
        self.connected = False
        self.check_crc = crc
        try:
            self.ser = serial.Serial(port, timeout=0.5)  # open serial port NON-Blocking read
            if self.ser.is_open:
                self.connected = True
                print("Port Open")  # check which port was really used
        except Exception as e:
            self.connected = False
            print("IO Excpetion in connection {} {}".format(port, self), e)

    def setCrcCheck(self, enable=True):
        self.check_crc = enable

    def setCompression(self, enable=True):
        self.compression = enable

    def __del__(self):
        if self.connected:
            self.ser.close()  # close port

    def send(self, data):
        if self.connected:
            tbsent = (data + self.getCrc(data, from_to_string=True)).encode()
            self.ser.write(tbsent + b'\n')
            return True
        else:
            return False

    def receive_pending(self):
        payload = ""
        if self.connected:
            data = self.ser.readline()
            if len(data) > 8:
                if self.check_crc:
                    payload = data[:-9]
                    crc = data[-9:-1]  # cuutout crc
                    if self.getCrc(payload) != crc:
                        raise ValueError("CRC Error in Data")
                else:
                    payload = data
        return payload

    def receive_blocking(self):
        if self.connected:
            to = self.ser.timeout
            self.ser.timeout = 20
            data = self.ser.readline()
            self.ser.timeout = to
            return data
        return ""

    def getCrc(self, data, from_to_string=False):
        '''
        Data is assumed to be a bytarray
        :param data:
        :return:
        '''
        if from_to_string:
            crc = "{:08x}".format(zlib.crc32(data.encode()))
        else:
            crc = "{:08x}".format(zlib.crc32(data)).encode()
        return crc


##################################################################################################################
##################################################################################################################
##################################################################################################################
class GUI():
    def __init__(self, is_slave=True, port="/dev/ttyUSB0"):
        self.window = Tk()
        # Import the tcl file
        # see: https://github.com/rdbende/Azure-ttk-theme
        self.window.tk.call('source', 'themes/azure-dark.tcl')
        self.window.tk.call('source', 'themes/azure.tcl')
        # Set the theme with the theme_use method
        ttk.Style().theme_use('azure')
        self.theme_dark = False
        # ttk.Style().theme_use('azure-dark')
        self.window.title('Control: {}'.format("Slave" if is_slave else "Master"))
        Grid.rowconfigure(self.window, 0, weight=1)
        Grid.columnconfigure(self.window, 0, weight=1)
        # self.window.attributes('-zoomed', True)
        self.window.bind("<F11>", self.toggleFullScreen)
        self.window.bind("<Escape>", self.quitFullScreen)
        self.mainFrame = Frame(self.window)

        self.mainFrame.grid(row=0, column=0, sticky=N + S + E + W)
        # cbB=Checkbutton( self.mainFrame, text='Theme ', style='Switch', variable=self.theme_dark,command=self.toggle_theme)
        cbB = Checkbutton(self.mainFrame, text='Theme ', style='ToggleButton', variable=self.theme_dark,
                          command=self.toggle_theme)
        cbB.grid(row=0, column=3, sticky="e")
        #######################
        # Logger:
        ######################
        logging.basicConfig(level="DEBUG")
        logging.getLogger('matplotlib.font_manager').disabled = True
        formatter = logging.Formatter('%(asctime)s %(levelname)-6s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        self.logger = logging.getLogger('piMon')
        self.handler = RotatingFileHandler('piMon.log', maxBytes=2e6, backupCount=3)
        self.handler.setFormatter(formatter)
        self.logger.addHandler(self.handler)
        ######
        # Logger GUI:
        #######
        self.textLog = ScrolledText(self.mainFrame, state="disabled")
        self.textLog.configure(font='TkFixedFont')
        self.textLog.tag_config('INFO', foreground='black')
        self.textLog.tag_config('DEBUG', foreground='gray')
        self.textLog.tag_config('WARNING', foreground='orange')
        self.textLog.tag_config('ERROR', foreground='red')
        self.textLog.tag_config('CRITICAL', foreground='red', underline=1)
        self.text_handler = TextHandler(self.textLog)
        self.text_handler.setFormatter(formatter)
        self.logger.addHandler(self.text_handler)
        # Will be added into the GUI Later!

        self.logger.info('Application: startup')

        ###############
        # Variables
        ###############
        self.bad = 0  # mon has a bad state if >0 (number of checks*bad states)
        self.row_count = 8  # widgets rows
        '''
        We have two options here:
            - Master:   - Creates a set of widgets from the constuctor
                        - Runs on the node that is doing the work
                        - Creates a josn opject, that is send using the StatIo Class
            - No Master:- Creates a set of Widgets by requeisting them from the master:
                        - Runs on any Other Machine
                        - retrieves the States to update from the StatIo Class, does not Perform any Checks

        '''
        self.is_slave = is_slave
        self.io = StatIo(port)
        if not self.io.connected:
            if self.is_slave:
                print("Error in connection to port {}\nExiting\n\n".format(port))
                sys.exit(-1)
            else:
                self.logger.warning("Could not connect to Serial-Port: {}\n\t\tSlaves will be blind.".format(port))
        else:
            self.logger.info("Port {} connected".format(port))
        self.s_last_results = {}
        self.check_names = []
        self.elements = []

        #############
        # Settings:
        ############
        self.path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../reader/beastReader/')
        ##############
        # Checks
        if self.is_slave:
            self.elements = self.get_elements()  # Gets the Elements from Master
            # Now Add the functions, that must be called by the "Slave"
            for itm in self.elements:
                if itm["type"] in ["label", "plot"]:
                    itm["function"] = lambda n=itm['name']: self.get_state_from_received_data(
                        n)  # This n=itm["name" see: https://stackoverflow.com/questions/19837486/lambda-in-a-loop
                elif itm["type"] == "button":
                    itm["function"] = lambda n=itm['name']: self.request_command(n)
                else:
                    raise ValueError("SLAVE-Mode: Unkown Type >{}< in widget list".format(itm["type"]))
                    # self.checks.append({"name": "port_in_use", "function": self.check_port_in_use})
        else:  # Master
            self.elements.append({"type": "button", "name": "Wifi-Setup", "function": self.set_wifi})
            self.elements.append({"type": "button", "name": "Show Plot", "function": self.set_show_plot})
            self.elements.append({"type": "label", "name": "self", "function": self.check_self})
            self.elements.append({"type": "label", "name": "internet", "function": self.check_internet})
            self.elements.append({"type": "label", "name": "check_samplesToFile", "function": self.check_processrunning,
                                  "parameter": ["samplesToFile"]})
            self.elements.append({"type": "plot", "name": "Disk Queue", "function": self.plot_queue, })
            self.elements.append({"type": "label", "name": "media", "function": self.check_df, "parameter": ["media", "label"]})
            self.elements.append({"type": "plot", "name": "media_plot", "history": 30, "function": self.check_df,
                                  "parameter": ["media", "plot"]})
            self.elements.append({"type": "label", "name": "check_reader", "function": self.check_processrunning,
                                  "parameter": ["beast_reader.py"]})
            self.elements.append({"type": "label", "name": "file_written", "function": self.check_file_write, })
            self.elements.append({"type": "label", "name": "rate", "function": self.check_rate, })
            self.elements.append({"type": "label", "name": "overflow_label", "function": self.check_overflow, })
            self.elements.append({"type": "plot", "name": "Overflow", "function": self.plot_overflow, })
            self.elements.append({"type": "plot", "name": "Peak", "function": self.plot_peak })
            self.elements.append({"type": "label", "name": "clipping", "function": self.check_clipping})

        self.labels = []  # creates an empty list for your labels
        self.plots = []
        self.buttons = []
        rowcnt = 0
        for i, itm in enumerate(self.elements):  # iterates over your nums
            r = (rowcnt) % self.row_count + 1
            c = ((rowcnt) // self.row_count) +2
            rowcnt += 1  ##Plot will always be tow rows high
            if itm["name"] not in self.check_names:
                self.check_names.append(itm["name"])
            else:
                raise ValueError("Duplicate Name for check! Please create individaul names")
            if itm["type"] == "label":
                label = Label(self.mainFrame, text=itm['name'], anchor="center")  # set your text
                itm['widget'] = label
                label.grid(row=r, column=c, sticky='nswe', padx=5, pady=1)
                self.labels.append(label)  # appends the label to the list for further use
            elif itm["type"] == "plot":
                plot = Plotwindow(self.mainFrame, itm["name"], itm.get('history', 10), (10, 10))
                itm['widget'] = plot
                plot.widget.grid(row=r, column=c, rowspan=2, sticky='nswe', padx=5, pady=1)
                self.plots.append(plot)
                rowcnt += 1
            elif itm['type'] == "button":
                button = Button(self.mainFrame, text=itm['name'],
                                command=itm['function'])  # fisrt-case: master , second slave
                itm['widget'] = button
                button.grid(row=r, column=c, sticky='nswe', padx=5, pady=5, ipady=5)
                self.buttons.append(button)

            else:
                print("Error, unkown check type")

        ##Embedd the Logger into the GUI!
        self.textLog.grid(row=1, column=0, rowspan=self.row_count, columnspan=2,
                          sticky="nsew",
                          padx=5, pady=1)

        #######
        # Plot in Layout:
        #######
        # self.panel.grid(row=len(self.buttons), column=2, rowspan=len(self.labels) - len(self.buttons), sticky="we",
        #                padx=5, pady=1)

        for i in range(0, self.row_count + 1):
            self.mainFrame.rowconfigure(i, weight=1)
        for i in range(0, (len(self.elements) // self.row_count)+2):
            self.mainFrame.columnconfigure(i+2, weight=1)
        self.mainFrame.columnconfigure(0, weight=0)  # The textbox
        self.mainFrame.columnconfigure(1, weight=0)  # The textbox
        #######
        # Start
        #######
        if not self.is_slave:
            self.handle_command_requests()
        self.sys_check()
        #############

        ###########################
        ### Fullscreen
        ############################
        self.window.geometry("1024x768")
        # self.fullScreenState = True
        # self.window.attributes("-fullscreen", self.fullScreenState)

        self.window.mainloop()

    def toggle_theme(self):
        print("theme change")
        self.theme_dark = not self.theme_dark
        if self.theme_dark:
            ttk.Style().theme_use('azure-dark')
            self.textLog.config(bg='#A0A0A0')
        else:
            ttk.Style().theme_use('azure')
            self.textLog.config(bg='#FFFFFF')

    def toggleFullScreen(self, event):
        self.fullScreenState = not self.fullScreenState
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen {}".format(self.fullScreenState))

    def quitFullScreen(self, event):
        self.fullScreenState = False
        self.window.attributes("-fullscreen", self.fullScreenState)
        self.logger.debug("Fullscreen quit")

    def stingify_elements(self):
        data = {"elements": []}
        export = self.elements.copy()
        for item in export:
            itm = item.copy()
            del itm["function"]
            del itm["widget"]
            try:
                del itm["parameter"]
            except Exception:
                pass
            data['elements'].append(itm)
        return json.dumps(data)

    def get_elements(self):
        i = 0
        while True:
            i += 1
            self.logger.info("Requesting Masters Config. This may take a while....")
            try:
                self.request_command("init")
                sleep(5)
                obj = json.loads(self.io.receive_pending())
                return obj["elements"]
            except Exception as e:
                self.logger.error("Error retrieving Masters Config. Retrying. {} {}".format(i, e))
                sleep(5)
        return None

    def send_elements(self):
        '''
        Sends the GUI Elements over IO
        This function is only called in the Master mode.
        :return:
        '''
        self.logger.info("Sending all Elements.")
        self.io.send(self.stingify_elements())

    def handle_command_requests(self):
        '''
        Executed by Master only: Check if commands are send from the slave:
        :return:
        '''
        ###################
        ##Handle Incomming Commands
        rcv = ""
        try:
            rcv = self.io.receive_pending()
        except Exception as e:
            self.logger.warning("Reception Error {}".format(e))
        if rcv != "":
            try:
                obj = json.loads(rcv)
                self.logger.debug("Command received: {}".format(obj["command"]))
                if obj["command"] == "init":
                    self.send_elements()
                else:
                    for itm in self.elements:
                        if itm["type"] == "button":
                            if itm["name"] == obj["command"]:
                                itm["function"]()  # Call the Funktions
            except Exception as e:
                self.logger.error("Bad formatted incomming command {}".format(rcv))
                print("Command receive", e)

        self.window.after(1000, self.handle_command_requests)

    def request_command(self, command_name):
        '''
        This function is only called in the Slave mode.
        :param button_name:
        :return:
        '''
        self.logger.info("Transmitting Command Request: {}".format(command_name))
        self.io.send(json.dumps({"command": command_name}))

    def get_state_from_received_data(self, widget_name):
        '''
              This function is only called in the Slave mode.
        '''
        # print("Getting Data from the Masters Data >{}".format(widget_name))
        if widget_name not in self.s_last_results:
            return False, "N/A"
        return self.s_last_results[widget_name]["state"], self.s_last_results[widget_name]["result"]

    def send_and_receive_states(self):
        '''
        Dependent on self.is_slave This funktion either sends the current state, or receives from the master.
        Secondly, in case of Master ifd handels requests from the slave:
        :return:
        '''
        if self.is_slave:
            rcv = ""
            try:
                rcv = self.io.receive_pending()
            except Exception as e:
                self.logger.warning("Error in receiving states from master >{}<".format(e))
            if len(rcv) > 3:  ##Data received
                try:
                    self.s_last_results = json.loads(rcv)
                except Exception as e:
                    self.logger.warning("States Error Data >{}<".format(e))
                    self.s_last_results = {}
            else:
                self.logger.warning("No Data received from Master")
                self.s_last_results = {}
        else:
            # Gather the current UI state
            ui_state = {}
            for itm in self.elements:
                if itm["type"] == "label":
                    if "green" in str(itm["widget"].cget('background')):
                        state = True
                    else:
                        state = False
                    ui_state[itm["name"]] = {"state": state
                        , "result": itm["widget"].cget("text")}

                elif itm["type"] == "plot":
                    ui_state[itm["name"]] = {"state": True
                        , "result": itm["widget"].getLast()}
            # TODO: hier noch mehr zusammen sammeln und dann versenden
            self.io.send(json.dumps(ui_state))
            self.logger.debug("Sent States Data to Port")

    def sys_check(self):
        '''
        In case of MAster, the class functions are called.
        In Case of slve the get_state_from_received_data funcktion is called.
        :return:
        '''
        for itm in self.elements:
            if itm['type'] in ["label", "plot"]:
                state, result = itm['function'](*itm.get('parameter', []))
                self.update_widget_state(itm['widget'], itm['type'], state, result)

        ###
        # Execute IO Things for slave/Master modes
        self.send_and_receive_states()

        self.window.after(10000, self.sys_check)

    def update_widget_state(self, widget, type, state, result_value):
        result = False
        if type == "label":
            color = ('green3' if state else 'orange red')
            if str(widget.cget('background')) != color:
                if state:
                    self.logger.info("OK: {}".format(result_value))
                    result = True
                else:
                    self.logger.error("NOK: {}".format(result_value))
                    result = False
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
        # todo:https://raspberrypi.stackexchange.com/questions/104887/information-about-network-gui-in-raspbian
        self.logger.debug("Wifi Setup called")

    def set_show_plot(self):
        self.logger.debug("Showing Plot")

    ###################################################################################################################
    ###################################################################################################################
    ###################################################################################################################

    def check_self(self):
        if self.io.connected:
            return True, "Port Connected"
        # TODO More selftests
        return False, "Selftest failed"

    def check_internet(self, ):
        conn = httplib.HTTPConnection("www.google.com", timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True, "Internet available"
        except:
            conn.close()
            return False, "Internet not available"

    def check_file_write(self, max_time_diff=600):
        path_s = self.path + '*.dat'
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

    def check_df(self, grep_filter="media", return_type="label"):
        # result=subprocess.check_output(['df', '-h','|','grep',grep_filter])
        cmd = "df -BG | grep {}".format(grep_filter)
        ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = ps.communicate()[0]
        # Parse:
        elements = output.split()
        if len(elements) != 6:
            print("Error DF!", len(elements), return_type)
            print(elements)
            return False, "DF Check failed!"

        # If less than 10GB left, turn into red...
        freeGb = int(elements[3].decode()[:-1])
        if freeGb < 10:
            result = False
        else:
            result = True

        if return_type == "label":
            return result, "{} {}:\n  use: {} {},".format(elements[0].decode(), elements[1].decode(),
                                                          elements[2].decode(), elements[4].decode())
        elif return_type == "plot":
            # return True,  #free GB
            return True, int(random.randint(0, 22))  # free GB
        return False, "Error"

    def _get_file_line(self, file, field_name=None):
        '''
               :param field_name:  If None ist specified, all Field will be returned
               :return:
               '''
        with open(file, 'rb') as f:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
            last_line = f.readline().decode()

        cols = last_line.split(",")
        if len(cols) > 2:
            if field_name:
                for idx, itm in enumerate(cols):
                    if field_name in itm:
                        return itm.split(":")[-1]
            else:
                return cols
        else:
            return None

    def check_clipping(self):
        '''
        :return:
        '''
        # path_s = self.path + 'log*.csv'
        # list_of_files = glob.glob(path_s)  # * means all if need specific format then *.csv
        # if not list_of_files:
        #    return False, "No Logs found"
        # latest_file = max(list_of_files, key=os.path.getctime)

        data = self._get_file_line("/home/slevon/Desktop/test.log", "clipp")
        retString = "Rx-Clipping: {}".format(data)
        try:
            if int(data) == 0:
                return True, retString
            else:
                return False, retString
        except:
            pass
        return False, retString

    def plot_peak(self):
        data = float(self._get_file_line("/home/slevon/Desktop/test.log", "peak"))/32767
        data2 = float(self._get_file_line("/home/slevon/Desktop/test.log", "peak_tot"))/32767

        return True, (data,data2)

    def plot_queue(self):
        data = self._get_file_line("/home/slevon/Desktop/test.log", "queue")
        try:
            return True, int(data)
        except:
            return False, 0

    def check_rate(self):
        data = self._get_file_line("/home/slevon/Desktop/test.log", "rate")
        try:
            return True, "Rate: {} MSPS".format(data)
        except:
            return False, "Rate: ?? MSPS"
    def check_overflow(self):
        data = self._get_file_line("/home/slevon/Desktop/test.log", "ovf")
        retString = "Buffer Overflow: {}".format(data)
        try:
            if int(data) == 0:
                return True, retString
            else:
                return False, retString
        except:
            pass

        return False, retString
    def plot_overflow(self):
        data = self._get_file_line("/home/slevon/Desktop/test.log", "ovf_tot")
        if data is not None:
            return True,float(data)
        else:
            return False,""

    def check_processrunning(self, processName):
        '''
        Check if there is any running process that contains the given name processName.
        '''
        # Iterate over the all the running process
        for proc in psutil.process_iter():
            try:
                # Check if process name contains the given name string.
                if any(processName in ext for ext in proc.cmdline()) or processName in proc.name():
                    return True, "{}\nis running {:.1f} mins".format(processName,
                                                                     (time.time() - proc.create_time()) / (60))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False, f"{processName}\nnot running"

    def take_screenshot(self):
        path = "/run/shm/scrot2.png"
        process = subprocess.Popen("scrot {}".format(path), shell=True, stdout=subprocess.PIPE)
        process.wait()
        return path


if __name__ == '__main__':
    ########################################
    # Parse the command line arguments
    ########################################
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', "--slave", action='store_true',
                        help="start Controller in Slave mode (Running on the Ground Station)")
    parser.add_argument('-l', '--list', action='store_true', help="List avialable devices and exit")
    parser.add_argument('-p', '--port', help="sets UART Port", type=str, default="/dev/ttyUSB0")
    args = parser.parse_args()
    if args.list:
        ports = serial.tools.list_ports.comports(include_links=False)
        for port in ports:
            print(port.device)
        sys.exit(0)

    app = GUI(is_slave=args.slave, port=args.port)


