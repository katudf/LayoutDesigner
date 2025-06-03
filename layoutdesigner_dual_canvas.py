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
        self._drag_start_x = [0] * self.num_canvases # Mouse X on canvas at drag start
        self._drag_start_y = [0] * self.num_canvases # Mouse Y on canvas at drag start
        self._active_drag_item_offset = [(0,0)] * self.num_canvases # Offset from item's top-left to mouse click
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
        
        # ウィンドウのConfigureイベントのバインドを解除またはコメントアウト
        # self.bind("<Configure>", self._update_size_entries_on_configure)
        
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

    def _set_active_drag_start_coords(self, x, y): # Mouse coords on canvas
        self._drag_start_x[self.active_canvas_idx] = x
        self._drag_start_y[self.active_canvas_idx] = y
    
    def _get_active_drag_start_coords(self):
        return self._drag_start_x[self.active_canvas_idx], self._drag_start_y[self.active_canvas_idx]

    def _set_active_drag_item_offset(self, offset_x, offset_y): # Offset from item TL to click
        self._active_drag_item_offset[self.active_canvas_idx] = (offset_x, offset_y)

    def _get_active_drag_item_offset(self):
        return self._active_drag_item_offset[self.active_canvas_idx]

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
        if event.widget not in self.canvases:
            parent_widget_str = str(event.widget.winfo_parent())
            determined_idx = -1
            for idx_loop, cv_loop in enumerate(self.canvases): # Use different loop var names
                if event.widget == cv_loop: 
                    determined_idx = idx_loop
                    break
                if parent_widget_str == str(cv_loop):
                    determined_idx = idx_loop
                    break
            
            if determined_idx != -1:
                self.active_canvas_idx = determined_idx
            else: 
                self.active_canvas_idx = canvas_idx # Fallback to lambda's captured index
        else: 
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
            grid_frame, from_=5, to=100, increment=1,
            textvariable=self.prop_grid_size, command=self.on_grid_size_change, width=5
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
                # ユーザーが明示的に適用した場合、initial_width/heightも更新する（任意）
                # self.initial_width = new_width
                # self.initial_height = new_height
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
        # このメソッドは呼ばれなくなりますが、念のため残しておきます。
        # if event and event.widget == self:
        #     self.window_width_var.set(str(self.winfo_width()))
        #     self.window_height_var.set(str(self.winfo_height()))
        pass # 何もしない
    
    def _update_sash_entry_on_release(self, event=None):
        if hasattr(self, 'main_paned_window') and self.main_paned_window.panes():
            try:
                sash_position = self.main_paned_window.sashpos(0)
                self.sash_pos_var.set(str(sash_position))
            except tk.TclError: pass 

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
        anchor_frame = ttk.Frame(self.property_frame); anchor_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(anchor_frame, text="Anchor:", font=("Helvetica", 12)).pack(anchor="w")
        anchor_buttons_frame = ttk.Frame(anchor_frame); anchor_buttons_frame.pack(pady=2)
        self.prop_anchor = tk.StringVar() 
        self.anchor_buttons = {} 
        anchor_positions = [['nw', 'n', 'ne'], ['w', 'center', 'e'], ['sw', 's', 'se']]
        for r, row_anchors in enumerate(anchor_positions):
            self.anchor_buttons[r] = {}
            row_frame = ttk.Frame(anchor_buttons_frame); row_frame.pack()
            for c, anchor_val in enumerate(row_anchors):
                btn = ttk.Button(row_frame, text=anchor_val.upper(), width=4,
                                 command=lambda val=anchor_val: self.on_anchor_button_click(val),
                                 style=self.default_anchor_style_name)
                btn.pack(side="left", padx=1, pady=1); self.anchor_buttons[r][c] = btn
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
        self.delete_button = ttk.Button(self.property_frame, text="選択項目を削除", command=self.delete_selected_item, state="disabled")
        self.delete_button.pack(pady=5, padx=10, fill='x')
        self.text_entry.config(state="disabled"); self.values_entry.config(state="disabled")
        self._set_font_ui_state("disabled"); self._set_anchor_ui_state("disabled"); self._set_color_ui_state("disabled")

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
            raw_x = active_canvas.winfo_width() / 2; raw_y = active_canvas.winfo_height() / 2
            snapped_x, snapped_y = self._snap_to_grid(raw_x, raw_y) 
            image_item_id = active_canvas.create_image(snapped_x, snapped_y, image=tk_photo_image, anchor=tk.NW)
            item_info = {
                'id': image_item_id, 'type': 'image', 'obj': tk_photo_image, 
                'path': filepath, 'width': current_pil_image.width, 'height': current_pil_image.height, 
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
            widget_args['text'] = text or "Button"; w = tk.Button(active_canvas, **widget_args)
            if fg_color: w.config(fg=fg_color) # Use config for tk widgets after creation for some properties
            if bg_color: w.config(bg=bg_color)
        elif widget_type == "label":
            widget_args['text'] = text or "Label"; w = ttk.Label(active_canvas, **widget_args)
            if fg_color: w.config(foreground=fg_color)
        elif widget_type == "checkbutton":
            widget_args['text'] = text or "Checkbutton"; w = tk.Checkbutton(active_canvas, **widget_args)
            if fg_color: w.config(fg=fg_color)
            if bg_color: w.config(bg=bg_color)
        elif widget_type == "radiobutton":
            widget_args['text'] = text or "Radiobutton"; w = tk.Radiobutton(active_canvas, **widget_args)
            if fg_color: w.config(fg=fg_color)
            if bg_color: w.config(bg=bg_color)
        elif widget_type == "entry":
            w = ttk.Entry(active_canvas, **widget_args); 
            if text: w.insert(0, text)
        elif widget_type == "combobox":
            w = ttk.Combobox(active_canvas, **widget_args)
            w['values'] = values if values else ["Item 1", "Item 2"]
            w.set(text if text else (w['values'][0] if w['values'] else ""))
        else: print(f"Unknown widget type: {widget_type}"); return
        
        canvas_x_center = x if x is not None else active_canvas.winfo_width() / 2
        canvas_y_center = y if y is not None else active_canvas.winfo_height() / 2
        canvas_id = active_canvas.create_window(canvas_x_center, canvas_y_center, window=w)
        if width is not None and height is not None:
            try: active_canvas.itemconfig(canvas_id, width=int(width), height=int(height))
            except (ValueError, tk.TclError) as e: print(f"Error setting loaded w/h: {e}")
        self.update_idletasks() 
        bbox_coords = active_canvas.bbox(canvas_id)
        actual_widget_width = bbox_coords[2] - bbox_coords[0] if bbox_coords else w.winfo_reqwidth()
        actual_widget_height = bbox_coords[3] - bbox_coords[1] if bbox_coords else w.winfo_reqheight()
        desired_top_left_x = (x if x is not None else canvas_x_center - actual_widget_width / 2)
        desired_top_left_y = (y if y is not None else canvas_y_center - actual_widget_height / 2)
        snapped_tl_x, snapped_tl_y = self._snap_to_grid(desired_top_left_x, desired_top_left_y)
        final_center_x = snapped_tl_x + actual_widget_width / 2
        final_center_y = snapped_tl_y + actual_widget_height / 2
        active_canvas.coords(canvas_id, final_center_x, final_center_y)
        item_info = {
            'id': canvas_id, 'type': 'widget', 'obj': w, 'widget_type': widget_type,
            'width': actual_widget_width, 'height': actual_widget_height
        }
        active_canvas_items.append(item_info)
        current_canvas_idx_for_item = self.active_canvas_idx 
        w.bind("<ButtonPress-1>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: self._dispatch_item_event(e, c_idx, i_id, self.on_canvas_item_press))
        w.bind("<B1-Motion>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: self._dispatch_item_event(e, c_idx, i_id, self.on_multi_item_drag))
        w.bind("<ButtonRelease-1>", lambda e, i_id=canvas_id, c_idx=current_canvas_idx_for_item: self._dispatch_item_event(e, c_idx, i_id, self.on_multi_item_release))

    def _dispatch_item_event(self, event, canvas_idx_of_item, item_id, handler_method):
        self.active_canvas_idx = canvas_idx_of_item
        if hasattr(self.canvases[self.active_canvas_idx], 'focus_set'):
            self.canvases[self.active_canvas_idx].focus_set() 
        handler_method(event, item_id)

    def on_canvas_press(self, event):
        active_canvas = self._get_active_canvas()
        active_canvas_items = self._get_active_canvas_items()
        overlapping_ids = active_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        is_on_resize_handle = False
        if overlapping_ids:
            for item_id_overlap in overlapping_ids:
                tags = active_canvas.gettags(item_id_overlap)
                if any(tag.startswith(f"{self.RESIZE_HANDLE_TAG_PREFIX}") and tag.endswith(f"_{self.active_canvas_idx}") for tag in tags):
                    is_on_resize_handle = True; break 
        if is_on_resize_handle: return 
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
                        clicked_item_id = item_id_overlap; break
        if not clicked_item_id and not self._get_active_dragged_item_id(): 
            self.deselect_all() 
        
    def deselect_all(self):
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        active_highlight_rects = self._get_active_highlight_rects()
        if active_selected_ids: active_selected_ids.clear()
        self.selected_widget = None; self.selected_item_info = None 
        for rect_id in active_highlight_rects.values(): active_canvas.delete(rect_id)
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
        try: # Convert mouse coords if event is on the item itself
            if event.widget != active_canvas: 
                abs_x = event.widget.winfo_rootx() + event.x; abs_y = event.widget.winfo_rooty() + event.y
                canvas_x = abs_x - active_canvas.winfo_rootx(); canvas_y = abs_y - active_canvas.winfo_rooty()
        except Exception: pass 
        
        self._set_active_drag_start_coords(canvas_x, canvas_y) # Store raw mouse click on canvas

        # Record offset from item's top-left to the click point
        bbox = active_canvas.bbox(item_id)
        if bbox:
            self._set_active_drag_item_offset(canvas_x - bbox[0], canvas_y - bbox[1])
        else:
            self._set_active_drag_item_offset(0,0)

        is_shift_pressed = (event.state & 0x0001) != 0
        if not is_shift_pressed:
            if item_id not in active_selected_ids or len(active_selected_ids) > 1: 
                current_selection_copy = set(active_selected_ids) 
                active_hr = self._get_active_highlight_rects()
                for prev_id in current_selection_copy:
                    if prev_id in active_hr: active_canvas.delete(active_hr[prev_id]); del active_hr[prev_id]
                active_selected_ids.clear(); active_selected_ids.add(item_id)
        else: 
            active_hr = self._get_active_highlight_rects()
            if item_id in active_selected_ids: 
                active_selected_ids.remove(item_id)
                if item_id in active_hr: active_canvas.delete(active_hr[item_id]); del active_hr[item_id]
            else: active_selected_ids.add(item_id)

        active_drag_bboxes.clear() 
        for s_id in active_selected_ids:
            bbox_val = active_canvas.bbox(s_id) # Renamed to avoid conflict
            if bbox_val: active_drag_bboxes[s_id] = bbox_val

        self.update_property_editor_for_selection() 
        self.update_highlight() 

        if active_selected_ids:
            for s_id in active_selected_ids: active_canvas.tag_raise(s_id) 
            active_canvas.bind("<B1-Motion>", lambda e, c_idx=self.active_canvas_idx: self._dispatch_canvas_event(e, c_idx, self.on_multi_item_drag))
            active_canvas.bind("<ButtonRelease-1>", lambda e, c_idx=self.active_canvas_idx: self._dispatch_canvas_event(e, c_idx, self.on_multi_item_release))

    def update_property_editor_for_selection(self):
        active_selected_ids = self._get_active_selected_item_ids()
        active_canvas_items = self._get_active_canvas_items()
        self.selected_widget = None; self.selected_item_info = None 
        if len(active_selected_ids) == 1:
            single_id = list(active_selected_ids)[0]
            item_info = next((item for item in active_canvas_items if item['id'] == single_id), None)
            if item_info:
                self.selected_item_info = item_info 
                if item_info['type'] == 'widget': self.selected_widget = item_info['obj'] 
        self.update_property_editor()

    def on_multi_item_drag(self, event, item_id_param=None): # item_id_param not used from event binding
        active_canvas = self._get_active_canvas()
        active_selected_ids = self._get_active_selected_item_ids()
        dragged_item_id_from_state = self._get_active_dragged_item_id() 
        active_resize_h = self._get_active_resize_handle()
        start_bboxes_map = self._get_active_drag_selected_items_start_bboxes() # Map of id:bbox
        active_canvas_items = self._get_active_canvas_items()

        if not dragged_item_id_from_state or not active_selected_ids or active_resize_h:
            return

        current_mouse_x_canvas = event.x
        current_mouse_y_canvas = event.y
        
        item_offset_x, item_offset_y = self._get_active_drag_item_offset()

        raw_new_primary_tl_x = current_mouse_x_canvas - item_offset_x
        raw_new_primary_tl_y = current_mouse_y_canvas - item_offset_y

        snapped_new_primary_tl_x, snapped_new_primary_tl_y = self._snap_to_grid(raw_new_primary_tl_x, raw_new_primary_tl_y)

        primary_start_bbox = start_bboxes_map.get(dragged_item_id_from_state)
        if not primary_start_bbox: return 

        effective_delta_x = snapped_new_primary_tl_x - primary_start_bbox[0]
        effective_delta_y = snapped_new_primary_tl_y - primary_start_bbox[1]

        for current_item_id_in_selection in active_selected_ids:
            if current_item_id_in_selection in start_bboxes_map:
                s_bbox = start_bboxes_map[current_item_id_in_selection]
                if not s_bbox: continue

                item_info = next((item for item in active_canvas_items if item['id'] == current_item_id_in_selection), None)
                if item_info:
                    width = s_bbox[2] - s_bbox[0]
                    height = s_bbox[3] - s_bbox[1]

                    new_tl_x = s_bbox[0] + effective_delta_x
                    new_tl_y = s_bbox[1] + effective_delta_y

                    if item_info['type'] == 'widget':
                        final_center_x = new_tl_x + width / 2
                        final_center_y = new_tl_y + height / 2
                        active_canvas.coords(current_item_id_in_selection, final_center_x, final_center_y)
                        item_info['width'] = width 
                        item_info['height'] = height
                    elif item_info['type'] == 'image':
                        active_canvas.coords(current_item_id_in_selection, new_tl_x, new_tl_y)
        self.update_highlight() 

    def on_multi_item_release(self, event, item_id=None): 
        active_canvas = self._get_active_canvas()
        self._set_active_dragged_item_id(None)
        self._get_active_drag_selected_items_start_bboxes().clear()
        self._set_active_drag_item_offset(0,0) # Reset offset
        active_canvas.unbind("<B1-Motion>"); active_canvas.unbind("<ButtonRelease-1>")
        active_canvas.bind("<ButtonPress-1>", lambda e, i=self.active_canvas_idx: self._dispatch_canvas_event(e, i, self.on_canvas_press))

    def update_property_editor(self):
        active_selected_ids = self._get_active_selected_item_ids(); num_selected = len(active_selected_ids)
        single_selected_item_info = self.selected_item_info; widget_obj = self.selected_widget
        is_single_widget = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'widget')
        is_single_image = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'image')
        self.text_entry.config(state="normal" if is_single_widget else "disabled")
        self.values_entry.config(state="normal" if is_single_widget and isinstance(widget_obj, ttk.Combobox) else "disabled")
        self._set_font_ui_state("normal" if is_single_widget else "disabled")
        anchor_ok = is_single_widget and isinstance(widget_obj, (tk.Label, ttk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton))
        self._set_anchor_ui_state("normal" if anchor_ok else "disabled")
        self._set_color_ui_state("normal" if is_single_widget else "disabled", widget_obj)
        self.delete_button.config(state="normal" if num_selected > 0 else "disabled")
        if is_single_widget and widget_obj and widget_obj.winfo_exists():
            self._updating_properties_internally = True 
            if isinstance(widget_obj, (ttk.Entry, ttk.Combobox)): self.prop_text.set(widget_obj.get())
            elif hasattr(widget_obj, 'cget'):
                try: self.prop_text.set(widget_obj.cget("text"))
                except tk.TclError: self.prop_text.set("")
            else: self.prop_text.set("")
            if isinstance(widget_obj, ttk.Combobox):
                self.prop_values.set(",".join(self._get_python_list_from_tcl_list(widget_obj.cget("values"))))
            else: self.prop_values.set("")
            try:
                font_obj = tkfont.Font(font=widget_obj.cget("font")); attrs = font_obj.actual()
                self.prop_font_family.set(attrs["family"]); self.prop_font_size.set(abs(attrs["size"])) 
                self.prop_font_bold.set(attrs["weight"] == "bold"); self.prop_font_italic.set(attrs["slant"] == "italic")
            except tk.TclError: self._set_font_ui_state("disabled") 
            if anchor_ok:
                try:
                    anchor = str(widget_obj.cget("anchor")); self.prop_anchor.set(anchor)
                    for r, btns in self.anchor_buttons.items():
                        for c, btn_w in btns.items():
                            btn_txt_low = btn_w.cget('text').lower()
                            btn_w.config(style=self.selected_anchor_style_name if btn_txt_low == anchor else self.default_anchor_style_name)
                except tk.TclError: 
                    self.prop_anchor.set("center") 
                    for r, btns in self.anchor_buttons.items():
                        for c, btn_w in btns.items(): btn_w.config(style=self.selected_anchor_style_name if btn_w.cget('text').lower() == 'center' else self.default_anchor_style_name)
            else: 
                self.prop_anchor.set("")
                for r, btns in self.anchor_buttons.items():
                    for c, btn_w in btns.items(): btn_w.config(style=self.default_anchor_style_name)
            try: 
                fg_opt = 'fg' if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)) else 'foreground'
                fg = widget_obj.cget(fg_opt); self.prop_fg_color.set(fg); self.fg_color_preview.config(bg=fg)
            except tk.TclError: self.prop_fg_color.set("#000000"); self.fg_color_preview.config(bg="#000000")
            if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)): 
                try: bg = widget_obj.cget('bg'); self.prop_bg_color.set(bg); self.bg_color_preview.config(bg=bg)
                except tk.TclError: self.prop_bg_color.set("#F0F0F0"); self.bg_color_preview.config(bg="#F0F0F0") 
            else: self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg')) 
            self._updating_properties_internally = False 
        elif is_single_image:
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
        active_canvas = self._get_active_canvas(); active_ids = self._get_active_selected_item_ids()
        active_rects = self._get_active_highlight_rects(); active_items = self._get_active_canvas_items()
        idx = self.active_canvas_idx 
        for rid in list(active_rects.values()): active_canvas.delete(rid)
        active_rects.clear(); active_canvas.delete(f"{self.ALL_RESIZE_HANDLES_TAG}_{idx}")
        if not active_ids: return
        for item_id in active_ids:
            try:
                coords = active_canvas.bbox(item_id)
                if not coords: continue
                x1,y1,x2,y2 = coords
                rid = active_canvas.create_rectangle(x1-1,y1-1,x2+1,y2+1,outline="gray",dash=(3,3),tags=(f"multi_highlight_rect_{idx}","multi_highlight_rect_common")) 
                active_rects[item_id] = rid
            except tk.TclError: pass 
        if len(active_ids) == 1:
            single_id = list(active_ids)[0]
            if single_id in active_rects: active_canvas.delete(active_rects[single_id]); del active_rects[single_id] 
            try:
                coords = active_canvas.bbox(single_id); 
                if not coords: return
                x1,y1,x2,y2 = coords
                pid = active_canvas.create_rectangle(x1-2,y1-2,x2+2,y2+2,outline="blue",width=1,tags=(f"primary_highlight_rect_{idx}","primary_highlight_rect_common"))
                active_rects[single_id] = pid 
                item_info = next((it for it in active_items if it['id'] == single_id), None)
                if item_info and (item_info['type'] == 'image' or item_info['type'] == 'widget'):
                    s = self.RESIZE_HANDLE_SIZE/2
                    h_defs={'nw':(x1,y1),'n':((x1+x2)/2,y1),'ne':(x2,y1),'w':(x1,(y1+y2)/2),'e':(x2,(y1+y2)/2),'sw':(x1,y2),'s':((x1+x2)/2,y2),'se':(x2,y2)}
                    ahs_tag = f"{self.ALL_RESIZE_HANDLES_TAG}_{idx}"
                    for ht, (hx,hy) in h_defs.items():
                        h_tag_spec = f"{self.RESIZE_HANDLE_TAG_PREFIX}{ht}_{idx}"
                        h_id = active_canvas.create_rectangle(hx-s,hy-s,hx+s,hy+s,fill="white",outline="black",tags=(ahs_tag,h_tag_spec,self.RESIZE_HANDLE_TAG_PREFIX+ht)) 
                        active_canvas.tag_bind(h_id,"<Enter>",lambda e,h=ht,c=idx:self.on_handle_enter(e,h,c))
                        active_canvas.tag_bind(h_id,"<Leave>",lambda e,c=idx:self.on_handle_leave(e,c))
                        active_canvas.tag_bind(h_id,"<ButtonPress-1>",lambda e,h=ht,c=idx:self.on_resize_handle_press(e,h,c))
                    active_canvas.tag_raise(ahs_tag); active_canvas.tag_raise(pid) 
            except tk.TclError: self.deselect_all() 

    def on_property_change(self, var_name_str, index, mode): 
        if self._updating_properties_internally: return 
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        txt = self.prop_text.get(); vals = self.prop_values.get()
        if var_name_str == str(self.prop_text): 
            if isinstance(self.selected_widget, ttk.Entry): self.selected_widget.delete(0,tk.END); self.selected_widget.insert(0,txt)
            elif isinstance(self.selected_widget, ttk.Combobox): self.selected_widget.set(txt)
            elif hasattr(self.selected_widget,'config') and 'text' in self.selected_widget.keys():
                try: self.selected_widget.config(text=txt)
                except tk.TclError: pass 
        elif var_name_str == str(self.prop_values): 
            if isinstance(self.selected_widget, ttk.Combobox):
                try:
                    curr_txt = self.selected_widget.get(); new_list = [v.strip() for v in vals.split(',') if v.strip()]
                    self.selected_widget.config(values=new_list)
                    if curr_txt in new_list: self.selected_widget.set(curr_txt)
                    elif new_list: self.selected_widget.current(0)
                    else: self.selected_widget.set("")
                except tk.TclError: pass 
        self.after(10, self.update_highlight) 

    def on_font_property_change(self, *args):
        if self._updating_properties_internally or self._updating_font_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        fam = self.prop_font_family.get(); sz = self.prop_font_size.get()
        if not fam or sz <= 0: return 
        sty = []
        if self.prop_font_bold.get(): sty.append("bold")
        if self.prop_font_italic.get(): sty.append("italic")
        try: self.selected_widget.config(font=(fam,sz," ".join(sty))); self.after(50,self.update_highlight) 
        except tk.TclError as e: print(f"Font Error: {e}")

    def on_anchor_button_click(self, new_anchor_value):
        if self._updating_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        if isinstance(self.selected_widget, (tk.Label, ttk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton)):
            try:
                self.selected_widget.config(anchor=new_anchor_value); self.prop_anchor.set(new_anchor_value) 
                for r,b_dict in self.anchor_buttons.items():
                    for c,btn in b_dict.items(): btn.config(style=self.selected_anchor_style_name if btn.cget('text').lower()==new_anchor_value else self.default_anchor_style_name)
            except tk.TclError as e: print(f"Anchor Error: {e}")

    def on_fg_color_change(self, *args):
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        clr = self.prop_fg_color.get()
        if len(clr) >= 4 and clr.startswith('#'): 
            try:
                opt = 'foreground' if isinstance(self.selected_widget,(ttk.Label,ttk.Entry,ttk.Combobox)) else 'fg'
                self.selected_widget.config(**{opt:clr}); self.fg_color_preview.config(bg=clr)
            except tk.TclError: pass 

    def on_bg_color_change(self, *args):
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self._get_active_selected_item_ids()) != 1: return
        if isinstance(self.selected_widget, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
            clr = self.prop_bg_color.get()
            if len(clr) >= 4 and clr.startswith('#'):
                try: self.selected_widget.config(background=clr); self.bg_color_preview.config(bg=clr)
                except tk.TclError: pass
        else: pass

    def open_fg_color_chooser(self):
        if self.selected_widget and self.fg_color_button['state']!='disabled' and len(self._get_active_selected_item_ids())==1:
            init_clr = self.prop_fg_color.get() or "#000000"
            code = colorchooser.askcolor(title="文字色を選択",initialcolor=init_clr)
            if code and code[1]: self.prop_fg_color.set(code[1])

    def open_bg_color_chooser(self):
        if self.selected_widget and self.bg_color_button['state']!='disabled' and len(self._get_active_selected_item_ids())==1:
            init_clr = self.prop_bg_color.get() or "#F0F0F0"
            code = colorchooser.askcolor(title="背景色を選択",initialcolor=init_clr)
            if code and code[1]: self.prop_bg_color.set(code[1])

    def on_handle_enter(self, event, handle_type, canvas_idx_of_handle):
        if len(self.selected_item_ids[canvas_idx_of_handle]) == 1: 
            cur = self.HANDLE_CURSORS.get(handle_type)
            if cur: self.canvases[canvas_idx_of_handle].config(cursor=cur)

    def on_handle_leave(self, event, canvas_idx_of_handle): 
        if not self.active_resize_handle[canvas_idx_of_handle]: 
            self.canvases[canvas_idx_of_handle].config(cursor="")

    def on_resize_handle_press(self, event, handle_type, canvas_idx_of_handle):
        self.active_canvas_idx = canvas_idx_of_handle 
        active_canvas = self._get_active_canvas()
        active_ids = self._get_active_selected_item_ids(); active_items = self._get_active_canvas_items()
        if len(active_ids) != 1: return 
        single_id = list(active_ids)[0]
        curr_item_info = next((it for it in active_items if it['id']==single_id),None)
        if not curr_item_info: return
        self.selected_item_info = curr_item_info 
        self._set_active_resize_handle(handle_type)
        mx_canvas = event.x_root - active_canvas.winfo_rootx()
        my_canvas = event.y_root - active_canvas.winfo_rooty()
        self._set_active_resize_start_mouse_coords(mx_canvas, my_canvas)
        self._set_active_resize_start_item_bbox(active_canvas.bbox(single_id))
        if self.selected_item_info['type'] == 'image':
            if 'original_pil_image' in self.selected_item_info:
                 self._set_active_resize_original_pil_image(self.selected_item_info['original_pil_image'].copy())
            else: 
                try: self._set_active_resize_original_pil_image(Image.open(self.selected_item_info['path']))
                except Exception as e: print(f"リサイズ用元画像読み込みエラー: {e}"); tkinter.messagebox.showerror("リサイズエラー",f"元画像読込失敗:\n{e}"); self._set_active_resize_handle(None); return
        elif self.selected_item_info['type'] == 'widget': self._set_active_resize_original_pil_image(None)
        active_canvas.unbind("<B1-Motion>"); active_canvas.unbind("<ButtonRelease-1>")
        active_canvas.bind("<B1-Motion>", lambda e, c=self.active_canvas_idx: self._dispatch_canvas_event(e,c,self.on_resize_handle_drag))
        active_canvas.bind("<ButtonRelease-1>", lambda e,c=self.active_canvas_idx: self._dispatch_canvas_event(e,c,self.on_resize_handle_release))

    def on_resize_handle_drag(self, event): 
        active_canvas = self._get_active_canvas(); active_rh = self._get_active_resize_handle()
        item_info_resize = self.selected_item_info; start_bbox = self._get_active_resize_start_item_bbox()
        pil_img = self._get_active_resize_original_pil_image(); smx,smy = self._get_active_resize_start_mouse_coords()
        if not all([active_rh, item_info_resize, start_bbox]):
            if not (item_info_resize and item_info_resize['type']=='image' and pil_img) and \
               not (item_info_resize and item_info_resize['type']=='widget'): return
        single_id = item_info_resize['id']; mouse_x = event.x; mouse_y = event.y
        curr_dx = mouse_x - smx; curr_dy = mouse_y - smy
        ox1,oy1,ox2,oy2 = start_bbox
        shift = (event.state & 0x0001) != 0
        final_dx,final_dy = curr_dx,curr_dy
        if shift and self.grid_spacing > 0:
            h = active_rh 
            if 'n' in h: ty=oy1+curr_dy; sy=self._snap_to_grid(0,ty)[1]; final_dy=sy-oy1
            if 's' in h: ty=oy2+curr_dy; sy=self._snap_to_grid(0,ty)[1]; final_dy=sy-oy2
            if 'w' in h: tx=ox1+curr_dx; sx=self._snap_to_grid(tx,0)[0]; final_dx=sx-ox1
            if 'e' in h: tx=ox2+curr_dx; sx=self._snap_to_grid(tx,0)[0]; final_dx=sx-ox2
        dx,dy = final_dx,final_dy; h = active_rh
        nx1,ny1,nx2,ny2 = ox1,oy1,ox2,oy2
        if 'n' in h: ny1=oy1+dy; 
        if 's' in h: ny2=oy2+dy; 
        if 'w' in h: nx1=ox1+dx; 
        if 'e' in h: nx2=ox2+dx; 
        
        if nx1 > nx2: nx1,nx2 = nx2,nx1
        if ny1 > ny2: ny1,ny2 = ny2,ny1

        nbw,nbh = nx2-nx1,ny2-ny1
        min_dim = self.RESIZE_HANDLE_SIZE*2 
        nbw=max(min_dim,nbw); nbh=max(min_dim,nbh)

        # Recalculate coordinates based on fixed point and new width/height
        # This logic ensures the correct corner/edge stays 'anchored' during resize
        if h == 'nw': nx1=nx2-nbw; ny1=ny2-nbh
        elif h == 'n': nx1=ox1; ny1=ny2-nbh; nx2=ox2 # X fixed, Y1 changes
        elif h == 'ne': ny1=ny2-nbh; nx2=nx1+nbw # Y1 changes, X2 changes relative to X1
        elif h == 'w': nx1=nx2-nbw; ny1=oy1; ny2=oy2 # Y fixed, X1 changes
        elif h == 'e': nx2=nx1+nbw; ny1=oy1; ny2=oy2 # Y fixed, X2 changes relative to X1
        elif h == 'sw': nx1=nx2-nbw; ny2=ny1+nbh # X1 changes, Y2 changes relative to Y1
        elif h == 's': nx1=ox1; ny2=ny1+nbh; nx2=ox2 # X fixed, Y2 changes
        elif h == 'se': nx2=nx1+nbw; ny2=ny1+nbh # X1, Y1 fixed, X2, Y2 change
        
        if item_info_resize['type'] == 'image':
            opw=pil_img.width; oph=pil_img.height; aspect=opw/oph if oph>0 else 1.0
            fpw,fph = nbw,nbh 
            if len(h)==2: 
                if opw==0 or oph==0: pass 
                elif nbw/opw > nbh/oph: fpw=nbw; fph=fpw/aspect
                else: fph=nbh; fpw=fph*aspect
            fpw=max(1,int(round(fpw))); fph=max(1,int(round(fph)))
            
            # Adjust final canvas bbox based on aspect-corrected fpw/fph and handle
            # The goal is to place the resized image correctly according to the dragged handle
            if h == 'nw': nx1_calc = nx2 - fpw; ny1_calc = ny2 - fph
            elif h == 'n': ny1_calc = ny2 - fph; nx1_calc = nx1 + (nbw - fpw) / 2 
            elif h == 'ne': ny1_calc = ny2 - fph; nx1_calc = nx1 # x1 is fixed, width grows to fpw
            elif h == 'w': nx1_calc = nx2 - fpw; ny1_calc = ny1 + (nbh - fph) / 2
            elif h == 'e': nx1_calc = nx1; ny1_calc = ny1 + (nbh - fph) / 2 # x1 fixed, y centered
            elif h == 'sw': nx1_calc = nx2 - fpw; ny1_calc = ny1
            elif h == 's': ny1_calc = ny1; nx1_calc = nx1 + (nbw - fpw) / 2
            elif h == 'se': nx1_calc = nx1; ny1_calc = ny1 # x1,y1 fixed
            else: # Should not happen
                nx1_calc, ny1_calc = nx1, ny1


            try:
                r_pil = pil_img.resize((fpw,fph),Image.Resampling.LANCZOS)
                self._update_canvas_image(single_id,r_pil,self.active_canvas_idx) 
                active_canvas.coords(single_id,int(round(nx1_calc)),int(round(ny1_calc))) 
                item_info_resize['width']=fpw; item_info_resize['height']=fph
            except Exception as e: print(f"Image resize drag error: {e}")
        elif item_info_resize['type'] == 'widget':
            fcx=nx1+nbw/2; fcy=ny1+nbh/2
            try:
                active_canvas.itemconfig(single_id,width=int(nbw),height=int(nbh))
                active_canvas.coords(single_id,fcx,fcy)
                item_info_resize['width']=int(nbw); item_info_resize['height']=int(nbh)
            except Exception as e: print(f"Widget resize drag error: {e}")
        self.update_highlight() 

    def on_resize_handle_release(self, event):
        active_canvas = self._get_active_canvas()
        self._set_active_resize_handle(None); self._set_active_resize_original_pil_image(None)
        self._set_active_resize_start_item_bbox(None)
        active_canvas.unbind("<B1-Motion>"); active_canvas.unbind("<ButtonRelease-1>")
        active_canvas.bind("<ButtonPress-1>", lambda e,i=self.active_canvas_idx:self._dispatch_canvas_event(e,i,self.on_canvas_press))
        active_canvas.config(cursor="")
        if self._get_active_selected_item_ids(): self.update_highlight()

    def _update_canvas_image(self, item_id,new_pil_img,c_idx):
        cv_widget=self.canvases[c_idx]; cv_items=self.canvas_items[c_idx]
        if not item_id or not new_pil_img: return 
        info=next((it for it in cv_items if it['id']==item_id and it['type']=='image'),None)
        if not info: print(f"Err: No img info ID {item_id} on cv {c_idx}"); return
        try: new_tk = ImageTk.PhotoImage(new_pil_img); cv_widget.itemconfig(item_id,image=new_tk); info['obj']=new_tk 
        except Exception as e: print(f"Canvas img update err: {e}"); tkinter.messagebox.showerror("Img Upd Err",f"Img upd fail:\n{e}")

    def on_grid_size_change(self):
        try:
            sp = self.prop_grid_size.get()
            if sp >= 1:  
                if self.grid_spacing != sp: self.grid_spacing=sp; [self.draw_grid(i) for i in range(self.num_canvases)]
            else: self.prop_grid_size.set(self.grid_spacing) 
        except tk.TclError: pass
        except Exception as e: print(f"Grid size err: {e}"); self.prop_grid_size.set(self.grid_spacing) 

    def on_canvas_resize(self, event):
        r_idx = -1; 
        for i,c_w in enumerate(self.canvases): 
            if event.widget == c_w: r_idx=i; break
        if r_idx != -1: self.draw_grid(r_idx)

    def on_delete_key_press(self, event):
        focus_w = self.focus_get()
        if isinstance(focus_w,(ttk.Entry,tk.Text,ttk.Spinbox)): return 
        focus_cv_idx = -1
        for i,c_w in enumerate(self.canvases):
            if focus_w == c_w: focus_cv_idx=i; break
        if focus_cv_idx == -1 and hasattr(focus_w,'winfo_parent'):
            parent = focus_w.winfo_parent()
            for i,c_w in enumerate(self.canvases):
                if parent == str(c_w): focus_cv_idx=i; break
        if focus_cv_idx != -1:
            self.active_canvas_idx = focus_cv_idx 
            if self._get_active_selected_item_ids(): self.delete_selected_item(); return "break" 
        return 

    def delete_selected_item(self): 
        acv=self._get_active_canvas(); aci=self._get_active_canvas_items(); asi=self._get_active_selected_item_ids()
        if not asi: return
        for item_id in list(asi):
            info_del=None; idx_del=-1
            for i,it_info in enumerate(aci):
                if it_info['id']==item_id: info_del=it_info; idx_del=i; break
            if info_del:
                if info_del['type']=='widget' and info_del.get('obj'): info_del['obj'].destroy()
                acv.delete(item_id) 
                if idx_del!=-1: del aci[idx_del]
        self.deselect_all() 

    def draw_grid(self, cv_idx):
        cv_draw = self.canvases[cv_idx]; tag=f"gl_{cv_idx}"; cv_draw.delete(tag) 
        w,h=cv_draw.winfo_width(),cv_draw.winfo_height()
        if self.grid_spacing>0 and w>0 and h>0 : 
            for x in range(0,w,self.grid_spacing): cv_draw.create_line(x,0,x,h,fill="#e0e0e0",tags=tag)
            for y in range(0,h,self.grid_spacing): cv_draw.create_line(0,y,w,y,fill="#e0e0e0",tags=tag)
            cv_draw.tag_lower(tag)

    def _snap_to_grid(self, x, y):
        if self.grid_spacing <= 0: return x,y
        return round(x/self.grid_spacing)*self.grid_spacing, round(y/self.grid_spacing)*self.grid_spacing

    def _get_python_list_from_tcl_list(self, tcl_list):
        if not tcl_list: return []
        if isinstance(tcl_list,(list,tuple)): return [str(i) for i in tcl_list]
        if isinstance(tcl_list,str):
            try: return list(self.tk.splitlist(tcl_list))
            except tk.TclError: return [] 
        try: return list(self.tk.splitlist(str(tcl_list)))
        except (tk.TclError,TypeError): 
            if hasattr(tcl_list,'__iter__'):
                 try: return [str(v) for v in tcl_list]
                 except Exception: pass 
            return []

    def save_layout(self):
        acv=self._get_active_canvas(); aci=self._get_active_canvas_items()
        fp=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON Files","*.json")],title=f"レイアウト保存 (Canvas {self.active_canvas_idx+1})")
        if not fp: return
        layout_data={"general_settings":{"grid_spacing":self.grid_spacing},"items":[]} # Corrected key
        for info_loop in aci: 
            iid=info_loop['id']; itype=info_loop['type']; bbox=acv.bbox(iid)
            if not bbox: continue
            tlx,tly=bbox[0],bbox[1]; iw=info_loop.get('width',bbox[2]-bbox[0]); ih=info_loop.get('height',bbox[3]-bbox[1])
            idata={"id_on_canvas":iid,"type":itype,"x":tlx,"y":tly,"width":int(iw),"height":int(ih)}
            if itype=='widget':
                wobj=info_loop['obj']; idata['widget_class_name']=wobj.winfo_class(); idata['widget_module']='tk' if not idata['widget_class_name'].startswith('T') else 'ttk'
                txt_v=""; 
                if isinstance(wobj,(ttk.Entry,ttk.Combobox)):txt_v=wobj.get()
                elif hasattr(wobj,"cget"):
                    try:txt_v=wobj.cget("text")
                    except tk.TclError:pass
                idata['text']=str(txt_v)
                try:
                    f_act=tkfont.Font(font=wobj.cget("font")).actual()
                    idata['font']={'family':str(f_act['family']),'size':abs(f_act['size']),'weight':str(f_act['weight']),'slant':str(f_act['slant'])}
                except tk.TclError:pass 
                if hasattr(wobj,'cget') and 'anchor' in wobj.keys():
                    try:idata['anchor']=str(wobj.cget('anchor'))
                    except tk.TclError:pass
                clrs={}; 
                try: 
                    fg_opt='foreground' if isinstance(wobj,(ttk.Label,ttk.Entry,ttk.Combobox)) else 'fg'
                    clrs['fg']=str(wobj.cget(fg_opt))
                except tk.TclError:pass
                try:
                    if isinstance(wobj,(tk.Button,tk.Checkbutton,tk.Radiobutton)):clrs['bg']=str(wobj.cget('bg'))
                except tk.TclError:pass
                if clrs:idata['colors']=clrs
                if isinstance(wobj,ttk.Combobox):idata['values']=self._get_python_list_from_tcl_list(wobj.cget('values'))
            elif itype=='image':idata['path']=str(info_loop['path'])
            layout_data["items"].append(idata)
        try:
            with open(fp,'w',encoding='utf-8') as f:json.dump(layout_data,f,indent=4,ensure_ascii=False)
        except TypeError as e: print(f"Save Err (Type): {e}");tkinter.messagebox.showerror("Save Err",f"Save type err: {e}")
        except Exception as e: print(f"Save Err: {e}");tkinter.messagebox.showerror("Save Err",f"Save err: {e}")

    def open_layout(self):
        acv=self._get_active_canvas(); aci=self._get_active_canvas_items(); asi=self._get_active_selected_item_ids(); ahr=self._get_active_highlight_rects()
        fp=filedialog.askopenfilename(filetypes=[("JSON Files","*.json")],title=f"レイアウトを開く (Canvas {self.active_canvas_idx+1})")
        if not fp: return
        for info_del in list(aci): 
            if info_del['type']=='widget' and info_del.get('obj'):info_del['obj'].destroy()
            acv.delete(info_del['id'])
        aci.clear(); asi.clear(); self.selected_widget=None; self.selected_item_info=None 
        for rid in list(ahr.values()):acv.delete(rid)
        ahr.clear(); acv.delete(f"{self.ALL_RESIZE_HANDLES_TAG}_{self.active_canvas_idx}")
        self.update_property_editor() 
        try:
            with open(fp,'r',encoding='utf-8') as f:layout_data=json.load(f)
        except Exception as e:print(f"Load Err: {e}");tkinter.messagebox.showerror("Open Err",f"Load fail: {e}");return
        g_set=layout_data.get("general_settings",{}); lgs=g_set.get("grid_spacing",20) 
        self.grid_spacing=lgs; self.prop_grid_size.set(lgs); self.draw_grid(self.active_canvas_idx) 
        items_data=layout_data.get("items",[])
        for info in items_data:
            itype=info.get('type'); lx,ly=info.get('x'),info.get('y'); lw,lh=info.get('width'),info.get('height') 
            if itype=='widget':
                wc_name=info.get('widget_class_name',''); wt_simple=wc_name.replace('T','').lower() if wc_name else ''
                l_anchor=info.get('anchor','center') 
                self.add_widget(widget_type=wt_simple,text=info.get('text'),x=lx,y=ly,values=info.get('values'),font_info=info.get('font'),colors=info.get('colors'),width=lw,height=lh,anchor=l_anchor)
            elif itype=='image':
                try:
                    pil_img_orig=Image.open(info['path']); spw=int(lw if lw is not None else pil_img_orig.width); sph=int(lh if lh is not None else pil_img_orig.height)
                    pil_resized=pil_img_orig.resize((spw,sph),Image.Resampling.LANCZOS); tk_photo=ImageTk.PhotoImage(pil_resized)
                    img_id=acv.create_image(lx,ly,image=tk_photo,anchor=tk.NW)
                    new_info={'id':img_id,'type':'image','obj':tk_photo,'path':info['path'],'width':pil_resized.width,'height':pil_resized.height,'original_pil_image':pil_img_orig}
                    aci.append(new_info)
                    acv.tag_bind(img_id,"<ButtonPress-1>",lambda e,item=img_id,c=self.active_canvas_idx:self._dispatch_item_event(e,c,item,self.on_canvas_item_press))
                except FileNotFoundError:tkinter.messagebox.showwarning("Img Load Err",f"Img not found:\n{info.get('path')}")
                except Exception as e:print(f"Err img {info.get('path')}: {e}");tkinter.messagebox.showwarning("Img Load Err",f"Img {info.get('path')} recreate fail:\n{e}")

    def generate_code(self):
        acv=self._get_active_canvas(); aci=self._get_active_canvas_items()
        code_win=tk.Toplevel(self); code_win.title(f"Generated Code (Canvas {self.active_canvas_idx+1})"); code_win.geometry("700x750")
        txt_area=tk.Text(code_win,wrap="word",font=("Courier New",10)); scroll=ttk.Scrollbar(code_win,command=txt_area.yview)
        txt_area.config(yscrollcommand=scroll.set); scroll.pack(side="right",fill="y"); txt_area.pack(expand=True,fill="both")
        lines=["import tkinter as tk","from tkinter import ttk","import tkinter.font as tkfont","from PIL import Image, ImageTk\n",
               "class App(tk.Tk):","    def __init__(self):","        super().__init__()",
               f"        self.title('Generated Layout - Canvas {self.active_canvas_idx+1}')",
               f"        self.geometry('{acv.winfo_width()}x{acv.winfo_height()}')\n",
               "        self._image_references_generated_app = [] \n"]
        w_count=0 
        for info_loop in aci: 
            w_count+=1; var_name=f"self.item_{w_count}" 
            iid=info_loop['id']; itype=info_loop['type']; bbox=acv.bbox(iid)
            if not bbox: continue
            px,py=int(bbox[0]),int(bbox[1]); iw=info_loop.get('width',bbox[2]-bbox[0]); ih=info_loop.get('height',bbox[3]-bbox[1])
            if itype=='widget':
                wobj=info_loop['obj']; cname=info_loop.get('widget_class_name',wobj.winfo_class())
                mname='tk' if not cname.startswith('T') else 'ttk'; act_cname=cname.replace('T','') if mname=='ttk' else cname
                opts=[]
                txt_v=wobj.get() if isinstance(wobj,(ttk.Entry,ttk.Combobox)) else wobj.cget("text")
                if not isinstance(wobj,ttk.Entry):opts.append(f"text='{str(txt_v).replace('\'','\\\\\'')}'")
                try:
                    f_act=tkfont.Font(font=wobj.cget("font")).actual()
                    ff=f_act['family'].replace("'","\\'");fs=abs(f_act['size']);fst=[]
                    if f_act['weight']=='bold':fst.append('bold')
                    if f_act['slant']=='italic':fst.append('italic')
                    opts.append(f"font=('{ff}', {fs}, '{' '.join(fst)}')")
                except tk.TclError:pass
                if hasattr(wobj,'cget') and 'anchor' in wobj.keys():
                    try:
                        anch=str(wobj.cget('anchor'))
                        if anch and anch!="center":opts.append(f"anchor='{anch}'") 
                    except tk.TclError:pass
                try:
                    fg_opt='foreground' if isinstance(wobj,(ttk.Label,ttk.Entry,ttk.Combobox)) else 'fg'
                    opts.append(f"{fg_opt}='{wobj.cget(fg_opt)}'")
                except tk.TclError:pass
                try: 
                    if isinstance(wobj,(tk.Button,tk.Checkbutton,tk.Radiobutton)):opts.append(f"background='{wobj.cget('bg')}'")
                except tk.TclError:pass
                if isinstance(wobj,ttk.Combobox):opts.append(f"values={self._get_python_list_from_tcl_list(wobj.cget('values'))}")
                opt_str=", ".join(opts)
                lines.append(f"        {var_name} = {mname}.{act_cname}(self{', ' if opt_str else ''}{opt_str})")
                if isinstance(wobj,ttk.Entry) and txt_v:lines.append(f"        {var_name}.insert(0, '{str(txt_v).replace('\'','\\\\\'')}')")
                if isinstance(wobj,ttk.Combobox) and txt_v: 
                    py_vals=self._get_python_list_from_tcl_list(wobj.cget('values'))
                    if txt_v in py_vals:lines.append(f"        {var_name}.set('{str(txt_v).replace('\'','\\\\\'')}')")
                    elif py_vals:lines.append(f"        {var_name}.current(0)")
                lines.append(f"        {var_name}.place(x={px}, y={py})\n")
            elif itype=='image':
                imgPath=info_loop['path'].replace('\\','\\\\'); imgW,imgH=int(iw),int(ih) 
                lines.extend([f"        # Image: {imgPath}","        try:",
                    f"            pil_img_{w_count}=Image.open(r'{imgPath}')",
                    f"            pil_img_{w_count}=pil_img_{w_count}.resize(({imgW},{imgH}),Image.Resampling.LANCZOS)",
                    f"            {var_name}_img_tk=ImageTk.PhotoImage(pil_img_{w_count})",
                    f"            self._image_references_generated_app.append({var_name}_img_tk) ",
                    f"            {var_name}=tk.Label(self,image={var_name}_img_tk,borderwidth=0)",
                    f"            {var_name}.place(x={px},y={py})", 
                    f"        except Exception as e: print(f'Err load img {{e}} for {var_name}')\n"])
        lines.extend(["\nif __name__ == '__main__':","    app = App()","    app.mainloop()"])
        txt_area.insert("1.0","\n".join(lines)); txt_area.config(state="disabled")

if __name__ == "__main__":
    app = LayoutDesigner()
    app.mainloop()
