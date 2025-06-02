import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import json
import tkinter.font as tkfont
from tkinter import colorchooser
from PIL import Image, ImageTk
import tkinter.messagebox 

# --- Mixinクラスのインポート ---
from event_handlers_mixin import EventHandlersMixin
# from file_operations_mixin import FileOperationsMixin # 将来的に追加する場合
# from ui_setup_mixin import UISetupMixin # 将来的に追加する場合

class LayoutDesigner(tk.Tk, EventHandlersMixin):
    def __init__(self):
        super().__init__()
        self.title("GUI Layout Designer")
        self.geometry("1000x700")

        # --- State Variables ---
        self._dragged_item_id = None 
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_selected_items_start_bboxes = {} 

        self.highlight_rects = {} 
        self.grid_spacing = 20
        self.prop_grid_size = tk.IntVar(value=self.grid_spacing)
        self.canvas_items = []
        
        self.selected_item_ids = set() 
        self.selected_widget = None 
        self.selected_item_info = None 

        self.RESIZE_HANDLE_SIZE = 10
        self.RESIZE_HANDLE_TAG_PREFIX = "rh_"
        self.ALL_RESIZE_HANDLES_TAG = "all_resize_handles"
        self.HANDLE_CURSORS = {
            'nw': 'size_nw_se', 'n': 'sb_v_double_arrow', 'ne': 'size_ne_sw',
            'w':  'sb_h_double_arrow', 'e': 'sb_h_double_arrow',
            'sw': 'size_ne_sw', 's': 'sb_v_double_arrow', 'se': 'size_nw_se',
        }
        self.active_resize_handle = None
        self.resize_start_mouse_x = 0
        self.resize_start_mouse_y = 0
        self.resize_start_item_bbox = None
        self.resize_original_pil_image = None 
        self._updating_font_properties_internally = False
        self._updating_properties_internally = False

        # --- Style Definitions for Anchor Buttons ---
        self.selected_anchor_style_name = "SelectedAnchor.TButton"
        self.default_anchor_style_name = "TButton" 
        style = ttk.Style()
        style.configure(self.selected_anchor_style_name, background="lightblue")

        # --- UI Setup ---
        self.create_menu()
        self.toolbox_frame = ttk.Frame(self, width=200, relief="sunken", borderwidth=2)
        self.toolbox_frame.pack(side="left", fill="y", padx=5, pady=5); self.toolbox_frame.pack_propagate(False)
        
        self.canvas_frame = tk.Canvas(self, bg="white", relief="sunken", borderwidth=2)
        self.canvas_frame.pack(side="left", expand=True, fill="both", padx=5, pady=5)
        
        self.property_frame = ttk.Frame(self, width=250, relief="sunken", borderwidth=2)
        self.property_frame.pack(side="right", fill="y", padx=10, pady=5); self.property_frame.pack_propagate(False)
        
        self.setup_toolbox()
        self.setup_properties()

        self.canvas_frame.bind("<ButtonPress-1>", self.on_canvas_press) 
        self.canvas_frame.bind("<Configure>", self.on_canvas_resize)
        self.after(100, self.draw_grid)

        self.bind("<Delete>", self.on_delete_key_press)

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
        ttk.Label(self.toolbox_frame, text="ツールボックス", font=("Helvetica", 14)).pack(pady=10)
        widget_types = ["Button", "Label", "Checkbutton", "Radiobutton", "Entry", "Combobox"]
        for name in widget_types:
            ttk.Button(self.toolbox_frame, text=name, command=lambda n=name: self.add_widget(n.lower())).pack(fill="x", padx=10, pady=5)
        
        ttk.Button(self.toolbox_frame, text="Image", command=self.add_image_to_canvas).pack(fill="x", padx=10, pady=5)

        grid_frame = ttk.Frame(self.toolbox_frame)
        grid_frame.pack(fill="x", padx=10, pady=5)
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
            
            raw_x = self.canvas_frame.winfo_width() / 2
            raw_y = self.canvas_frame.winfo_height() / 2
            snapped_x, snapped_y = self._snap_to_grid(raw_x, raw_y)
            
            image_item_id = self.canvas_frame.create_image(snapped_x, snapped_y, image=tk_photo_image, anchor=tk.NW)
            
            item_info = {
                'id': image_item_id, 
                'type': 'image', 
                'obj': tk_photo_image, 
                'path': filepath, 
                'width': current_pil_image.width, 
                'height': current_pil_image.height, 
                'original_pil_image': pil_image 
            }
            self.canvas_items.append(item_info)
            self.canvas_frame.tag_bind(image_item_id, "<ButtonPress-1>", 
                                       lambda e, i_id=image_item_id: self.on_canvas_item_press(e, i_id))
        except Exception as e: 
            print(f"画像処理エラー: {e}")
            tkinter.messagebox.showerror("画像エラー", f"画像の読み込みまたは処理中にエラーが発生しました:\n{e}")

    def add_widget(self, widget_type, text=None, x=None, y=None, values=None, font_info=None, colors=None, width=None, height=None, anchor=None):
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
        if anchor and widget_type in ["button", "label", "checkbutton", "radiobutton"]: # Added checkbutton, radiobutton
             widget_args['anchor'] = anchor
        
        w = None
        if widget_type == "button":
            widget_args['text'] = text or "Button"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Button(self.canvas_frame, **widget_args)
        elif widget_type == "label":
            widget_args['text'] = text or "Label"
            if fg_color: widget_args['foreground'] = fg_color 
            w = ttk.Label(self.canvas_frame, **widget_args)
        elif widget_type == "checkbutton":
            widget_args['text'] = text or "Checkbutton"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Checkbutton(self.canvas_frame, **widget_args)
        elif widget_type == "radiobutton":
            widget_args['text'] = text or "Radiobutton"
            if fg_color: widget_args['fg'] = fg_color
            if bg_color: widget_args['bg'] = bg_color
            w = tk.Radiobutton(self.canvas_frame, **widget_args)
        elif widget_type == "entry":
            w = ttk.Entry(self.canvas_frame, **widget_args)
            if text: w.insert(0, text)
        elif widget_type == "combobox":
            w = ttk.Combobox(self.canvas_frame, **widget_args)
            if values: w['values'] = values
            else: w['values'] = ["Item 1", "Item 2"]
            if text: w.set(text)
            else: w.current(0)
        else:
            print(f"Unknown widget type: {widget_type}")
            return
        
        canvas_x = x if x is not None else self.canvas_frame.winfo_width() / 2
        canvas_y = y if y is not None else self.canvas_frame.winfo_height() / 2
        
        canvas_id = self.canvas_frame.create_window(canvas_x, canvas_y, window=w)
        
        if width is not None and height is not None:
            try:
                self.canvas_frame.itemconfig(canvas_id, width=int(width), height=int(height))
            except (ValueError, tk.TclError) as e:
                print(f"Error setting loaded width/height for widget: {e}")
        
        self.update_idletasks() 

        actual_widget_width = self.canvas_frame.bbox(canvas_id)[2] - self.canvas_frame.bbox(canvas_id)[0] if self.canvas_frame.bbox(canvas_id) else w.winfo_reqwidth()
        actual_widget_height = self.canvas_frame.bbox(canvas_id)[3] - self.canvas_frame.bbox(canvas_id)[1] if self.canvas_frame.bbox(canvas_id) else w.winfo_reqheight()
        
        desired_top_left_x = x if x is not None else canvas_x - actual_widget_width / 2
        desired_top_left_y = y if y is not None else canvas_y - actual_widget_height / 2
        
        snapped_tl_x, snapped_tl_y = self._snap_to_grid(desired_top_left_x, desired_top_left_y)
        
        final_center_x = snapped_tl_x + actual_widget_width / 2
        final_center_y = snapped_tl_y + actual_widget_height / 2
        self.canvas_frame.coords(canvas_id, final_center_x, final_center_y)

        item_info = {
            'id': canvas_id, 
            'type': 'widget', 
            'obj': w, 
            'widget_type': widget_type,
            'width': actual_widget_width, 
            'height': actual_widget_height
            }
        self.canvas_items.append(item_info)
        
        w.bind("<ButtonPress-1>", lambda e, i_id=canvas_id: [self.canvas_frame.focus_set(), self.on_canvas_item_press(e, i_id)])
        # --- 追加: widgetにもドラッグ・リリースイベントをバインド ---
        w.bind("<B1-Motion>", lambda e, i_id=canvas_id: self.on_multi_item_drag(e))
        w.bind("<ButtonRelease-1>", lambda e, i_id=canvas_id: self.on_multi_item_release(e))


    def update_property_editor_for_selection(self):
        self.selected_widget = None 
        self.selected_item_info = None 

        if len(self.selected_item_ids) == 1:
            single_id = list(self.selected_item_ids)[0]
            item_info = next((item for item in self.canvas_items if item['id'] == single_id), None)
            if item_info:
                self.selected_item_info = item_info 
                if item_info['type'] == 'widget':
                    self.selected_widget = item_info['obj']
        
        self.update_property_editor()


    def on_multi_item_drag(self, event):
        if not self._dragged_item_id or not self.selected_item_ids or self.active_resize_handle:
            print(f"[DEBUG] on_multi_item_drag: drag条件不成立 _dragged_item_id={self._dragged_item_id}, selected_item_ids={self.selected_item_ids}, active_resize_handle={self.active_resize_handle}")
            return

        # --- ここでevent.x, event.yをCanvas座標に変換 ---
        if event.widget is not self.canvas_frame:
            abs_x = event.widget.winfo_rootx() + event.x
            abs_y = event.widget.winfo_rooty() + event.y
            current_mouse_x_canvas = abs_x - self.canvas_frame.winfo_rootx()
            current_mouse_y_canvas = abs_y - self.canvas_frame.winfo_rooty()
        else:
            current_mouse_x_canvas = event.x
            current_mouse_y_canvas = event.y
        print(f"[DEBUG] on_multi_item_drag: event.x={event.x}, event.y={event.y}, current_mouse_x_canvas={current_mouse_x_canvas}, current_mouse_y_canvas={current_mouse_y_canvas}")

        drag_delta_x = current_mouse_x_canvas - self._drag_start_x
        drag_delta_y = current_mouse_y_canvas - self._drag_start_y
        print(f"[DEBUG] on_multi_item_drag: drag_delta_x={drag_delta_x}, drag_delta_y={drag_delta_y}")

        effective_delta_x = drag_delta_x
        effective_delta_y = drag_delta_y
        
        if self._dragged_item_id and self._dragged_item_id in self._drag_selected_items_start_bboxes:
            primary_start_bbox = self._drag_selected_items_start_bboxes[self._dragged_item_id]
            primary_new_top_left_x_raw = primary_start_bbox[0] + drag_delta_x
            primary_new_top_left_y_raw = primary_start_bbox[1] + drag_delta_y
            
            snapped_primary_tl_x, snapped_primary_tl_y = self._snap_to_grid(primary_new_top_left_x_raw, primary_new_top_left_y_raw)
            
            effective_delta_x = snapped_primary_tl_x - primary_start_bbox[0]
            effective_delta_y = snapped_primary_tl_y - primary_start_bbox[1]
            print(f"[DEBUG] on_multi_item_drag: snapped_primary_tl_x={snapped_primary_tl_x}, snapped_primary_tl_y={snapped_primary_tl_y}")
            print(f"[DEBUG] on_multi_item_drag: effective_delta_x={effective_delta_x}, effective_delta_y={effective_delta_y}")

        for item_id in self.selected_item_ids:
            if item_id in self._drag_selected_items_start_bboxes:
                start_bbox = self._drag_selected_items_start_bboxes[item_id]
                
                new_top_left_x = start_bbox[0] + effective_delta_x
                new_top_left_y = start_bbox[1] + effective_delta_y
                print(f"[DEBUG] on_multi_item_drag: item_id={item_id}, new_top_left_x={new_top_left_x}, new_top_left_y={new_top_left_y}")

                item_info = next((item for item in self.canvas_items if item['id'] == item_id), None)
                if item_info:
                    if item_info['type'] == 'widget':
                        w = item_info['obj']
                        width = item_info.get('width', start_bbox[2] - start_bbox[0])
                        height = item_info.get('height', start_bbox[3] - start_bbox[1])
                        center_x = new_top_left_x + width / 2
                        center_y = new_top_left_y + height / 2
                        self.canvas_frame.coords(item_id, center_x, center_y)
                    elif item_info['type'] == 'image':
                        self.canvas_frame.coords(item_id, new_top_left_x, new_top_left_y)
        
        self.update_highlight()

    def on_multi_item_release(self, event):
        print(f"[DEBUG] on_multi_item_release: selected_item_ids={self.selected_item_ids}, _dragged_item_id={self._dragged_item_id}")
        self._dragged_item_id = None
        self._drag_selected_items_start_bboxes.clear()
        
        self.canvas_frame.unbind("<B1-Motion>")
        self.canvas_frame.unbind("<ButtonRelease-1>")
        
        self.canvas_frame.bind("<ButtonPress-1>", self.on_canvas_press)


    def update_property_editor(self):
        num_selected = len(self.selected_item_ids)
        single_selected_item_info = None
        widget_obj = None

        if num_selected == 1:
            single_id = list(self.selected_item_ids)[0]
            single_selected_item_info = next((item for item in self.canvas_items if item['id'] == single_id), None)
            if single_selected_item_info and single_selected_item_info['type'] == 'widget':
                widget_obj = single_selected_item_info['obj']
        
        is_single_widget_selected = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'widget')
        is_single_image_selected = (num_selected == 1 and single_selected_item_info and single_selected_item_info['type'] == 'image')
        is_multi_selected = num_selected > 1

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
                        for c_idx, button_widget in row_buttons_dict.items():
                            button_text_lower = button_widget.cget('text').lower()
                            button_widget.config(style=self.selected_anchor_style_name if button_text_lower == current_anchor else self.default_anchor_style_name)
                except tk.TclError: 
                    self.prop_anchor.set("center")
                    if 1 in self.anchor_buttons and 1 in self.anchor_buttons[1]:
                         self.anchor_buttons[1][1].config(style=self.selected_anchor_style_name) 
            else:
                self.prop_anchor.set("")
                for r_buttons in self.anchor_buttons.values(): 
                    for btn in r_buttons.values(): btn.config(style=self.default_anchor_style_name)


            try: 
                fg_opt = 'fg' if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)) else 'foreground'
                fg_val = widget_obj.cget(fg_opt)
                self.prop_fg_color.set(fg_val); self.fg_color_preview.config(bg=fg_val)
            except tk.TclError: self.prop_fg_color.set("#000000"); self.fg_color_preview.config(bg="#000000")

            if isinstance(widget_obj, (tk.Button,tk.Checkbutton,tk.Radiobutton)):
                try: bg_val = widget_obj.cget('bg'); self.prop_bg_color.set(bg_val); self.bg_color_preview.config(bg=bg_val)
                except tk.TclError: self.prop_bg_color.set("#F0F0F0"); self.bg_color_preview.config(bg="#F0F0F0")
            else: self.prop_bg_color.set(""); self.bg_color_preview.config(bg=self.cget('bg')) 
            self._updating_properties_internally = False 

        elif is_single_image_selected:
            self.prop_text.set("[Image Selected]"); self.prop_values.set(""); self.prop_anchor.set("")
        elif is_multi_selected:
            self.prop_text.set(f"[{num_selected} items selected]"); self.prop_values.set(""); self.prop_anchor.set("")
        else: 
            self.prop_text.set(""); self.prop_values.set(""); self.prop_anchor.set("")


    def update_highlight(self):
        for rect_id in self.highlight_rects.values():
            self.canvas_frame.delete(rect_id)
        self.highlight_rects.clear()
        self.canvas_frame.delete(self.ALL_RESIZE_HANDLES_TAG)

        if not self.selected_item_ids:
            return

        for item_id in self.selected_item_ids:
            try:
                coords = self.canvas_frame.bbox(item_id)
                if not coords: continue
                x1, y1, x2, y2 = coords
                rect_id = self.canvas_frame.create_rectangle(
                    x1 - 1, y1 - 1, x2 + 1, y2 + 1, 
                    outline="gray", dash=(3,3), tags="multi_highlight_rect" 
                )
                self.highlight_rects[item_id] = rect_id
            except tk.TclError:
                pass 

        if len(self.selected_item_ids) == 1:
            single_id = list(self.selected_item_ids)[0]
            if single_id in self.highlight_rects: 
                self.canvas_frame.delete(self.highlight_rects[single_id])
                del self.highlight_rects[single_id]

            try:
                coords = self.canvas_frame.bbox(single_id)
                if not coords: return
                x1, y1, x2, y2 = coords
                primary_highlight_id = self.canvas_frame.create_rectangle(
                    x1 - 2, y1 - 2, x2 + 2, y2 + 2, 
                    outline="blue", width=1, tags="primary_highlight_rect"
                )
                self.highlight_rects[single_id] = primary_highlight_id 

                item_info = next((item for item in self.canvas_items if item['id'] == single_id), None)
                if item_info and (item_info['type'] == 'image' or item_info['type'] == 'widget'):
                    s = self.RESIZE_HANDLE_SIZE / 2
                    handle_defs = {
                        'nw': (x1,y1), 'n': ((x1+x2)/2,y1), 'ne': (x2,y1),
                        'w': (x1,(y1+y2)/2), 'e': (x2,(y1+y2)/2),
                        'sw': (x1,y2), 's': ((x1+x2)/2,y2), 'se': (x2,y2)
                    }
                    for h_type, (hx,hy) in handle_defs.items():
                        tag = f"{self.RESIZE_HANDLE_TAG_PREFIX}{h_type}"
                        handle_id = self.canvas_frame.create_rectangle(
                            hx-s, hy-s, hx+s, hy+s,
                            fill="white", outline="black", tags=(self.ALL_RESIZE_HANDLES_TAG, tag)
                        )
                        self.canvas_frame.tag_bind(handle_id, "<Enter>", lambda e, ht=h_type: self.on_handle_enter(e, ht))
                        self.canvas_frame.tag_bind(handle_id, "<Leave>", self.on_handle_leave)
                        self.canvas_frame.tag_bind(handle_id, "<ButtonPress-1>", lambda e, ht=h_type: self.on_resize_handle_press(e, ht))
                    
                    self.canvas_frame.tag_raise(self.ALL_RESIZE_HANDLES_TAG)
                    self.canvas_frame.tag_raise(primary_highlight_id)
            except tk.TclError: 
                self.deselect_all() 


    def on_property_change(self, var_name_str, index, mode): 
        if self._updating_properties_internally: return 
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self.selected_item_ids) != 1:
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
        self.after(10, self.update_highlight)

    def on_font_property_change(self, *args):
        if self._updating_properties_internally or self._updating_font_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self.selected_item_ids) != 1:
            return
        
        family = self.prop_font_family.get(); size = self.prop_font_size.get()
        if not family or size <= 0: return 
        style_parts = []
        if self.prop_font_bold.get(): style_parts.append("bold")
        if self.prop_font_italic.get(): style_parts.append("italic")
        try:
            self.selected_widget.config(font=(family, size, " ".join(style_parts)))
            self.after(50, self.update_highlight) 
        except tk.TclError as e: print(f"Font Error: {e}")

    def on_anchor_button_click(self, new_anchor_value):
        if self._updating_properties_internally: return
        if not self.selected_widget or not self.selected_widget.winfo_exists() or len(self.selected_item_ids) != 1:
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
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self.selected_item_ids) != 1: return
        color = self.prop_fg_color.get()
        if len(color) >= 4 and color.startswith('#'): 
            try:
                opt_name = 'foreground' if isinstance(self.selected_widget, (ttk.Label, ttk.Entry, ttk.Combobox)) else 'fg'
                self.selected_widget.config(**{opt_name: color}); self.fg_color_preview.config(bg=color)
            except tk.TclError: pass 

    def on_bg_color_change(self, *args):
        if self._updating_properties_internally or not self.selected_widget or not self.selected_widget.winfo_exists() or len(self.selected_item_ids) != 1: return
        if isinstance(self.selected_widget, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
            color = self.prop_bg_color.get()
            if len(color) >= 4 and color.startswith('#'):
                try: self.selected_widget.config(background=color); self.bg_color_preview.config(bg=color)
                except tk.TclError: pass
        else: pass

    def open_fg_color_chooser(self):
        if self.selected_widget and self.fg_color_button['state'] != 'disabled' and len(self.selected_item_ids) == 1:
            init_color = self.prop_fg_color.get() if self.prop_fg_color.get() else "#000000"
            code = colorchooser.askcolor(title="文字色を選択", initialcolor=init_color)
            if code and code[1]: self.prop_fg_color.set(code[1])

    def open_bg_color_chooser(self):
        if self.selected_widget and self.bg_color_button['state'] != 'disabled' and len(self.selected_item_ids) == 1:
            init_color = self.prop_bg_color.get() if self.prop_bg_color.get() else "#F0F0F0"
            code = colorchooser.askcolor(title="背景色を選択", initialcolor=init_color)
            if code and code[1]: self.prop_bg_color.set(code[1])

    def on_handle_enter(self, event, handle_type):
        if len(self.selected_item_ids) == 1: 
            cursor_name = self.HANDLE_CURSORS.get(handle_type)
            if cursor_name: self.canvas_frame.config(cursor=cursor_name)

    def on_handle_leave(self, event): 
        if not self.active_resize_handle: 
            self.canvas_frame.config(cursor="")

    def on_resize_handle_press(self, event, handle_type):
        if len(self.selected_item_ids) != 1: return 
        
        single_id = list(self.selected_item_ids)[0]
        self.selected_item_info = next((item for item in self.canvas_items if item['id'] == single_id), None)
        if not self.selected_item_info: return

        self.active_resize_handle = handle_type
        # self._dragged_item_id = None # Not needed for resize, multi-drag uses _drag_reference_point_canvas

        self.resize_start_mouse_x = event.x_root - self.canvas_frame.winfo_rootx()
        self.resize_start_mouse_y = event.y_root - self.canvas_frame.winfo_rooty()
        self.resize_start_item_bbox = self.canvas_frame.bbox(single_id)
        
        if self.selected_item_info['type'] == 'image':
            if 'original_pil_image' in self.selected_item_info:
                 self.resize_original_pil_image = self.selected_item_info['original_pil_image'].copy()
            else: 
                try:
                    self.resize_original_pil_image = Image.open(self.selected_item_info['path'])
                except Exception as e:
                    print(f"リサイズ用元画像読み込みエラー: {e}")
                    tkinter.messagebox.showerror("リサイズエラー", f"リサイズ用の元画像を読み込めませんでした:\n{e}")
                    self.active_resize_handle = None; return
        elif self.selected_item_info['type'] == 'widget':
            self.resize_original_pil_image = None 
        
        self.canvas_frame.unbind("<B1-Motion>")
        self.canvas_frame.unbind("<ButtonRelease-1>")
        self.canvas_frame.bind("<B1-Motion>", self.on_resize_handle_drag)
        self.canvas_frame.bind("<ButtonRelease-1>", self.on_resize_handle_release)

    def on_resize_handle_drag(self, event): 
        if not all([self.active_resize_handle, self.selected_item_info, self.resize_start_item_bbox]):
            if not (self.selected_item_info and self.selected_item_info['type'] == 'image' and self.resize_original_pil_image) and \
               not (self.selected_item_info and self.selected_item_info['type'] == 'widget'):
                 return
        
        single_id = self.selected_item_info['id']

        mouse_x_canvas = event.x_root - self.canvas_frame.winfo_rootx()
        mouse_y_canvas = event.y_root - self.canvas_frame.winfo_rooty()

        current_delta_x = mouse_x_canvas - self.resize_start_mouse_x
        current_delta_y = mouse_y_canvas - self.resize_start_mouse_y
        
        orig_x1, orig_y1, orig_x2, orig_y2 = self.resize_start_item_bbox
        
        modifier_state = event.state; SHIFT_MASK = 0x0001
        snap_active = ((modifier_state & SHIFT_MASK) != 0)

        final_delta_x, final_delta_y = current_delta_x, current_delta_y
        if snap_active and self.grid_spacing > 0:
            handle = self.active_resize_handle
            if 'n' in handle: target_y = orig_y1 + current_delta_y; snapped_y = self._snap_to_grid(0, target_y)[1]; final_delta_y = snapped_y - orig_y1
            if 's' in handle: target_y = orig_y2 + current_delta_y; snapped_y = self._snap_to_grid(0, target_y)[1]; final_delta_y = snapped_y - orig_y2
            if 'w' in handle: target_x = orig_x1 + current_delta_x; snapped_x = self._snap_to_grid(target_x, 0)[0]; final_delta_x = snapped_x - orig_x1
            if 'e' in handle: target_x = orig_x2 + current_delta_x; snapped_x = self._snap_to_grid(target_x, 0)[0]; final_delta_x = snapped_x - orig_x2
        
        delta_x, delta_y = final_delta_x, final_delta_y
        handle = self.active_resize_handle 
        
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

        item_info = self.selected_item_info 

        if item_info['type'] == 'image':
            orig_pil_w = self.resize_original_pil_image.width 
            orig_pil_h = self.resize_original_pil_image.height
            aspect_ratio = orig_pil_w / orig_pil_h if orig_pil_h > 0 else 1.0
            final_pil_w, final_pil_h = new_bbox_w, new_bbox_h
            if len(handle) == 2: 
                if orig_pil_w == 0 or orig_pil_h == 0: pass 
                elif new_bbox_w / orig_pil_w > new_bbox_h / orig_pil_h:
                    final_pil_w = new_bbox_w; final_pil_h = final_pil_w / aspect_ratio
                else:
                    final_pil_h = new_bbox_h; final_pil_w = final_pil_h * aspect_ratio
            final_pil_w = max(1, int(round(final_pil_w))); final_pil_h = max(1, int(round(final_pil_h)))
            new_x1_calc, new_y1_calc = new_x1, new_y1 
            if handle == 'nw': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y2 - final_pil_h
            elif handle == 'ne': new_x1_calc = new_x1; new_y1_calc = new_y2 - final_pil_h
            elif handle == 'sw': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y1
            elif handle == 'se': new_x1_calc = new_x1; new_y1_calc = new_y1
            elif handle == 'n': new_y1_calc = new_y2 - final_pil_h; new_x1_calc = new_x1 + (new_bbox_w - final_pil_w) / 2
            elif handle == 's': new_y1_calc = new_y1; new_x1_calc = new_x1 + (new_bbox_w - final_pil_w) / 2
            elif handle == 'w': new_x1_calc = new_x2 - final_pil_w; new_y1_calc = new_y1 + (new_bbox_h - final_pil_h) / 2
            elif handle == 'e': new_x1_calc = new_x1; new_y1_calc = new_y1 + (new_bbox_h - final_pil_h) / 2
            try:
                resized_pil = self.resize_original_pil_image.resize((final_pil_w, final_pil_h), Image.Resampling.LANCZOS)
                self._update_canvas_image(single_id, resized_pil) 
                self.canvas_frame.coords(single_id, int(round(new_x1_calc)), int(round(new_y1_calc)))
                item_info['width'] = final_pil_w; item_info['height'] = final_pil_h
            except Exception as e: print(f"Image resize drag error: {e}")

        elif item_info['type'] == 'widget':
            final_center_x = new_x1 + new_bbox_w / 2
            final_center_y = new_y1 + new_bbox_h / 2
            try:
                self.canvas_frame.itemconfig(single_id, width=int(new_bbox_w), height=int(new_bbox_h))
                self.canvas_frame.coords(single_id, final_center_x, final_center_y)
                item_info['width'] = int(new_bbox_w)
                item_info['height'] = int(new_bbox_h)
            except Exception as e: print(f"Widget resize drag error: {e}")
        
        self.update_highlight() 

    def on_resize_handle_release(self, event):
        self.active_resize_handle = None
        self.resize_original_pil_image = None 
        self.resize_start_item_bbox = None
        # self.selected_item_info = None # Keep selected_item_info if it's still the primary selection
        
        self.canvas_frame.unbind("<B1-Motion>")
        self.canvas_frame.unbind("<ButtonRelease-1>")
        
        # Restore canvas-wide press binding, which will then set up appropriate motion/release for next op
        self.canvas_frame.bind("<ButtonPress-1>", self.on_canvas_press)

        self.canvas_frame.config(cursor="")
        if self.selected_item_ids: 
            self.update_highlight()

    def _update_canvas_image(self, item_id_to_update, new_pil_image):
        if not item_id_to_update or not new_pil_image: return 
        item_info = next((item for item in self.canvas_items if item['id'] == item_id_to_update and item['type'] == 'image'), None)
        if not item_info: 
            print(f"Error: Could not find image item_info for ID {item_id_to_update}")
            return
        try:
            new_tk_photo = ImageTk.PhotoImage(new_pil_image)
            self.canvas_frame.itemconfig(item_id_to_update, image=new_tk_photo)
            item_info['obj'] = new_tk_photo 
        except Exception as e:
            print(f"キャンバス画像の更新エラー (_update_canvas_image): {e}")
            tkinter.messagebox.showerror("画像更新エラー", f"画像の更新中にエラーが発生しました:\n{e}")
        except Exception as e:
            print(f"キャンバス画像の更新エラー (_update_canvas_image): {e}")
            tkinter.messagebox.showerror("画像更新エラー", f"画像の更新中にエラーが発生しました:\n{e}")

    def on_grid_size_change(self):
        try:
            new_spacing = self.prop_grid_size.get()
            if new_spacing >= 1:  
                if self.grid_spacing != new_spacing:
                    self.grid_spacing = new_spacing
                    self.draw_grid()
            else:
                self.prop_grid_size.set(self.grid_spacing)
        except tk.TclError:
            pass
        except Exception as e:
            print(f"グリッドサイズ変更エラー: {e}")
            if hasattr(self, 'grid_spacing'):
                self.prop_grid_size.set(self.grid_spacing)
    def on_canvas_resize(self, event): self.draw_grid()

    def on_delete_key_press(self, event):
        widget_with_focus = self.focus_get()
        if isinstance(widget_with_focus, (ttk.Entry, tk.Text, ttk.Spinbox)): return 
        if self.selected_item_ids: 
            self.delete_selected_item()
            return "break" 
        return 

    def delete_selected_item(self): # Now deletes all in self.selected_item_ids
        if not self.selected_item_ids: return

        ids_to_delete = list(self.selected_item_ids) 
        for item_id in ids_to_delete:
            item_to_delete_info = None
            item_index = -1
            for i, item_info_iter in enumerate(self.canvas_items):
                if item_info_iter['id'] == item_id:
                    item_to_delete_info = item_info_iter
                    item_index = i
                    break
            
            if item_to_delete_info:
                self.canvas_frame.delete(item_id)
                if item_index != -1:
                    del self.canvas_items[item_index]
        
        self.deselect_all() 

    def draw_grid(self):
        self.canvas_frame.delete("grid_line")
        w, h = self.canvas_frame.winfo_width(), self.canvas_frame.winfo_height()
        if self.grid_spacing > 0: 
            for x_coord in range(0, w, self.grid_spacing): self.canvas_frame.create_line(x_coord,0,x_coord,h,fill="#e0e0e0",tags="grid_line")
            for y_coord in range(0, h, self.grid_spacing): self.canvas_frame.create_line(0,y_coord,w,y_coord,fill="#e0e0e0",tags="grid_line")
            self.canvas_frame.tag_lower("grid_line")

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
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")], title="レイアウトを保存")
        if not filepath: return
        
        full_layout_data = {"general_settings": {"grid_spacing": self.grid_spacing}, "items": []}
        
        for item_info_loop in self.canvas_items: 
            item_id = item_info_loop['id']
            item_type = item_info_loop['type']
            
            bbox = self.canvas_frame.bbox(item_id) 
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
                except tk.TclError: pass
                if colors: item_data['colors'] = colors

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
        filepath = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")], title="レイアウトを開く")
        if not filepath: return
        
        # Clear existing items and selection state
        for item_info_to_delete in list(self.canvas_items): 
            self.canvas_frame.delete(item_info_to_delete['id'])
        self.canvas_items.clear()
        self.selected_item_ids.clear() # Use new multi-selection set
        self.selected_widget = None
        self.selected_item_info = None
        
        # Clear visual feedback
        for rect_id in self.highlight_rects.values():
            self.canvas_frame.delete(rect_id)
        self.highlight_rects.clear()
        self.canvas_frame.delete(self.ALL_RESIZE_HANDLES_TAG)
        
        self.update_property_editor() # Update editor to reflect no selection

        try:
            with open(filepath, 'r', encoding='utf-8') as f: 
                full_layout_data = json.load(f)
        except Exception as e:
            print(f"レイアウトファイル読み込みエラー: {e}"); tkinter.messagebox.showerror("オープンエラー", f"レイアウトファイルの読み込み中にエラー: {e}"); return

        general_settings = full_layout_data.get("general_settings", {})
        loaded_grid_spacing = general_settings.get("grid_spacing", 20) 
        self.grid_spacing = loaded_grid_spacing; self.prop_grid_size.set(loaded_grid_spacing) 
        self.draw_grid() 

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
                    img_id = self.canvas_frame.create_image(load_x, load_y, image=tk_photo, anchor=tk.NW)
                    new_item_info = {'id': img_id, 'type': 'image', 'obj': tk_photo, 'path': info['path'], 
                                     'width': pil_image_resized.width, 'height': pil_image_resized.height, 
                                     'original_pil_image': pil_image_orig }
                    self.canvas_items.append(new_item_info)
                    self.canvas_frame.tag_bind(img_id, "<ButtonPress-1>", lambda e, i_id=img_id: self.on_canvas_item_press(e, i_id))
                except FileNotFoundError: tkinter.messagebox.showwarning("画像読み込みエラー", f"画像ファイルが見つかりません:\n{info.get('path')}")
                except Exception as e: print(f"Error image {info.get('path')}: {e}"); tkinter.messagebox.showwarning("画像読み込みエラー", f"画像 {info.get('path')} 再作成失敗:\n{e}")

    def generate_code(self):
        code_window = tk.Toplevel(self); code_window.title("Generated Code"); code_window.geometry("700x750")
        text_area = tk.Text(code_window, wrap="word", font=("Courier New", 10))
        scrollbar = ttk.Scrollbar(code_window, command=text_area.yview)
        text_area.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y"); text_area.pack(expand=True, fill="both")
        
        code_lines = [
            "import tkinter as tk", "from tkinter import ttk", "import tkinter.font as tkfont",
            "from PIL import Image, ImageTk\n", "class App(tk.Tk):", "    def __init__(self):",
            "        super().__init__()", f"        self.title('Generated Layout')",
            f"        self.geometry('{self.canvas_frame.winfo_width()}x{self.canvas_frame.winfo_height()}')\n",
            "        self._image_references_generated_app = []\n"
        ]
        widget_counter = 0
        for item_info_loop in self.canvas_items: 
            widget_counter += 1; var_name = f"self.item_{widget_counter}"
            item_id = item_info_loop['id']; item_type = item_info_loop['type']
            bbox = self.canvas_frame.bbox(item_id)
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
                # If forcing pixel dimensions in generated code via place:
                # place_opts_list.append(f"width={int(item_w)}")
                # place_opts_list.append(f"height={int(item_h)}")
                code_lines.append(f"        {var_name}.place({', '.join(place_opts_list)})\n")

            elif item_type == 'image':
                img_path_escaped = item_info_loop['path'].replace('\\', '\\\\')
                img_w, img_h = int(item_info_loop['width']), int(item_info_loop['height'])
                code_lines.extend([
                    f"        # Image: {img_path_escaped}", "        try:",
                    f"            pil_img_{widget_counter} = Image.open(r'{img_path_escaped}')",
                    f"            pil_img_{widget_counter} = pil_img_{widget_counter}.resize(({img_w}, {img_h}), Image.Resampling.LANCZOS)",
                    f"            {var_name}_img_tk = ImageTk.PhotoImage(pil_img_{widget_counter})",
                    f"            self._image_references_generated_app.append({var_name}_img_tk)",
                    f"            {var_name} = tk.Label(self, image={var_name}_img_tk, borderwidth=0)",
                    f"            {var_name}.image = {var_name}_img_tk ",
                    f"            {var_name}.place(x={place_x}, y={place_y})",
                    f"        except Exception as e:",
                    f"            print(f'Error loading image {{e}} for {var_name}')\n"
                ])
        code_lines.extend(["\nif __name__ == '__main__':", "    app = App()", "    app.mainloop()"])
        text_area.insert("1.0", "\n".join(code_lines)); text_area.config(state="disabled")

    def deselect_all(self):
        if self.selected_item_ids:
            self.selected_item_ids.clear()
        self.selected_widget = None
        self.selected_item_info = None
        for rect_id in self.highlight_rects.values():
            self.canvas_frame.delete(rect_id)
        self.highlight_rects.clear()
        self.canvas_frame.delete(self.ALL_RESIZE_HANDLES_TAG)
        self.update_property_editor()

if __name__ == "__main__":
    app = LayoutDesigner()
    app.mainloop()
