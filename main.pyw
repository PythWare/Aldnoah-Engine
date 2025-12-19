# main.pyw
import os
import tkinter as tk
from Aldnoah_Logic import Core_Tools

"""Main script the user will use to call other scripts"""

def main():
    # make double click launches behave consistently
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    root = tk.Tk()
    app = Core_Tools(root)
    root.mainloop()

if __name__ == "__main__":
    main()
