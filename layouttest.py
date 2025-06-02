import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from PIL import Image, ImageTk

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Generated Layout - Canvas 2')
        self.geometry('386x790')

        self._image_references_generated_app = [] 

        self.item_1 = tk.Button(self, text='Button', font=('Yu Gothic UI', 9, ''), fg='SystemButtonText', background='SystemButtonFace')
        self.item_1.place(x=142, y=280)


if __name__ == '__main__':
    app = App()
    app.mainloop()