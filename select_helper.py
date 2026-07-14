import sys
import json
import tkinter as tk
from tkinter import filedialog

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'files'
    try:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        
        if mode == 'folder':
            folder_path = filedialog.askdirectory(title="Chọn thư mục")
            root.destroy()
            print(json.dumps(folder_path or ""))
        else:
            file_paths = filedialog.askopenfilenames(
                title="Chọn các file video",
                filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.flv *.ts"), ("All files", "*.*")]
            )
            root.destroy()
            print(json.dumps(list(file_paths)))
    except Exception as e:
        print(json.dumps("" if mode == 'folder' else []))

if __name__ == '__main__':
    main()
