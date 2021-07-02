import tkinter as tk
import matplotlib
import matplotlib as plt
from matplotlib.figure import Figure

plt.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class Plotwindow():
    def __init__(self, masterframe,title, history, size):
        (w,h)=size
        inchsize=(w/25.4, h/25.4)
        self.figure = Figure(inchsize)
        self.figure.tight_layout()
        self.figure.suptitle(title,fontsize=10)
        self.axes = self.figure.add_subplot(111)
        self.history = history
        self.data=[0]
        self.indices=[0]
        # create canvas as matplotlib drawing area
        #
        self.canvas = FigureCanvasTkAgg(self.figure, master=masterframe)
        self.widget=self.canvas.get_tk_widget()
    def plotxy(self, x, y):
        self.axes.plot(x,y)
        #self.figure.tight_layout()

        self.canvas.draw()

    def append(self,y):
        self.data.append(y)
        self.indices.append(self.indices[-1] + 1)
        self.axes.cla()
        #self.axes.grid(True)
        if len(self.data)>self.history:
            del self.data[0]
            del self.indices[0]
        self.axes.plot(self.indices,self.data)
        # self.figure.tight_layout()
        try:
            self.figure.tight_layout()
        except:
            pass
        self.canvas.draw()

    def getLast(self):
        return self.data[-1]

    def clearplot(self):
        self.axes.cla()
        self.axes.grid(True)
        #self.axes.autoscale(True)
        self.canvas.draw()