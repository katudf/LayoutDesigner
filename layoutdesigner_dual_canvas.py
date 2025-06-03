import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import json
import tkinter.font as tkfont
from tkinter import colorchooser
from PIL import Image, ImageTk
import tkinter.messagebox

class LayoutDesigner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GUI Layout Designer (Dual Canvas)")
        # 初期サイズを変数で保持
        self.initial_width = 1200
        self.initial_height = 800
        self.geometry(f"{self.initial_width}x{self.initial_height}")

        # --- State Variables ---
        # Most state variables will be lists, one entry per canvas
        self.num_canvases = 2
        self.active_canvas_idx = 0 # 0 for left, 1 for right

        self._dragged_item_id = [None] * self.num_canvases
        self._drag_start_x = [0] * self.num_canvases
        self._drag_start_y = [0] * self.num_canvases
        self._drag_selected_items_start_bboxes = [{} for _ in range(self.num_canvases)]

        self.highlight_rects = [{} for _ in range(self.num_canvases)]
        self.grid_spacing = 20 # Shared grid spacing, could be per-canvas if needed
        self.prop_grid_size = tk.IntVar(value=self.grid_spacing)
        self.canvas_items = [[] for _ in range(self.num_canvases)]
        
        self.selected_item_ids = [set() for _ in range(self.num_canvases)]
        # self.selected_widget and self.selected_item_info will refer to the active canvas's selection
        self.selected_widget = None 
        self.selected_item_info = None 

        self.RESIZE_HANDLE_SIZE = 10
        self.RESIZE_HANDLE_TAG_PREFIX = "rh_"
        self.ALL_RESIZE_HANDLES_TAG = "all_resize_handles" # Will need to be canvas-specific if tags are global
        self.HANDLE_CURSORS = {
            'nw': 'size_nw_se', 'n': 'sb_v_double_arrow', 'ne': 'size_ne_sw',
            'w':  'sb_h_double_arrow', 'e': 'sb_h_double_arrow',
            'sw': 'size_ne_sw', 's': 'sb_v_double_arrow', 'se': 'size_nw_se',
        }
        self.active_resize_handle = [None] * self.num_canvases # Per canvas
        self.resize_start_mouse_x = [0] * self.num_canvases
        self.resize_start_mouse_y = [0] * self.num_canvases
        self.resize_start_item_bbox = [None] * self.num_canvases
        self.resize_original_pil_image = [None] * self.num_canvases
        self._updating_font_properties_internally = False
        self._updating_properties_internally = False

        # --- Style Definitions for Anchor Buttons ---
        self.selected_anchor_style_name = "SelectedAnchor.TButton"
        self.default_anchor_style_name = "TButton" 
        style = ttk.Style()
        style.configure(self.selected_anchor_style_name, background="lightblue")


        # --- UI Setup ---
        self.create_menu()
        
        # Toolbox (remains on the left of the paned window)
        self.toolbox_frame = ttk.Frame(self, width=200, relief="sunken", borderwidth=2)
        self.toolbox_frame.pack(side="left", fill="y", padx=5, pady=5); self.toolbox_frame.pack_propagate(False)
        
        # Main Paned Window for Canvases
        self.main_paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_paned_window.pack(side="left", expand=True, fill="both", padx=5, pady=5)

        self.canvases = []
        canvas_containers = []

        for i in range(self.num_canvases):
            container = ttk.Frame(self.main_paned_window) # Container for each canvas
            canvas_containers.append(container)
            # 初期サッシ位置をウィンドウ幅の半分に設定（おおよそ）
            # PanedWindowへの追加時に weight を使うことで、リサイズ時の挙動を制御
            self.main_paned_window.add(container, weight=1) 
            
            canvas = tk.Canvas(container, bg="white", relief="sunken", borderwidth=2)
            canvas.pack(expand=True, fill="both")
            self.canvases.append(canvas)

        # Property editor (remains on the right)
        self.property_frame = ttk.Frame(self, width=250, relief="sunken", borderwidth=2)
        self.property_frame.pack(side="right", fill="y", padx=5, pady=5); self.property_frame.pack_propagate(False)
        
        self.setup_toolbox() # Toolbox setup needs to happen after main_paned_window is created for sash control
        self.setup_properties()

        for idx, canvas_widget in enumerate(self.canvases):
            # Use a dispatcher to set active_canvas_idx before calling the main handler
            canvas_widget.bind("<ButtonPress-1>", lambda e, i=idx: self._dispatch_canvas_event(e, i, self.on_canvas_press))
            canvas_widget.bind("<Configure>", lambda e, i=idx: self._dispatch_canvas_event(e, i, self.on_canvas_resize))
        
        self.after(100, self.initial_draw_grids)
        # 初期サッシ位置を設定 (add の後、ウィンドウが表示される前が良い)
        self.after(50, lambda: self.main_paned_window.sashpos(0, self.initial_width // (self.num_canvases * 2) ))


        self.bind("<Delete>", self.on_delete_key_press)
        
        # Set initial focus to the first canvas
        self.canvases[self.active_canvas_idx].focus_set()
        
        # ウィンドウのConfigureイベントをバインドして、サイズ変更時にエントリーを更新
        self.bind("<Configure>", self._update_size_entries_on_configure)
        # PanedWindowのサッシ移動イベントを監視 (直接的なイベントはないため、ButtonReleaseで代用または定期確認)
        # 簡単な実装として、ButtonReleaseでサッシ位置を取得し更新
        self.main_paned_window.bind("<ButtonRelease-1>", self._update_sash_entry_on_release)


    def _get_active_canvas(self):
        return self.canvases[self.active_canvas_idx]

    def _get_active_canvas_items(self):
        return self.canvas_items[self.active_canvas_idx]

    def _get_active_selected_item_ids(self):
        return self.selected_item_ids[self.active_canvas_idx]
    
    def _get_active_highlight_rects(self):
        return self.highlight_rects[self.active_canvas_idx]

    def _set_active_dragged_item_id(self, item_id):
        self._dragged_item_id[self.active_canvas_idx] = item_id

    def _get_active_dragged_item_id(self):
        return self._dragged_item_id[self.active_canvas_idx]

    def _set_active_drag_start_coords(self, x, y):
        self._drag_start_x[self.active_canvas_idx] = x
        self._drag_start_y[self.active_canvas_idx] = y
    
    def _get_active_drag_start_coords(self):
        return self. _drag_start_x[self.active_canvas_idx], self._drag_start_y[self.active_canvas_idx]

    def _get_active_drag_selected_items_start_bboxes(self):
        return self._drag_selected_items_start_bboxes[self.active_canvas_idx]

    def _set_active_resize_handle(self, handle_type):
        self.active_resize_handle[self.active_canvas_idx] = handle_type

    def _get_active_resize_handle(self):
        return self.active_resize_handle[self.active_canvas_idx]
        
    def _set_active_resize_start_mouse_coords(self, x, y):
        self.resize_start_mouse_x[self.active_canvas_idx] = x
        self.resize_start_mouse_y[self.active_canvas_idx] = y

    def _get_active_resize_start_mouse_coords(self):
        return self.resize_start_mouse_x[self.active_canvas_idx], self.resize_start_mouse_y[self.active_canvas_idx]

    def _set_active_resize_start_item_bbox(self, bbox):
        self.resize_start_item_bbox[self.active_canvas_idx] = bbox
    
    def _get_active_resize_start_item_bbox(self):
        return self.resize_start_item_bbox[self.active_canvas_idx]

    def _set_active_resize_original_pil_image(self, img):
        self.resize_original_pil_image[self.active_canvas_idx] = img

    def _get_active_resize_original_pil_image(self):
        return self.resize_original_pil_image[self.active_canvas_idx]


    def _dispatch_canvas_event(self, event, canvas_idx, handler_method):
        """Sets the active canvas and calls the appropriate event handler."""
        if event.widget not in self.canvases:
            parent_widget_str = str(event.widget.winfo_parent())
            determined_idx = -1
            for idx, cv in enumerate(self.canvases):
                if event.widget == cv: 
                    determined_idx = idx
                    break
                if parent_widget_str == str(cv):
                    determined_idx = idx
                    break
            
            if determined_idx != -1:
                self.active_canvas_idx = determined_idx
            else: 
                self.active_canvas_idx = canvas_idx

        else: # Direct click on canvas background
             self.active_canvas_idx = canvas_idx
        
        if hasattr(self.canvases[self.active_canvas_idx], 'focus_set'):
             self.canvases[self.active_canvas_idx].focus_set()
        
        handler_method(event)


    def initial_draw_grids(self):
        for i in range(self.num_canvases):
            self.draw_grid(i)

    def _set_font_ui_state(self, state):
        self.font_family_combo.config(state=state); self.font_size_spin.config(state=state)
        self.font_bold_check.config(state=state); self.font_italic_check.config(state=state)

    def _set_anchor_ui_state(self, state): 
        if hasattr(self, 'anchor_buttons'):
            for r_buttons in self.anchor_buttons.values():
                for btn in r_buttons.values():
                    btn.config(state=state)
                    if state == "disabled": 
                        btn.config(style=self.default_anchor_style_name)


    def _set_color_ui_state(self, state, widget_obj=None): 
        fg_s, bg_s = state, state
        if widget_obj:
            if not isinstance(widget_obj, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
                 bg_s = "disabled" 
        else: 
            fg_s, bg_s = "disabled", "disabled"

        self.fg_color_entry.config(state=fg_s); self.fg_color_button.config(state=fg_s)
        self.bg_color_entry.config(state=bg_s); self.bg_color_button.config(state=bg_s)

    def create_menu(self):
        menubar = tk.Menu(self); self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0); menubar.add_cascade(label="ファイル", menu=file_menu)
        file_menu.add_command(label="レイアウトを開く...", command=self.open_layout) 
        file_menu.add_command(label="レイアウトを保存...", command=self.save_layout) 
        file_menu.add_separator(); file_menu.add_command(label="終了", command=self.quit)

    def setup_toolbox(self):
        ttk.Label(self.toolbox_frame, text="ツールボックス", font=("Helvetica", 14)).pack(pady=5) 
        
        size_control_frame = ttk.LabelFrame(self.toolbox_frame, text="ウィンドウサイズ")
        size_control_frame.pack(fill="x", padx=10, pady=(5,10))

        ttk.Label(size_control_frame, text="幅:").grid(row=0, column=0, padx=2, pady=2, sticky="w")
        self.window_width_var = tk.StringVar(value=str(self.initial_width))
        self.window_width_entry = ttk.Entry(size_control_frame, textvariable=self.window_width_var, width=7)
        self.window_width_entry.grid(row=0, column=1, padx=2, pady=2)

        ttk.Label(size_control_frame, text="高さ:").grid(row=1, column=0, padx=2, pady=2, sticky="w")
        self.window_height_var = tk.StringVar(value=str(self.initial_height))
        self.window_height_entry = ttk.Entry(size_control_frame, textvariable=self.window_height_var, width=7)
        self.window_height_entry.grid(row=1, column=1, padx=2, pady=2)
        
        apply_size_button = ttk.Button(size_control_frame, text="サイズ適用", command=self.apply_window_size)
        apply_size_button.grid(row=2, column=0, columnspan=2, pady=5)

        sash_control_frame = ttk.LabelFrame(self.toolbox_frame, text="分割位置 (左画面 幅)")
        sash_control_frame.pack(fill="x", padx=10, pady=(0,10))

        self.sash_pos_var = tk.StringVar()
        self.after(100, self._update_sash_entry_on_release) 

        self.sash_pos_entry = ttk.Entry(sash_control_frame, textvariable=self.sash_pos_var, width=7)
        self.sash_pos_entry.pack(side="left", padx=5, pady=5)
        
        apply_sash_button = ttk.Button(sash_control_frame, text="位置適用", command=self.apply_sash_position)
        apply_sash_button.pack(side="left", padx=5, pady=5)

        ttk.Separator(self.toolbox_frame, orient='horizontal').pack(fill='x', pady=5, padx=5)


        widget_types = ["Button", "Label", "Checkbutton", "Radiobutton", "Entry", "Combobox"]
        for name in widget_types:
            ttk.Button(self.toolbox_frame, text=name, command=lambda n=name: self.add_widget(n.lower())).pack(fill="x", padx=10, pady=2) 
        
        ttk.Button(self.toolbox_frame, text="Image", command=self.add_image_to_canvas).pack(fill="x", padx=10, pady=2)

        grid_frame = ttk.Frame(self.toolbox_frame)
        grid_frame.pack(fill="x", padx=10, pady=2)
        ttk.Label(grid_frame, text="グリッド間隔:").pack(side="left", padx=(0,5))
        self.grid_size_spinbox = ttk.Spinbox(
            grid_frame,
            from_=5,
            to=100,
            increment=1,
            textvariable=self.prop_grid_size,
            command=self.on_grid_size_change, 
            width=5
        )
        self.grid_size_spinbox.pack(side="left")

        ttk.Separator(self.toolbox_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)
        ttk.Button(self.toolbox_frame, text="コード生成", command=self.generate_code).pack(fill="x", padx=10, pady=5)
        
    def apply_window_size(self):
        try:
            new_width = int(self.window_width_var.get())
            new_height = int(self.window_height_var.get())
            if new_width > 0 and new_height > 0:
                self.geometry(f"{new_width}x{new_height}")
            else:
                tkinter.messagebox.showerror("入力エラー", "幅と高さは正の整数である必要があります。")
        except ValueError:
            tkinter.messagebox.showerror("入力エラー", "幅と高さには整数値を入力してください。")

    def apply_sash_position(self):
        try:
            new_pos = int(self.sash_pos_var.get())
            if new_pos > 0:
                self.main_paned_window.sashpos(0, new_pos)
            else:
                tkinter.messagebox.showerror("入力エラー", "分割位置は正の整数である必要があります。")
        except ValueError:
            tkinter.messagebox.showerror("入力エラー", "分割位置には整数値を入力してください。")
        except tk.TclError as e:
            print(f"サッシ位置設定エラー: {e}")
            tkinter.messagebox.showwarning("設定エラー", "サッシ位置の設定に失敗しました。ウィンドウが完全に表示されているか確認してください。")


    def _update_size_entries_on_configure(self, event=None):
        if event and event.widget == self:
            self.window_width_var.set(str(self.winfo_width()))
            self.window_height_var.set(str(self.winfo_height()))
    
    def _update_sash_entry_on_release(self, event=None):
        if hasattr(self, 'main_paned_window') and self.main_paned_window.panes():
            try:
                sash_position = self.main_paned_window.sashpos(0)
                self.sash_pos_var.set(str(sash_position))
            except tk.TclError:
                pass 

    def setup_properties(self):
        ttk.Label(self.property_frame, text="プロパティエディタ", font=("Helvetica", 14)).pack(pady=10)
        
        text_frame = ttk.Frame(self.property_frame); text_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(text_frame, text="Text:").pack(side="left")
        self.prop_text = tk.StringVar(); self.prop_text.trace_add("write", self.on_property_change)
        self.text_entry = ttk.Entry(text_frame, textvariable=self.prop_text) 
        self.text_entry.pack(side="left", expand=True, fill="x")

        values_frame = ttk.Frame(self.property_frame); values_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(values_frame, text="Values:").pack(side="left")
        self.prop_values = tk.StringVar(); self.prop_values.trace_add("write", self.on_property_change)
        self.values_entry = ttk.Entry(values_frame, textvariable=self.prop_values)
        self.values_entry.pack(side="left", expand=True, fill="x")
        
        ttk.Separator(self.property_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)
        
        font_frame = ttk.Frame(self.property_frame); font_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(font_frame, text="Font:", font=("Helvetica", 12)).pack(anchor="w")
        family_frame = ttk.Frame(font_frame); family_frame.pack(fill="x", pady=2)
        ttk.Label(family_frame, text="Family:", width=7).pack(side="left")
        self.prop_font_family = tk.StringVar()
        self.font_family_combo = ttk.Combobox(family_frame, textvariable=self.prop_font_family, values=sorted(list(tkfont.families())))
        self.font_family_combo.pack(fill="x", expand=True)
        self.prop_font_family.trace_add('write', self.on_font_property_change)

        size_frame = ttk.Frame(font_frame); size_frame.pack(fill="x", pady=2)
        ttk.Label(size_frame, text="Size:", width=7).pack(side="left")
        self.prop_font_size = tk.IntVar(value=9) 
        self.font_size_spin = ttk.Spinbox(size_frame, textvariable=self.prop_font_size, from_=6, to=72)
        self.font_size_spin.pack(fill="x", expand=True)
        self.prop_font_size.trace_add('write', self.on_font_property_change)

        style_frame = ttk.Frame(font_frame); style_frame.pack(fill="x", pady=2)
        ttk.Label(style_frame, text="Style:", width=7).pack(side="left")
        self.prop_font_bold = tk.BooleanVar()
        self.font_bold_check = ttk.Checkbutton(style_frame, text="Bold", variable=self.prop_font_bold, command=self.on_font_property_change)
        self.font_bold_check.pack(side="left")
        self.prop_font_italic = tk.BooleanVar()
        self.font_italic_check = ttk.Checkbutton(style_frame, text="Italic", variable=self.prop_font_italic, command=self.on_font_property_change)
        self.font_italic_check.pack(side="left")

        ttk.Separator(self.property_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)

        anchor_frame = ttk.Frame(self.property_frame)
        anchor_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(anchor_frame, text="Anchor:", font=("Helvetica", 12)).pack(anchor="w")
        
        anchor_buttons_frame = ttk.Frame(anchor_frame)
        anchor_buttons_frame.pack(pady=2)
        self.prop_anchor = tk.StringVar() 
        self.anchor_buttons = {} 
        anchor_positions = [ 
            ['nw', 'n', 'ne'],
            ['w', 'center', 'e'],
            ['sw', 's', 'se']
        ]

        for r, row_anchors in enumerate(anchor_positions):
            self.anchor_buttons[r] = {}
            row_frame = ttk.Frame(anchor_buttons_frame)
            row_frame.pack()
            for c, anchor_val in enumerate(row_anchors):
                btn = ttk.Button(row_frame, text=anchor_val.upper(), width=4,
                                 command=lambda val=anchor_val: self.on_anchor_button_click(val),
                                 style=self.default_anchor_style_name)
                btn.pack(side="left", padx=1, pady=1)
                self.anchor_buttons[r][c] = btn


        ttk.Separator(self.property_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)

        fg_frame = ttk.Frame(self.property_frame); fg_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(fg_frame, text="Foreground Color:", font=("Helvetica", 12)).pack(anchor="w")
        fg_editor_frame = ttk.Frame(fg_frame); fg_editor_frame.pack(fill="x", pady=2)
        self.fg_color_preview = tk.Label(fg_editor_frame, text=" ", bg="#000000", width=2, relief="sunken")
        self.fg_color_preview.pack(side="left", padx=(0, 5))
        self.prop_fg_color = tk.StringVar(); self.prop_fg_color.trace_add('write', self.on_fg_color_change)
        self.fg_color_entry = ttk.Entry(fg_editor_frame, textvariable=self.prop_fg_color, width=10)
        self.fg_color_entry.pack(side="left", expand=True, fill="x")
        self.fg_color_button = ttk.Button(fg_editor_frame, text="...", width=3, command=self.open_fg_color_chooser)
        self.fg_color_button.pack(side="left", padx=(5, 0))
        
        bg_frame = ttk.Frame(self.property_frame); bg_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(bg_frame, text="Background Color:", font=("Helvetica", 12)).pack(anchor="w")
        bg_editor_frame = ttk.Frame(bg_frame); bg_editor_frame.pack(fill="x", pady=2)
        self.bg_color_preview = tk.Label(bg_editor_frame, text=" ", bg="#F0F0F0", width=2, relief="sunken")
        self.bg_color_preview.pack(side="left", padx=(0, 5))
        self.prop_bg_color = tk.StringVar(); self.prop_bg_color.trace_add('write', self.on_bg_color_change)
        self.bg_color_entry = ttk.Entry(bg_editor_frame, textvariable=self.prop_bg_color, width=10)
        self.bg_color_entry.pack(side="left", expand=True, fill="x")
        self.bg_color_button = ttk.Button(bg_editor_frame, text="...", width=3, command=self.open_bg_color_chooser)
        self.bg_color_button.pack(side="left", padx=(5, 0))

        ttk.Separator(self.property_frame, orient='horizontal').pack(fill='x', pady=(15, 5), padx=5) 
        self.delete_button = ttk.Button(
            self.property_frame,
            text="選択項目を削除",
            command=self.delete_selected_item, 
            state="disabled"
        )
        self.delete_button.pack(pady=5, padx=10, fill='x')

        self.text_entry.config(state="disabled")
        self.values_entry.config(state="disabled")
        self._set_font_ui_state("disabled")
        self._set_anchor_ui_state("disabled")
        self._set_color_ui_state("disabled")

    def add_image_to_canvas(self): 
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()

        filepath = filedialog.askopenfilename(
            title="画像ファイルを選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.gif *.bmp"), ("すべてのファイル", "*.*")]
        )
        if not filepath: return
        try:
            pil_image = Image.open(filepath)
            max_dim = 200 
            
            current_pil_image = pil_image.copy() 
            if current_pil_image.width > max_dim or current_pil_image.height > max_dim:
                current_pil_image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            tk_photo_image = ImageTk.PhotoImage(current_pil_image)
            
            raw_x = active_canvas.winfo_width() / 2
            raw_y = active_canvas.winfo_height() / 2
            snapped_x, snapped_y = self._snap_to_grid(raw_x, raw_y) 
            
            image_item_id = active_canvas.create_image(snapped_x, snapped_y, image=tk_photo_image, anchor=tk.NW)
            
            item_info = {
                'id': image_item_id, 
                'type': 'image', 
                'obj': tk_photo_image, 
                'path': filepath, 
                'width': current_pil_image.width, 
                'height': current_pil_image.height, 
                'original_pil_image': pil_image 
            }
            active_canvas_items.append(item_info)
            active_canvas.tag_bind(image_item_id, "<ButtonPress-1>", 
                                       lambda e, i_id=image_item_id, c_idx=self.active_canvas_idx: \
                                       self._dispatch_item_event(e, c_idx, i_id, self.on_canvas_item_press))
        except Exception as e: 
            print(f"画像処理エラー: {e}")
            tkinter.messagebox.showerror("画像エラー", f"画像の読み込みまたは処理中にエラーが発生しました:\n{e}")

    def add_widget(self, widget_type, text=None, x=None, y=None, values=None, font_info=None, colors=None, width=None, height=None, anchor=None):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()

        font_tuple = None
        if font_info:
            family = font_info.get('family', tkfont.nametofont("TkDefaultFont").actual()["family"])
            size = font_info.get('size', tkfont.nametofont("TkDefaultFont").actual()["size"])
            style_parts = []
            if font_info.get('weight') == 'bold': style_parts.append('bold')
            if font_info.get('slant') == 'italic': style_parts.append('italic')
            font_tuple = (family, size, " ".join(style_parts))
        
        fg_color = colors.get('fg') if colors else None
        bg_color = colors.get('bg') if colors else None

        widget_args = {}
        if font_tuple: widget_args['font'] = font_tuple
        if anchor and widget_type in ["button", "label", "checkbutton", "radiobutton"]:
             widget_args['anchor'] = anchor
        
        w = None
        if widget_type == "button":
            widget_args['text'] = text or "Button"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Button(active_canvas, **widget_args)
        elif widget_type == "label":
            widget_args['text'] = text or "Label"
            if fg_color: widget_args['foreground'] = fg_color 
            w = ttk.Label(active_canvas, **widget_args) 
        elif widget_type == "checkbutton":
            widget_args['text'] = text or "Checkbutton"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Checkbutton(active_canvas, **widget_args)
        elif widget_type == "radiobutton":
            widget_args['text'] = text or "Radiobutton"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Radiobutton(active_canvas, **widget_args)
        elif widget_type == "entry":
            w = ttk.Entry(active_canvas, **widget_args) 
            if text: w.insert(0, text)
        elif widget_type == "combobox":
            w = ttk.Combobox(active_canvas, **widget_args) 
            if values: w['values'] = values
            else: w['values'] = ["Item 1", "Item 2"]
            if text: w.set(text)
            else: w.current(0)
        else:
            print(f"Unknown widget type: {widget_type}")
            return
        
        canvas_x_center = x if x is not None else active_canvas.winfo_width() / 2
        canvas_y_center = y if y is not None else active_canvas.winfo_height() / 2
        
        canvas_id = active_canvas.create_window(canvas_x_center, canvas_y_center, window=w)
        
        if width is not None and height is not None:
            try:
                active_canvas.itemconfig(canvas_id, width=int(width), height=int(height))
            except (ValueError, tk.TclError) as e:
                print(f"Error setting loaded width/height for widget: {e}")
        
        self.update_idletasks() 

        bbox_coords = active_canvas.bbox(canvas_id)
        actual_widget_width = bbox_coords[2] - bbox_coords[0] if bbox_coords else w.winfo_reqwidth()
        actual_widget_height = bbox_coords[3] - bbox_coords[1] if bbox_coords else w.winfo_reqheight()
        
        desired_top_left_x = (x if x is not None 
                              else canvas_x_center - actual_widget_width / 2)
        desired_top_left_y = (y if y is not None 
                              else canvas_y_center - actual_widget_height / 2)
        
        snapped_tl_x, snapped_tl_y = self._snap_to_grid(desired_top_left_x, desired_top_left_y)
        
        final_center_x = snapped_tl_x + actual_widget_width / 2
        final_center_y = snapped_tl_y + actual_widget_height / 2
        active_canvas.coords(canvas_id, final_center_x, final_center_y)

        item_info = {
            'id': canvas_id, 
            'type': 'widget', 
            'obj': w, 
            'widget_type': widget_type,
            'width': actual_widget_width, 
            'height': actual_widget_height
            }
        active_canvas_items.append(item_info)
        
        current_canvas_idx_for_item = self.active_canvas_idx 

        w.bind("<ButtonPress-1>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: \
                                  self._dispatch_item_event(e, c_idx, i_id, self.on_canvas_item_press))
        w.bind("<B1-Motion>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: \
                                self._dispatch_item_event(e, c_idx, i_id, self.on_multi_item_drag))
        w.bind("<ButtonRelease-1>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: \
                                    self._dispatch_item_event(e, c_idx, i_id, self.on_multi_item_release))


    def _dispatch_item_event(self, event, canvas_idx_of_item, item_id, handler_method):
        """
        Dispatcher for events on items (widgets or images).
        Ensures active_canvas_idx is set to the canvas where the item resides.
        """
        self.active_canvas_idx = canvas_idx_of_item
        if hasattr(self.canvases[self.active_canvas_idx], 'focus_set'):
            self.canvases[self.active_canvas_idx].focus_set() 
        
        handler_method(event, item_id)


    def on_canvas_press(self, event):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()
        active_selected_ids = self._get_active_selected_item_ids()
        
        overlapping_ids = active_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        is_on_resize_handle = False
        if overlapping_ids:
            for item_id_overlap in overlapping_ids:
                tags = active_canvas.gettags(item_id_overlap)
                if any(tag.startswith(f"{self.RESIZE_HANDLE_TAG_PREFIX}") and tag.endswith(f"_{self.active_canvas_idx}") for tag in tags):
                    is_on_resize_handle = True
                    break 
        if is_on_resize_handle:
            return 

        clicked_item_id = None
        if overlapping_ids:
            for item_id_overlap in overlapping_ids:
                if any(ci['id'] == item_id_overlap for ci in active_canvas_items): 
                    current_tags = active_canvas.gettags(item_id_overlap)
                    is_highlight_or_handle = False
                    if f"multi_highlight_rect_{self.active_canvas_idx}" in current_tags or \
                       f"primary_highlight_rect_{self.active_canvas_idx}" in current_tags or \
                       f"{self.ALL_RESIZE_HANDLES_TAG}_{self.active_canvas_idx}" in current_tags or \
                       any(tag.startswith(f"{self.RESIZE_HANDLE_TAG_PREFIX}") and tag.endswith(f"_{self.active_canvas_idx}") for tag in current_tags) :
                        is_highlight_or_handle = True
                        
                    if not is_highlight_or_handle:
                        clicked_item_id = item_id_overlap
                        break
        
        if not clicked_item_id and not self._get_active_dragged_item_id(): 
            self.deselect_all() 
        

    def deselect_all(self):
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        active_highlight_rects = self._get_active_highlight_rects()

        if active_selected_ids: 
            active_selected_ids.clear()
        
        self.selected_widget = None
        self.selected_item_info = None 

        for rect_id in active_highlight_rects.values(): 
            active_canvas.delete(rect_id)
        active_highlight_rects.clear()
        
        active_canvas.delete(f"{self.ALL_RESIZE_HANDLES_TAG}_{self.active_canvas_idx}") 
        self.update_property_editor() 

    def on_canvas_item_press(self, event, item_id):
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        active_drag_bboxes = self._get_active_drag_selected_items_start_bboxes()
        self._set_active_dragged_item_id(item_id)

        canvas_x = event.x 
        canvas_y = event.y
        # --- 追加: ドラッグ開始時のマウス座標とウィジェット中心のオフセットを記録 ---
        bbox = active_canvas.bbox(item_id)
        if bbox:
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            offset_x = canvas_x - center_x
            offset_y = canvas_y - center_y
            self._active_drag_offset = (offset_x, offset_y)
        else:
            self._active_drag_offset = (0, 0)
        # ...existing code...
        try:
            if event.widget != active_canvas: 
                abs_x = event.widget.winfo_rootx() + event.x
                abs_y = event.widget.winfo_rooty() + event.y
                canvas_x = abs_x - active_canvas.winfo_rootx()
                canvas_y = abs_y - active_canvas.winfo_rooty()
        except Exception as e:
            pass 
        self._set_active_drag_start_coords(canvas_x, canvas_y)

        is_shift_pressed = (event.state & 0x0001) != 0

        if not is_shift_pressed:
            if item_id not in active_selected_ids or len(active_selected_ids) > 1: 
                current_selection_copy = set(active_selected_ids) 
                active_hr = self._get_active_highlight_rects()
                for prev_id in current_selection_copy:
                    if prev_id in active_hr:
                        active_canvas.delete(active_hr[prev_id])
                        del active_hr[prev_id]
                active_selected_ids.clear()
                active_selected_ids.add(item_id)
        else: 
            active_hr = self._get_active_highlight_rects()
            if item_id in active_selected_ids: 
                active_selected_ids.remove(item_id)
                if item_id in active_hr: 
                    active_canvas.delete(active_hr[item_id])
                    del active_hr[item_id]
            else: 
                active_selected_ids.add(item_id)

        active_drag_bboxes.clear() 
        for s_id in active_selected_ids:
            bbox = active_canvas.bbox(s_id)
            if bbox: 
                 active_drag_bboxes[s_id] = bbox

        self.update_property_editor_for_selection() 
        self.update_highlight() 

        if active_selected_ids:
            for s_id in active_selected_ids:
                active_canvas.tag_raise(s_id) 
            
            active_canvas.bind("<B1-Motion>", lambda e, c_idx=self.active_canvas_idx: \
                self._dispatch_canvas_event(e, c_idx, self.on_multi_item_drag))
            active_canvas.bind("<ButtonRelease-1>", lambda e, c_idx=self.active_canvas_idx: \
                self._dispatch_canvas_event(e, c_idx, self.on_multi_item_release))


    def update_property_editor_for_selection(self):
        active_selected_ids = self._get_active_selected_item_ids()
        active_canvas_items = self._get_active_canvas_items()

        self.selected_widget = None 
        self.selected_item_info = None 

        if len(active_selected_ids) == 1:
            single_id = list(active_selected_ids)[0]
            item_info = next((item for item in active_canvas_items if item['id'] == single_id), None)
            if item_info:
                self.selected_item_info = item_info 
                if item_info['type'] == 'widget':
                    self.selected_widget = item_info['obj'] 
        
        self.update_property_editor()


    def on_multi_item_drag(self, event, item_id=None): 
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        dragged_item_id_from_state = self._get_active_dragged_item_id() 
        active_resize_h = self._get_active_resize_handle()
        start_bboxes = self._get_active_drag_selected_items_start_bboxes()
        start_drag_x, start_drag_y = self._get_active_drag_start_coords()
        active_canvas_items = self._get_active_canvas_items()

        if not dragged_item_id_from_state or not active_selected_ids or active_resize_h:
            return

        # Convert event coordinates to be relative to the active_canvas
        current_mouse_x_canvas = event.x
        current_mouse_y_canvas = event.y
        if event.widget != active_canvas:
            # event.widget is the actual tk/ttk widget that received the event
            try:
                abs_x = event.widget.winfo_rootx() + event.x
                abs_y = event.widget.winfo_rooty() + event.y
                current_mouse_x_canvas = abs_x - active_canvas.winfo_rootx()
                current_mouse_y_canvas = abs_y - active_canvas.winfo_rooty()
            except tk.TclError: # Widget might be in a weird state during drag/destroy
                # This can happen if the widget is destroyed while dragging
                return
            except Exception: # Catch any other potential errors during coordinate conversion
                return
                
        drag_delta_x = current_mouse_x_canvas - start_drag_x
        drag_delta_y = current_mouse_y_canvas - start_drag_y
        effective_delta_x = drag_delta_x
        effective_delta_y = drag_delta_y
        if dragged_item_id_from_state and dragged_item_id_from_state in start_bboxes:
            primary_start_bbox = start_bboxes[dragged_item_id_from_state]
            if not primary_start_bbox: 
                return
            primary_new_top_left_x_raw = primary_start_bbox[0] + drag_delta_x
            primary_new_top_left_y_raw = primary_start_bbox[1] + drag_delta_y
            snapped_primary_tl_x, snapped_primary_tl_y = self._snap_to_grid(primary_new_top_left_x_raw, primary_new_top_left_y_raw)
            effective_delta_x = snapped_primary_tl_x - primary_start_bbox[0]
            effective_delta_y = snapped_primary_tl_y - primary_start_bbox[1]

        for current_item_id_in_selection in active_selected_ids:
            if current_item_id_in_selection in start_bboxes:
                start_bbox = start_bboxes[current_item_id_in_selection]
                if not start_bbox:
                    continue
                item_info = next((item for item in active_canvas_items if item['id'] == current_item_id_in_selection), None)
                if item_info:
                    if item_info['type'] == 'widget':
                        width = item_info.get('width', start_bbox[2] - start_bbox[0])
                        height = item_info.get('height', start_bbox[3] - start_bbox[1])
                        # --- ここでドラッグ中の中心座標を正しく計算 ---
                        if current_item_id_in_selection == dragged_item_id_from_state:
                            # 主アイテムはスナップ・オフセット考慮
                            center_x = snapped_primary_tl_x + width / 2
                            center_y = snapped_primary_tl_y + height / 2
                        else:
                            # 他の選択アイテムは相対移動
                            center_x = (start_bbox[0] + effective_delta_x) + width / 2
                            center_y = (start_bbox[1] + effective_delta_y) + height / 2
                        active_canvas.coords(current_item_id_in_selection, center_x, center_y)
                    elif item_info['type'] == 'image':
                        new_top_left_x = start_bbox[0] + effective_delta_x
                        new_top_left_y = start_bbox[1] + effective_delta_y
                        active_canvas.coords(current_item_id_in_selection, new_top_left_x, new_top_left_y)
        self.update_highlight() 

    def on_multi_item_release(self, event, item_id=None): 
        active_canvas = self._get_active_canvas()
        
        self._set_active_dragged_item_id(None)
        self._get_active_drag_selected_items_start_bboxes().clear()
        
        active_canvas.unbind("<B1-Motion>")
        active_canvas.unbind("<ButtonRelease-1>")
        
        active_canvas.bind("<ButtonPress-1>", lambda e, i=self.active_canvas_idx: \
            self._dispatch_canvas_event(e, i, self.on_canvas_press))


    def update_property_editor(self):
        active_selected_ids = self._get_active_selected_item_ids() 
        num_selected = len(active_selected_ids)
        
        single_selected_item_info = self.selected_item_info 
        widget_obj = self.selected_widget

        is_single_widget_selected = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'widget')
        is_single_image_selected = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'image')

        self.text_entry.config(state="normal" if is_single_widget_selected else "disabled")
        self.values_entry.config(state="normal" if is_single_widget_selected and isinstance(widget_obj, ttk.Combobox) else "disabled")
        self._set_font_ui_state("normal" if is_single_widget_selected else "disabled")
        
        anchor_applicable = is_single_widget_selected and isinstance(widget_obj, (tk.Label, ttk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton))
        self._set_anchor_ui_state("normal" if anchor_applicable else "disabled")
        
        self._set_color_ui_state("normal" if is_single_widget_selected else "disabled", widget_obj)
        self.delete_button.config(state="normal" if num_selected > 0 else "disabled")

        if is_single_widget_selected and widget_obj and widget_obj.winfo_exists():
            self._updating_properties_internally = True 
            if isinstance(widget_obj, (ttk.Entry, ttk.Combobox)): self.prop_text.set(widget_obj.get())
            elif hasattr(widget_obj, 'cget'):
                try: self.prop_text.set(widget_obj.cget("text"))
                except tk.TclError: self.prop_text.set("")
            else: self.prop_text.set("")

            if isinstance(widget_obj, ttk.Combobox):
                combo_values = widget_obj.cget("values"); self.prop_values.set(",".join(self._get_python_list_from_tcl_list(combo_values)))
            else: self.prop_values.set("")
            
            try:
                font_obj = tkfont.Font(font=widget_obj.cget("font")); attrs = font_obj.actual()
                self.prop_font_family.set(attrs["family"]); self.prop_font_size.set(abs(attrs["size"])) 
                self.prop_font_bold.set(attrs["weight"] == "bold"); self.prop_font_italic.set(attrs["slant"] == "italic")
            except tk.TclError: self._set_font_ui_state("disabled") 
            
            if anchor_applicable:
                try:
                    current_anchor = str(widget_obj.cget("anchor"))
                    self.prop_anchor.set(current_anchor)
                    for r_idx, row_buttons_dict in self.anchor_buttons.items():
                        for c_idx, button_widget_iter in row_buttons_dict.items(): 
                            button_text_lower = button_widget_iter.cget('text').lower()
                            button_widget_iter.config(style=self.selected_anchor_style_name if button_text_lower == current_anchor else self.default_anchor_style_name)
                except tk.TclError: 
                    self.prop_anchor.set("center") 
                    for r_buttons in self.anchor_buttons.values():
                        for btn_widget in r_buttons.values():
                            if btn_widget.cget('text').lower() == 'center':
                                btn_widget.config(style=self.selected_anchor_style_name)
                            else:
                                btn_widget.config(style=self.default_anchor_style_name)
            else: 
                self.prop_anchor.set("")
                for r_buttons in self.anchor_buttons.values(): 
                    for btn_widget in r_buttons.values(): btn_widget.config(style=self.default_anchor_style_name)


            try: 
                fg_opt = 'fg' if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)) else 'foreground'
                fg_val = widget_obj.cget(fg_opt)
                self.prop_fg_color.set(fg_val); self.fg_color_preview.config(bg=fg_val)
            except tk.TclError: self.prop_fg_color.set("#000000"); self.fg_color_preview.config(bg="#000000")

            if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)): 
                try: bg_val = widget_obj.cget('bg'); self.prop_bg_color.set(bg_val); self.bg_color_preview.config(bg=bg_val)
                except tk.TclError: self.prop_bg_color.set("#F0F0F0"); self.bg_color_preview.config(bg="#F0F0F0") 
            else: 
                self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg')) 
            self._updating_properties_internally = False 

        elif is_single_image_selected:
            self.prop_text.set("[Image Selected]"); self.prop_values.set(""); self.prop_anchor.set("")
            self.prop_fg_color.set(""); self.fg_color_preview.config(bg=self.cget('bg'))
            self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg'))
        elif num_selected > 1: 
            self.prop_text.set(f"[{num_selected} items selected]"); self.prop_values.set(""); self.prop_anchor.set("")
            self.prop_fg_color.set(""); self.fg_color_preview.config(bg=self.cget('bg'))
            self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg'))
        else: 
            self.prop_text.set(""); self.prop_values.set(""); self.prop_anchor.set("")
            self.prop_fg_color.set(""); self.fg_color_preview.config(bg=self.cget('bg'))
            self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg'))


    def update_highlight(self):
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        active_highlight_rects = self._get_active_highlight_rects()
        active_canvas_items = self._get_active_canvas_items()
        current_active_idx = self.active_canvas_idx 

        for rect_id in list(active_highlight_rects.values()): 
            active_canvas.delete(rect_id)
        active_highlight_rects.clear()
        active_canvas.delete(f"{self.ALL_RESIZE_HANDLES_TAG}_{current_active_idx}")


        if not active_selected_ids:
            return

        for item_id in active_selected_ids:
            try:
                coords = active_canvas.bbox(item_id)
                if not coords: continue
                x1, y1, x2, y2 = coords
                rect_id = active_canvas.create_rectangle(
                    x1 - 1, y1 - 1, x2 + 1, y2 + 1, 
                    outline="gray", dash=(3,3), tags=(f"multi_highlight_rect_{current_active_idx}", "multi_highlight_rect_common") 
                )
                active_highlight_rects[item_id] = rect_id
            except tk.TclError:
                pass 

        if len(active_selected_ids) == 1:
            single_id = list(active_selected_ids)[0]
            if single_id in active_highlight_rects: 
                active_canvas.delete(active_highlight_rects[single_id]) 
                del active_highlight_rects[single_id] 

            try:
                coords = active_canvas.bbox(single_id)
                if not coords: return
                x1, y1, x2, y2 = coords
                primary_highlight_id = active_canvas.create_rectangle(
                    x1 - 2, y1 - 2, x2 + 2, y2 + 2, 
                    outline="blue", width=1, tags=(f"primary_highlight_rect_{current_active_idx}", "primary_highlight_rect_common")
                )
                active_highlight_rects[single_id] = primary_highlight_id 

                item_info = next((item for item in active_canvas_items if item['id'] == single_id), None)
                if item_info and (item_info['type'] == 'image' or item_info['type'] == 'widget'):
                    s = self.RESIZE_HANDLE_SIZE / 2
                    handle_defs = {
                        'nw': (x1,y1), 'n': ((x1+x2)/2,y1), 'ne': (x2,y1),
                        'w': (x1,(y1+y2)/2), 'e': (x2,(y1+y2)/2),
                        'sw': (x1,y2), 's': ((x1+x2)/2,y2), 'se': (x2,y2)
                    }
                    all_handles_tag_canvas = f"{self.ALL_RESIZE_HANDLES_TAG}_{current_active_idx}"

                    for h_type, (hx,hy) in handle_defs.items():
                        handle_tag_specific_on_canvas = f"{self.RESIZE_HANDLE_TAG_PREFIX}{h_type}_{current_active_idx}"
                        handle_id = active_canvas.create_rectangle(
                            hx-s, hy-s, hx+s, hy+s,
                            fill="white", outline="black", tags=(all_handles_tag_canvas, handle_tag_specific_on_canvas, self.RESIZE_HANDLE_TAG_PREFIX + h_type) 
                        )
                        active_canvas.tag_bind(handle_id, "<Enter>", lambda e, ht=h_type, c_idx=current_active_idx: self.on_handle_enter(e, ht, c_idx))
                        active_canvas.tag_bind(handle_id, "<Leave>", lambda e, c_idx=current_active_idx: self.on_handle_leave(e, c_idx))
                        active_canvas.tag_bind(handle_id, "<ButtonPress-1>", lambda e, ht=h_type, c_idx=current_active_idx: self.on_resize_handle_press(e, ht, c_idx))
                    
                    active_canvas.tag_raise(all_handles_tag_canvas)
                    active_canvas.tag_raise(primary_highlight_id) 
            except tk.TclError: 
                self.deselect_all() 


    def on_property_change(self, var_name_str, index, mode): 
        if self._updating_properties_internally: return 
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1:
            return

        new_text_from_prop_editor = self.prop_text.get()
        new_values_from_prop_editor = self.prop_values.get()

        if var_name_str == str(self.prop_text): 
            if isinstance(self.selected_widget, ttk.Entry):
                self.selected_widget.delete(0, tk.END)
                self.selected_widget.insert(0, new_text_from_prop_editor)
            elif isinstance(self.selected_widget, ttk.Combobox):
                self.selected_widget.set(new_text_from_prop_editor)
            elif hasattr(self.selected_widget, 'config') and 'text' in self.selected_widget.keys():
                try: self.selected_widget.config(text=new_text_from_prop_editor)
                except tk.TclError: pass 
        elif var_name_str == str(self.prop_values): 
            if isinstance(self.selected_widget, ttk.Combobox):
                try:
                    current_combo_text = self.selected_widget.get() 
                    new_values_list = [v.strip() for v in new_values_from_prop_editor.split(',') if v.strip()]
                    self.selected_widget.config(values=new_values_list)
                    if current_combo_text in new_values_list: self.selected_widget.set(current_combo_text)
                    elif new_values_list: self.selected_widget.current(0)
                    else: self.selected_widget.set("")
                except tk.TclError: pass 
        # After property change, widget might resize. Update highlight which re-reads bbox.
        self.after(10, self.update_highlight) 

    def on_font_property_change(self, *args):
        if self._updating_properties_internally or self._updating_font_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1:
            return
        
        family = self.prop_font_family.get(); size = self.prop_font_size.get()
        if not family or size <= 0: return 
        style_parts = []
        if self.prop_font_bold.get(): style_parts.append("bold")
        if self.prop_font_italic.get(): style_parts.append("italic")
        try:
            self.selected_widget.config(font=(family, size, " ".join(style_parts)))
            # After font change, widget might resize. Update highlight.
            self.after(50, self.update_highlight) 
        except tk.TclError as e: print(f"Font Error: {e}")

    def on_anchor_button_click(self, new_anchor_value):
        if self._updating_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1:
            return
        
        if isinstance(self.selected_widget, (tk.Label, ttk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton)):
            try:
                self.selected_widget.config(anchor=new_anchor_value)
                self.prop_anchor.set(new_anchor_value) 

                for r_idx, row_buttons_dict in self.anchor_buttons.items():
                    for c_idx, button_widget in row_buttons_dict.items():
                        button_text_lower = button_widget.cget('text').lower()
                        button_widget.config(style=self.selected_anchor_style_name if button_text_lower == new_anchor_value else self.default_anchor_style_name)
            except tk.TclError as e:
                print(f"Anchor Error: {e}")


    def on_fg_color_change(self, *args):
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        color = self.prop_fg_color.get()
        if len(color) >= 4 and color.startswith('#'): 
            try:
                opt_name = 'foreground' if isinstance(self.selected_widget, (ttk.Label, ttk.Entry, ttk.Combobox)) else 'fg'
                self.selected_widget.config(**{opt_name: color}); self.fg_color_preview.config(bg=color)
            except tk.TclError: pass 

    def on_bg_color_change(self, *args):
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        if isinstance(self.selected_widget, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
            color = self.prop_bg_color.get()
            if len(color) >= 4 and color.startswith('#'):
                try: self.selected_widget.config(background=color); self.bg_color_preview.config(bg=color)
                except tk.TclError: pass
        else: pass

    def open_fg_color_chooser(self):
        if self.selected_widget and self.fg_color_button['state'] != 'disabled' and len(self._get_active_selected_item_ids()) == 1:
            init_color = self.prop_fg_color.get() if self.prop_fg_color.get() else "#000000"
            code = colorchooser.askcolor(title="文字色を選択", initialcolor=init_color)
            if code and code[1]: self.prop_fg_color.set(code[1])

    def open_bg_color_chooser(self):
        if self.selected_widget and self.bg_color_button['state'] != 'disabled' and len(self._get_active_selected_item_ids()) == 1:
            init_color = self.prop_bg_color.get() if self.prop_bg_color.get() else "#F0F0F0"
            code = colorchooser.askcolor(title="背景色を選択", initialcolor=init_color)
            if code and code[1]: self.prop_bg_color.set(code[1])

    def on_handle_enter(self, event, handle_type, canvas_idx_of_handle):
        if len(self.selected_item_ids[canvas_idx_of_handle]) == 1: 
            cursor_name = self.HANDLE_CURSORS.get(handle_type)
            if cursor_name: self.canvases[canvas_idx_of_handle].config(cursor=cursor_name)

    def on_handle_leave(self, event, canvas_idx_of_handle): 
        if not self.active_resize_handle[canvas_idx_of_handle]: 
            self.canvases[canvas_idx_of_handle].config(cursor="")

    def on_resize_handle_press(self, event, handle_type, canvas_idx_of_handle):
        self.active_canvas_idx = canvas_idx_of_handle 
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        active_canvas_items = self._get_active_canvas_items()

        if len(active_selected_ids) != 1: return 
        
        single_id = list(active_selected_ids)[0]
        current_item_info = next((item for item in active_canvas_items if item['id'] == single_id), None)
        if not current_item_info: return
        self.selected_item_info = current_item_info 

        self._set_active_resize_handle(handle_type)

        mouse_x_on_canvas = event.x_root - active_canvas.winfo_rootx()
        mouse_y_on_canvas = event.y_root - active_canvas.winfo_rooty()
        self._set_active_resize_start_mouse_coords(mouse_x_on_canvas, mouse_y_on_canvas)
        self._set_active_resize_start_item_bbox(active_canvas.bbox(single_id))
        
        if self.selected_item_info['type'] == 'image':
            if 'original_pil_image' in self.selected_item_info:
                 self._set_active_resize_original_pil_image(self.selected_item_info['original_pil_image'].copy())
            else: 
                try:
                    loaded_pil_img = Image.open(self.selected_item_info['path'])
                    self._set_active_resize_original_pil_image(loaded_pil_img)
                except Exception as e:
                    print(f"リサイズ用元画像読み込みエラー: {e}")
                    tkinter.messagebox.showerror("リサイズエラー", f"リサイズ用の元画像を読み込めませんでした:\n{e}")
                    self._set_active_resize_handle(None); 
                    return
        elif self.selected_item_info['type'] == 'widget':
            self._set_active_resize_original_pil_image(None) # Ensure it's None for widgets

        # Unbind general canvas drag handlers and bind resize-specific ones
        active_canvas.unbind("<B1-Motion>")
        active_canvas.unbind("<ButtonRelease-1>")
        active_canvas.bind("<B1-Motion>", lambda e, c_idx=self.active_canvas_idx: \
            self._dispatch_canvas_event(e, c_idx, self.on_resize_handle_drag))
        active_canvas.bind("<ButtonRelease-1>", lambda e, c_idx=self.active_canvas_idx: \
            self._dispatch_canvas_event(e, c_idx, self.on_resize_handle_release))


    def on_resize_handle_drag(self, event): 
        active_canvas = self._get_active_canvas()
        active_resize_h = self._get_active_resize_handle()
        item_info_for_resize = self.selected_item_info 
        start_item_bbox = self._get_active_resize_start_item_bbox()
        resize_pil_img = self._get_active_resize_original_pil_image()
        start_mouse_x, start_mouse_y = self._get_active_resize_start_mouse_coords()


        if not all([active_resize_h, item_info_for_resize, start_item_bbox]):
            if not (item_info_for_resize and item_info_for_resize['type'] == 'image' and resize_pil_img) and \
               not (item_info_for_resize and item_info_for_resize['type'] == 'widget'):
                 return
        
        single_id = item_info_for_resize['id']

        mouse_x_canvas = event.x
        mouse_y_canvas = event.y

        current_delta_x = mouse_x_canvas - start_mouse_x
        current_delta_y = mouse_y_canvas - start_mouse_y
        
        orig_x1, orig_y1, orig_x2, orig_y2 = start_item_bbox
        
        modifier_state = event.state; SHIFT_MASK = 0x0001
        snap_active = ((modifier_state & SHIFT_MASK) != 0) 

        final_delta_x, final_delta_y = current_delta_x, current_delta_y
        if snap_active and self.grid_spacing > 0:
            handle = active_resize_h 
            if 'n' in handle: target_y = orig_y1 + current_delta_y; snapped_y = self._snap_to_grid(0, target_y)[1]; final_delta_y = snapped_y - orig_y1
            if 's' in handle: target_y = orig_y2 + current_delta_y; snapped_y = self._snap_to_grid(0, target_y)[1]; final_delta_y = snapped_y - orig_y2
            if 'w' in handle: target_x = orig_x1 + current_delta_x; snapped_x = self._snap_to_grid(target_x, 0)[0]; final_delta_x = snapped_x - orig_x1
            if 'e' in handle: target_x = orig_x2 + current_delta_x; snapped_x = self._snap_to_grid(target_x, 0)[0]; final_delta_x = snapped_x - orig_x2
        
        delta_x, delta_y = final_delta_x, final_delta_y
        handle = active_resize_h
        
        new_x1, new_y1, new_x2, new_y2 = orig_x1, orig_y1, orig_x2, orig_y2
        if 'n' in handle: new_y1 = orig_y1 + delta_y
        if 's' in handle: new_y2 = orig_y2 + delta_y
        if 'w' in handle: new_x1 = orig_x1 + delta_x
        if 'e' in handle: new_x2 = orig_x2 + delta_x
        
        if new_x1 > new_x2: new_x1, new_x2 = new_x2, new_x1 
        if new_y1 > new_y2: new_y1, new_y2 = new_y2, new_y1

        new_bbox_w, new_bbox_h = new_x2 - new_x1, new_y2 - new_y1
        min_dim_canvas = self.RESIZE_HANDLE_SIZE * 2 
        new_bbox_w = max(min_dim_canvas, new_bbox_w)
        new_bbox_h = max(min_dim_canvas, new_bbox_h)

        temp_x1, temp_y1, temp_x2, temp_y2 = new_x1, new_y1, new_x2, new_y2 
        if 'w' in handle and 'e' not in handle : new_x1 = new_x2 - new_bbox_w 
        elif 'e' in handle and 'w' not in handle : new_x2 = new_x1 + new_bbox_w 
        
        if 'n' in handle and 's' not in handle : new_y1 = new_y2 - new_bbox_h 
        elif 's' in handle and 'n' not in handle : new_y2 = new_y1 + new_bbox_h 

        if handle == 'nw': new_x1 = temp_x2 - new_bbox_w; new_y1 = temp_y2 - new_bbox_h; new_x2 = temp_x2; new_y2 = temp_y2
        elif handle == 'ne': new_x2 = temp_x1 + new_bbox_w; new_y1 = temp_y2 - new_bbox_h; new_x1 = temp_x1; new_y2 = temp_y2
        elif handle == 'sw': new_x1 = temp_x2 - new_bbox_w; new_y2 = temp_y1 + new_bbox_h; new_x2 = temp_x2; new_y1 = temp_y1
        elif handle == 'se': new_x2 = temp_x1 + new_bbox_w; new_y2 = temp_y1 + new_bbox_h; new_x1 = temp_x1; new_y1 = temp_y1


        if item_info_for_resize['type'] == 'image':
            orig_pil_w = resize_pil_img.width 
            orig_pil_h = resize_pil_img.height
            aspect_ratio = orig_pil_w / orig_pil_h if orig_pil_h > 0 else 1.0
            
            final_pil_w, final_pil_h = new_bbox_w, new_bbox_h 

            if len(handle) == 2: 
                if orig_pil_w == 0 or orig_pil_h == 0: pass 
                elif new_bbox_w / orig_pil_w > new_bbox_h / orig_pil_h:
                    final_pil_w = new_bbox_w
                    final_pil_h = final_pil_w / aspect_ratio
                else:
                    final_pil_h = new_bbox_h
                    final_pil_w = final_pil_h * aspect_ratio
            
            final_pil_w = max(1, int(round(final_pil_w))) 
            final_pil_h = max(1, int(round(final_pil_h)))

            new_x1_calc, new_y1_calc = new_x1, new_y1 
            if handle == 'nw': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y2 - final_pil_h
            elif handle == 'ne': new_x1_calc = new_x1; new_y1_calc = new_y2 - final_pil_h 
            elif handle == 'sw': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y1 
            elif handle == 'n': new_y1_calc = new_y2 - final_pil_h; new_x1_calc = new_x1 + (new_bbox_w - final_pil_w) / 2 
            elif handle == 's': new_y1_calc = new_y1; new_x1_calc = new_x1 + (new_bbox_w - final_pil_w) / 2
            elif handle == 'w': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y1 + (new_bbox_h - final_pil_h) / 2 
            elif handle == 'e': new_x1_calc = new_x1; new_y1_calc = new_y1 + (new_bbox_h - final_pil_h) / 2

            try:
                resized_pil = resize_pil_img.resize((final_pil_w, final_pil_h), Image.Resampling.LANCZOS)
                self._update_canvas_image(single_id, resized_pil, self.active_canvas_idx) 
                active_canvas.coords(single_id, int(round(new_x1_calc)), int(round(new_y1_calc))) 
                item_info_for_resize['width'] = final_pil_w 
                item_info_for_resize['height'] = final_pil_h
            except Exception as e: print(f"Image resize drag error: {e}")

        elif item_info_for_resize['type'] == 'widget':
            final_center_x = new_x1 + new_bbox_w / 2
            final_center_y = new_y1 + new_bbox_h / 2
            try:
                active_canvas.itemconfig(single_id, width=int(new_bbox_w), height=int(new_bbox_h))
                active_canvas.coords(single_id, final_center_x, final_center_y)
                item_info_for_resize['width'] = int(new_bbox_w)
                item_info_for_resize['height'] = int(new_bbox_h)
            except Exception as e: print(f"Widget resize drag error: {e}")
        
        self.update_highlight() 

    def on_resize_handle_release(self, event):
        active_canvas = self._get_active_canvas()
        
        self._set_active_resize_handle(None)
        self._set_active_resize_original_pil_image(None)
        self._set_active_resize_start_item_bbox(None)
        
        active_canvas.unbind("<B1-Motion>")
        active_canvas.unbind("<ButtonRelease-1>")
        
        active_canvas.bind("<ButtonPress-1>", lambda e, i=self.active_canvas_idx: \
            self._dispatch_canvas_event(e, i, self.on_canvas_press))

        active_canvas.config(cursor="")
        if self._get_active_selected_item_ids(): 
            self.update_highlight()


    def _update_canvas_image(self, item_id_to_update, new_pil_image, canvas_idx_of_item):
        canvas_widget = self.canvases[canvas_idx_of_item]
        canvas_items_list = self.canvas_items[canvas_idx_of_item]

        if not item_id_to_update or not new_pil_image: return 
        item_info = next((item for item in canvas_items_list if item['id'] == item_id_to_update and item['type'] == 'image'), None)
        if not item_info: print(f"Error: Could not find image item_info for ID {item_id_to_update} on canvas {canvas_idx_of_item}"); return
        try:
            new_tk_photo = ImageTk.PhotoImage(new_pil_image)
            canvas_widget.itemconfig(item_id_to_update, image=new_tk_photo)
            item_info['obj'] = new_tk_photo 
        except Exception as e:
            print(f"キャンバス画像の更新エラー (_update_canvas_image): {e}")
            tkinter.messagebox.showerror("画像更新エラー", f"画像の更新中にエラーが発生しました:\n{e}")

    def on_grid_size_change(self):
        try:
            new_spacing = self.prop_grid_size.get()
            if new_spacing >= 1:  
                if self.grid_spacing != new_spacing:
                    self.grid_spacing = new_spacing
                    for i in range(self.num_canvases):
                        self.draw_grid(i) 
            else: self.prop_grid_size.set(self.grid_spacing) 
        except tk.TclError: pass
        except Exception as e:
            print(f"グリッドサイズ変更エラー: {e}")
            if hasattr(self, 'grid_spacing'): self.prop_grid_size.set(self.grid_spacing) 

    def on_canvas_resize(self, event):
        resized_canvas_idx = -1
        for idx, c in enumerate(self.canvases):
            if event.widget == c:
                resized_canvas_idx = idx
                break
        if resized_canvas_idx != -1:
            self.draw_grid(resized_canvas_idx)

    def on_delete_key_press(self, event):
        widget_with_focus = self.focus_get()
        if isinstance(widget_with_focus, (ttk.Entry, tk.Text, ttk.Spinbox)): return 
        
        focused_canvas_idx = -1
        for idx, c_widget in enumerate(self.canvases):
            if widget_with_focus == c_widget:
                focused_canvas_idx = idx
                break
        
        if focused_canvas_idx == -1 and hasattr(widget_with_focus, 'winfo_parent'):
            parent_path = widget_with_focus.winfo_parent()
            for idx, c_widget in enumerate(self.canvases):
                if parent_path == str(c_widget): 
                    focused_canvas_idx = idx
                    break
        
        if focused_canvas_idx != -1:
            self.active_canvas_idx = focused_canvas_idx 
            if self._get_active_selected_item_ids(): 
                self.delete_selected_item() 
                return "break" 
        return 

    def delete_selected_item(self): 
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()
        active_selected_ids = self._get_active_selected_item_ids()

        if not active_selected_ids: return

        ids_to_delete = list(active_selected_ids) 
        for item_id in ids_to_delete:
            item_to_delete_info = None
            item_index = -1
            for i, item_info_iter in enumerate(active_canvas_items):
                if item_info_iter['id'] == item_id:
                    item_to_delete_info = item_info_iter
                    item_index = i
                    break
            
            if item_to_delete_info:
                if item_to_delete_info['type'] == 'widget' and item_to_delete_info.get('obj'):
                    item_to_delete_info['obj'].destroy()
                active_canvas.delete(item_id) 
                if item_index != -1:
                    del active_canvas_items[item_index]
        
        self.deselect_all() 

    def draw_grid(self, canvas_idx_to_draw):
        canvas_to_draw = self.canvases[canvas_idx_to_draw]
        grid_tag = f"grid_line_{canvas_idx_to_draw}"
        canvas_to_draw.delete(grid_tag) 
        
        w, h = canvas_to_draw.winfo_width(), canvas_to_draw.winfo_height()
        if self.grid_spacing > 0 and w > 0 and h > 0 : 
            for x_coord in range(0, w, self.grid_spacing): 
                canvas_to_draw.create_line(x_coord,0,x_coord,h,fill="#e0e0e0",tags=grid_tag)
            for y_coord in range(0, h, self.grid_spacing): 
                canvas_to_draw.create_line(0,y_coord,w,y_coord,fill="#e0e0e0",tags=grid_tag)
            canvas_to_draw.tag_lower(grid_tag)

    def _snap_to_grid(self, x, y):
        if self.grid_spacing <= 0: return x, y
        return round(x/self.grid_spacing)*self.grid_spacing, round(y/self.grid_spacing)*self.grid_spacing

    def _get_python_list_from_tcl_list(self, tcl_list_representation):
        if not tcl_list_representation: return []
        if isinstance(tcl_list_representation, (list, tuple)): return [str(item) for item in tcl_list_representation]
        if isinstance(tcl_list_representation, str):
            try: return list(self.tk.splitlist(tcl_list_representation))
            except tk.TclError: return [] 
        try:
            return list(self.tk.splitlist(str(tcl_list_representation)))
        except (tk.TclError, TypeError): 
            if hasattr(tcl_list_representation, '__iter__'):
                 try: return [str(v) for v in tcl_list_representation]
                 except Exception: pass 
            return []

    def save_layout(self):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()

        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")], title=f"レイアウトを保存 (Canvas {self.active_canvas_idx + 1})")
        if not filepath: return
        
        full_layout_data = {"general_settings": {"grid_spacing": self.grid_spacing}, "items": []}
        
        for item_info_loop in active_canvas_items: 
            item_id = item_info_loop['id']
            item_type = item_info_loop['type']
            
            bbox = active_canvas.bbox(item_id) 
            if not bbox: continue

            top_left_x, top_left_y = bbox[0], bbox[1]
            item_width = item_info_loop.get('width', bbox[2] - bbox[0]) 
            item_height = item_info_loop.get('height', bbox[3] - bbox[1])
            
            item_data = {"id_on_canvas": item_id, "type": item_type, "x": top_left_x, "y": top_left_y,
                         "width": int(item_width), "height": int(item_height)}

            if item_type == 'widget':
                widget_obj = item_info_loop['obj'] 
                item_data['widget_class_name'] = widget_obj.winfo_class() 
                item_data['widget_module'] = 'tk' if not item_data['widget_class_name'].startswith('T') else 'ttk'
                
                text_val = ""; 
                if isinstance(widget_obj, (ttk.Entry, ttk.Combobox)): text_val = widget_obj.get()
                elif hasattr(widget_obj, "cget"):
                    try: text_val = widget_obj.cget("text")
                    except tk.TclError: pass
                item_data['text'] = str(text_val)
                
                try:
                    font_actual = tkfont.Font(font=widget_obj.cget("font")).actual()
                    item_data['font'] = {'family': str(font_actual['family']), 
                                         'size': abs(font_actual['size']), 
                                         'weight': str(font_actual['weight']), 
                                         'slant': str(font_actual['slant'])}
               
                except tk.TclError: pass 
                
                if hasattr(widget_obj, 'cget') and 'anchor' in widget_obj.keys():
                    try: item_data['anchor'] = str(widget_obj.cget('anchor'))
                    except tk.TclError: pass

                colors = {}; 
                try: 
                    fg_opt = 'foreground' if isinstance(widget_obj, (ttk.Label, ttk.Entry, ttk.Combobox)) else 'fg'
                    colors['fg'] = str(widget_obj.cget(fg_opt))
                except tk.TclError: pass



                try:
                    if isinstance(widget_obj, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
                        colors['bg'] = str(widget_obj.cget('bg'))
                except tk.TclError:
                    pass
                if colors:
                    item_data['colors'] = colors

                if isinstance(widget_obj, ttk.Combobox):
                    item_data['values'] = self._get_python_list_from_tcl_list(widget_obj.cget('values'))
            elif item_type == 'image':
                item_data['path'] = str(item_info_loop['path'])
            full_layout_data["items"].append(item_data)
            
        try:
            with open(filepath, 'w', encoding='utf-8') as f: 
                json.dump(full_layout_data, f, indent=4, ensure_ascii=False)
        except TypeError as e:
            print(f"レイアウト保存エラー (TypeError): {e}"); tkinter.messagebox.showerror("保存エラー", f"レイアウトの保存中に型エラー: {e}")
        except Exception as e:
            print(f"レイアウト保存エラー: {e}"); tkinter.messagebox.showerror("保存エラー", f"レイアウトの保存中にエラー: {e}")

    def open_layout(self):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items() 
        active_selected_ids = self._get_active_selected_item_ids()
        active_highlight_rects = self._get_active_highlight_rects()

        filepath = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")], title=f"レイアウトを開く (Canvas {self.active_canvas_idx + 1})")
        if not filepath: return
        
        for item_info_to_delete in list(active_canvas_items): 
            if item_info_to_delete['type'] == 'widget' and item_info_to_delete.get('obj'):
                item_info_to_delete['obj'].destroy()
            active_canvas.delete(item_info_to_delete['id'])
        active_canvas_items.clear() 
        
        active_selected_ids.clear()
        self.selected_widget = None 
        self.selected_item_info = None 
        
        for rect_id in list(active_highlight_rects.values()): 
            active_canvas.delete(rect_id)
        active_highlight_rects.clear()
        active_canvas.delete(f"{self.ALL_RESIZE_HANDLES_TAG}_{self.active_canvas_idx}")
        
        self.update_property_editor() 

        try:
            with open(filepath, 'r', encoding='utf-8') as f: 
                full_layout_data = json.load(f)
        except Exception as e:
            print(f"レイアウトファイル読み込みエラー: {e}"); tkinter.messagebox.showerror("オープンエラー", f"レイアウトファイルの読み込み中にエラー: {e}"); return

        general_settings = full_layout_data.get("general_settings", {})
        loaded_grid_spacing = general_settings.get("grid_spacing", 20) 
        self.grid_spacing = loaded_grid_spacing; self.prop_grid_size.set(loaded_grid_spacing) 
        self.draw_grid(self.active_canvas_idx) 

        items_data = full_layout_data.get("items", [])
        for info in items_data:
            item_type = info.get('type')
            load_x, load_y = info.get('x'), info.get('y')
            load_w, load_h = info.get('width'), info.get('height') 

            if item_type == 'widget':
                widget_class_name = info.get('widget_class_name', ''); widget_type_simple = widget_class_name.replace('T','').lower() if widget_class_name else ''
                load_anchor = info.get('anchor', 'center') 
                self.add_widget(widget_type=widget_type_simple, text=info.get('text'), x=load_x, y=load_y,
                                values=info.get('values'), font_info=info.get('font'), colors=info.get('colors'),
                                width=load_w, height=load_h, anchor=load_anchor)
            elif item_type == 'image':
                try:
                    pil_image_orig = Image.open(info['path'])
                    saved_pil_width = int(load_w if load_w is not None else pil_image_orig.width)
                    saved_pil_height = int(load_h if load_h is not None else pil_image_orig.height)
                    pil_image_resized = pil_image_orig.resize((saved_pil_width, saved_pil_height), Image.Resampling.LANCZOS)
                    tk_photo = ImageTk.PhotoImage(pil_image_resized)
                    
                    img_id = active_canvas.create_image(load_x, load_y, image=tk_photo, anchor=tk.NW)
                    new_item_info = {'id': img_id, 'type': 'image', 'obj': tk_photo, 'path': info['path'], 
                                     'width': pil_image_resized.width, 'height': pil_image_resized.height, 
                                     'original_pil_image': pil_image_orig }
                    active_canvas_items.append(new_item_info)
                    
                    active_canvas.tag_bind(img_id, "<ButtonPress-1>", 
                                           lambda e, item=img_id, c_idx=self.active_canvas_idx: \
                                           self._dispatch_item_event(e, c_idx, item, self.on_canvas_item_press))

                except FileNotFoundError: tkinter.messagebox.showwarning("画像読み込みエラー", f"画像ファイルが見つかりません:\n{info.get('path')}")
                except Exception as e: print(f"Error image {info.get('path')}: {e}"); tkinter.messagebox.showwarning("画像読み込みエラー", f"画像 {info.get('path')} 再作成失敗:\n{e}")

    def generate_code(self):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()

        code_window = tk.Toplevel(self); code_window.title(f"Generated Code (Canvas {self.active_canvas_idx + 1})"); code_window.geometry("700x750")
        text_area = tk.Text(code_window, wrap="word", font=("Courier New", 10))
        scrollbar = ttk.Scrollbar(code_window, command=text_area.yview)
        text_area.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y"); text_area.pack(expand=True, fill="both")
        
        code_lines = [
            "import tkinter as tk", "from tkinter import ttk", "import tkinter.font as tkfont",
            "from PIL import Image, ImageTk\n", "class App(tk.Tk):", "    def __init__(self):",
            "        super().__init__()", f"        self.title('Generated Layout - Canvas {self.active_canvas_idx + 1}')",
            f"        self.geometry('{active_canvas.winfo_width()}x{active_canvas.winfo_height()}')\n",
            "        self._image_references_generated_app = [] \n"
        ]
        widget_counter = 0 
        for item_info_loop in active_canvas_items: 
            widget_counter += 1; var_name = f"self.item_{widget_counter}" 
            item_id = item_info_loop['id']; item_type = item_info_loop['type']
            bbox = active_canvas.bbox(item_id)
            if not bbox: continue
            place_x, place_y = int(bbox[0]), int(bbox[1])
            item_w = item_info_loop.get('width', bbox[2] - bbox[0])
            item_h = item_info_loop.get('height', bbox[3] - bbox[1])


            if item_type == 'widget':
                widget_obj = item_info_loop['obj']
                class_name = item_info_loop.get('widget_class_name', widget_obj.winfo_class())
                module_name = 'tk' if not class_name.startswith('T') else 'ttk'
                actual_class_name = class_name.replace('T','') if module_name == 'ttk' else class_name
                opts_list = []
                text_val = widget_obj.get() if isinstance(widget_obj, (ttk.Entry, ttk.Combobox)) else widget_obj.cget("text")
                if not isinstance(widget_obj, ttk.Entry): opts_list.append(f"text='{str(text_val).replace('\'', '\\\'')}'")
                try:
                    font_actual = tkfont.Font(font=widget_obj.cget("font")).actual()
                    f_fam = font_actual['family'].replace('\'', '\\\''); f_siz = abs(font_actual['size']); f_sty = []
                    if font_actual['weight'] == 'bold': f_sty.append('bold')
                    if font_actual['slant'] == 'italic': f_sty.append('italic')
                    opts_list.append(f"font=('{f_fam}', {f_siz}, '{' '.join(f_sty)}')")
                except tk.TclError: pass
                if hasattr(widget_obj, 'cget') and 'anchor' in widget_obj.keys():
                    try:
                        anchor_val = str(widget_obj.cget('anchor'))
                        if anchor_val and anchor_val != "center": opts_list.append(f"anchor='{anchor_val}'") 
                    except tk.TclError: pass
                try:
                    fg_opt_name = 'foreground' if isinstance(widget_obj, (ttk.Label, ttk.Entry, ttk.Combobox)) else 'fg'
                    opts_list.append(f"{fg_opt_name}='{widget_obj.cget(fg_opt_name)}'")
                except tk.TclError: pass
                try: 
                    if isinstance(widget_obj, (tk.Button, tk.Checkbutton, tk.Radiobutton)): 
                        opts_list.append(f"background='{widget_obj.cget('bg')}'")
                except tk.TclError: pass
                if isinstance(widget_obj, ttk.Combobox):
                    opts_list.append(f"values={self._get_python_list_from_tcl_list(widget_obj.cget('values'))}")
                
                opt_str = ", ".join(opts_list)
                code_lines.append(f"        {var_name} = {module_name}.{actual_class_name}(self{', ' if opt_str else ''}{opt_str})")
                if isinstance(widget_obj, ttk.Entry) and text_val: code_lines.append(f"        {var_name}.insert(0, '{str(text_val).replace('\'', '\\\'')}')")
                if isinstance(widget_obj, ttk.Combobox) and text_val: 
                    python_current_values = self._get_python_list_from_tcl_list(widget_obj.cget('values'))
                    if text_val in python_current_values: code_lines.append(f"        {var_name}.set('{str(text_val).replace('\'', '\\\'')}')")
                    elif python_current_values: code_lines.append(f"        {var_name}.current(0)")
                
                place_opts_list = [f"x={place_x}", f"y={place_y}"]
                code_lines.append(f"        {var_name}.place({', '.join(place_opts_list)})\n")

            elif item_type == 'image':
                img_path_escaped = item_info_loop['path'].replace('\\', '\\\\')
                img_w, img_h = int(item_info_loop['width']), int(item_info_loop['height']) 
                code_lines.extend([
                    f"        # Image: {img_path_escaped}", "        try:",
                    f"            pil_img_{widget_counter} = Image.open(r'{img_path_escaped}')",
                    f"            pil_img_{widget_counter} = pil_img_{widget_counter}.resize(({img_w}, {img_h}), Image.Resampling.LANCZOS)",
                    f"            {var_name}_img_tk = ImageTk.PhotoImage(pil_img_{widget_counter})",
                    f"            self._image_references_generated_app.append({var_name}_img_tk) ",
                    f"            {var_name} = tk.Label(self, image={var_name}_img_tk, borderwidth=0)",
                    f"            {var_name}.place(x={place_x}, y={place_y})", 
                    f"        except Exception as e:",
                    f"            print(f'Error loading image {{e}} for {var_name}')\n"
                ])
        code_lines.extend(["\nif __name__ == '__main__':", "    app = App()", "    app.mainloop()"])
        text_area.insert("1.0", "\n".join(code_lines)); text_area.config(state="disabled")


if __name__ == "__main__":
    app = LayoutDesigner()
    app.mainloop()
