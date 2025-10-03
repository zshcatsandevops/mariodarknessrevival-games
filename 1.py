import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class MariOS64Modder(tk.Tk):
    """
    A GUI application for modding Super Mario 64, inspired by the cancelled MariOS 64.
    This is a prototype and does not perform actual ROM hacking.
    """
    def __init__(self):
        super().__init__()
        self.title("Flames Co. MariOS Darkness build 10325")
        self.geometry("800x600")
        self.configure(bg="#2E2E2E")
        self.rom_path = None

        # --- Style Configuration ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('.', background="#2E2E2E", foreground="white", fieldbackground="#4A4A4A", bordercolor="#555555")
        self.style.configure('TNotebook', background='#2E2E2E', borderwidth=0)
        self.style.configure('TNotebook.Tab', background='#4A4A4A', foreground='white', padding=[10, 5], borderwidth=0)
        self.style.map('TNotebook.Tab', background=[('selected', '#3C3C3C')])
        self.style.configure('TFrame', background='#3C3C3C')
        self.style.configure('TButton', background='#5A5A5A', foreground='white', padding=6, relief='flat')
        self.style.map('TButton', background=[('active', '#6A6A6A')])
        self.style.configure('TLabel', background='#3C3C3C', foreground='white', font=('Segoe UI', 10))
        self.style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
        self.style.configure('TEntry', fieldbackground="#4A4A4A", foreground="white", insertbackground="white")
        self.style.configure('TSpinbox', fieldbackground="#4A4A4A", foreground="white", insertbackground="white")

        self._create_widgets()

    def _create_widgets(self):
        # --- Top Frame for File Operations ---
        top_frame = ttk.Frame(self, padding="10")
        top_frame.pack(fill='x', side='top')

        self.rom_label = ttk.Label(top_frame, text="No ROM Loaded", font=('Segoe UI', 9), style='TLabel')
        self.rom_label.pack(side='left', padx=(0, 10))

        self.open_button = ttk.Button(top_frame, text="Open SM64 ROM", command=self.open_rom)
        self.open_button.pack(side='left')
        
        self.save_button = ttk.Button(top_frame, text="Save Modded ROM", command=self.save_rom, state='disabled')
        self.save_button.pack(side='left', padx=5)

        # --- Main Notebook for Modding Categories ---
        notebook = ttk.Notebook(self, padding="10")
        notebook.pack(expand=True, fill='both')

        player_frame = self._create_player_tab()
        level_frame = self._create_level_tab()
        texture_frame = self._create_texture_tab()

        notebook.add(player_frame, text='Player Mods')
        notebook.add(level_frame, text='Level Editor')
        notebook.add(texture_frame, text='Texture Importer')

        # --- Status Bar ---
        self.status_bar = ttk.Label(self, text="Welcome to MariOS 64 Modder", anchor='w', padding=5)
        self.status_bar.pack(side='bottom', fill='x')

    def _create_player_tab(self):
        frame = ttk.Frame(padding="20")
        ttk.Label(frame, text="Mario Character Properties", style='Header.TLabel').pack(pady=(0, 20), anchor='w')

        # --- Cap Color ---
        ttk.Label(frame, text="Mario's Cap Color:").pack(anchor='w', pady=(0, 5))
        self.cap_color = tk.StringVar(value='Red')
        cap_options = ['Red', 'Green (Luigi)', 'Blue (Wario)', 'Yellow']
        cap_menu = ttk.OptionMenu(frame, self.cap_color, self.cap_color.get(), *cap_options)
        cap_menu.pack(fill='x', pady=(0, 15))

        # --- Infinite Lives ---
        self.infinite_lives = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Infinite Lives", variable=self.infinite_lives).pack(anchor='w', pady=(0, 15))

        # --- Health Modifier ---
        ttk.Label(frame, text="Max Health (Wedges):").pack(anchor='w', pady=(0, 5))
        self.max_health = tk.IntVar(value=8)
        ttk.Spinbox(frame, from_=1, to=16, textvariable=self.max_health, width=10).pack(anchor='w', pady=(0, 25))

        apply_button = ttk.Button(frame, text="Apply Player Mods", command=self.apply_player_mods)
        apply_button.pack(anchor='w')
        
        return frame

    def _create_level_tab(self):
        frame = ttk.Frame(padding="20")
        ttk.Label(frame, text="Level & Star Editor", style='Header.TLabel').pack(pady=(0, 20), anchor='w')
        
        ttk.Label(frame, text="This is a conceptual placeholder for level editing features.").pack(anchor='w')
        
        return frame

    def _create_texture_tab(self):
        frame = ttk.Frame(padding="20")
        ttk.Label(frame, text="Custom Texture Importer", style='Header.TLabel').pack(pady=(0, 20), anchor='w')
        
        ttk.Label(frame, text="This feature would allow replacing in-game textures.").pack(anchor='w', pady=(0,10))
        
        import_button = ttk.Button(frame, text="Import Texture...", command=self.import_texture)
        import_button.pack(anchor='w')
        
        return frame

    def open_rom(self):
        path = filedialog.askopenfilename(
            title="Select Super Mario 64 ROM",
            filetypes=(("N64 ROMs", "*.z64 *.n64"), ("All files", "*.*"))
        )
        if path:
            self.rom_path = path
            filename = path.split('/')[-1]
            self.rom_label.config(text=f"Loaded: {filename}")
            self.status_bar.config(text=f"Successfully loaded {filename}")
            self.save_button.config(state='normal')
            messagebox.showinfo("ROM Loaded", f"'{filename}' has been loaded into the program.")

    def save_rom(self):
        if not self.rom_path:
            messagebox.showerror("Error", "No ROM file is currently loaded.")
            return
        
        messagebox.showinfo("Save ROM", "This is a placeholder. In a real application, the modified ROM would be saved here.")
        self.status_bar.config(text="Modded ROM saved (simulation).")

    def apply_player_mods(self):
        if not self.rom_path:
            messagebox.showwarning("Warning", "Please load a ROM before applying mods.")
            return

        cap = self.cap_color.get()
        lives = "Infinite" if self.infinite_lives.get() else "Default"
        health = self.max_health.get()

        info_message = (
            f"Applying Player Mods:\n\n"
            f" - Cap Color set to: {cap}\n"
            f" - Lives set to: {lives}\n"
            f" - Max Health Wedges: {health}\n\n"
            f"(This is a simulation. No changes were made to the ROM.)"
        )
        messagebox.showinfo("Applying Mods", info_message)
        self.status_bar.config(text="Player mods applied (simulation).")
        
    def import_texture(self):
        messagebox.showinfo("Import Texture", "This is a placeholder for the texture import functionality.")


if __name__ == "__main__":
    app = MariOS64Modder()
    app.mainloop()
