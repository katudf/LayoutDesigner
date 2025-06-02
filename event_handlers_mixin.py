import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import tkinter.font as tkfont
from tkinter import colorchooser
import tkinter.messagebox
from PIL import Image, ImageTk

class EventHandlersMixin:
    def on_canvas_press(self, event):
        # self.canvas_frame や self.selected_item_ids など、
        # メインクラスの属性にアクセスする
        # ... (元の on_canvas_press のロジック) ...
        # print("Mixin: on_canvas_press called")
        overlapping_ids = self.canvas_frame.find_overlapping(event.x, event.y, event.x, event.y)
        is_on_resize_handle = False
        if overlapping_ids:
            for item_id_overlap in overlapping_ids:
                tags = self.canvas_frame.gettags(item_id_overlap)
                if any(tag.startswith(self.RESIZE_HANDLE_TAG_PREFIX) for tag in tags):
                    is_on_resize_handle = True
                    break 
        if is_on_resize_handle:
            return 

        clicked_item_id = None
        if overlapping_ids:
            for item_id_overlap in overlapping_ids:
                if any(ci['id'] == item_id_overlap for ci in self.canvas_items):
                    if "highlight_rect" not in self.canvas_frame.gettags(item_id_overlap) and \
                       "multi_highlight_rect" not in self.canvas_frame.gettags(item_id_overlap) and \
                       self.ALL_RESIZE_HANDLES_TAG not in self.canvas_frame.gettags(item_id_overlap):
                        clicked_item_id = item_id_overlap
                        break
        # --- ここで「何も選択すべきでない場合のみ」deselect_allを呼ぶ ---
        if not clicked_item_id and not self._dragged_item_id:
            self.deselect_all()
        self.canvas_frame.focus_set()


    def on_canvas_item_press(self, event, item_id):
        # ... (元の on_canvas_item_press のロジック) ...
        # print(f"[DEBUG] Mixin: on_canvas_item_press: item_id={item_id}, selected_item_ids={self.selected_item_ids}")
        self.canvas_frame.focus_set()
        self._dragged_item_id = item_id

        canvas_x = event.x
        canvas_y = event.y
        try:
            abs_x = event.widget.winfo_rootx() + event.x
            abs_y = event.widget.winfo_rooty() + event.y
            canvas_x = abs_x - self.canvas_frame.winfo_rootx()
            canvas_y = abs_y - self.canvas_frame.winfo_rooty()
        except Exception:
            pass
        self._drag_start_x, self._drag_start_y = canvas_x, canvas_y
        # print(f"[DEBUG] Mixin: on_canvas_item_press: _drag_start_x={self._drag_start_x}, _drag_start_y={self._drag_start_y}")

        is_shift_pressed = (event.state & 0x0001) != 0

        if not is_shift_pressed:
            if item_id not in self.selected_item_ids or len(self.selected_item_ids) > 1:
                # print(f"[DEBUG] Mixin: on_canvas_item_press: 単体選択 item_id={item_id}")
                current_selection_copy = set(self.selected_item_ids) 
                for prev_id in current_selection_copy:
                    if prev_id in self.highlight_rects:
                        self.canvas_frame.delete(self.highlight_rects[prev_id])
                        del self.highlight_rects[prev_id]
                self.selected_item_ids.clear()
                self.selected_item_ids.add(item_id)
        else:
            if item_id in self.selected_item_ids:
                # print(f"[DEBUG] Mixin: on_canvas_item_press: Shift+クリックで既に選択中 item_id={item_id}")
                self.selected_item_ids.remove(item_id)
                if item_id in self.highlight_rects: 
                    self.canvas_frame.delete(self.highlight_rects[item_id])
                    del self.highlight_rects[item_id]
            else:
                # print(f"[DEBUG] Mixin: on_canvas_item_press: Shift+クリックで追加選択 item_id={item_id}")
                self.selected_item_ids.add(item_id)

        # --- ここで必ず全選択アイテムのbboxをセットし直す ---
        self._dragged_item_id = item_id
        self._drag_selected_items_start_bboxes = {}
        for s_id in self.selected_item_ids:
            self._drag_selected_items_start_bboxes[s_id] = self.canvas_frame.bbox(s_id)

        self.update_property_editor_for_selection()
        self.update_highlight()

        if self.selected_item_ids:
            # print(f"[DEBUG] Mixin: on_canvas_item_press: drag対象 self.selected_item_ids={self.selected_item_ids}")
            for s_id in self.selected_item_ids:
                # print(f"[DEBUG] Mixin: on_canvas_item_press: drag対象 s_id={s_id}")
                self.canvas_frame.tag_raise(s_id) # Raise selected items
            self.canvas_frame.bind("<B1-Motion>", self.on_multi_item_drag)
            self.canvas_frame.bind("<ButtonRelease-1>", self.on_multi_item_release)

    # ... 他のイベントハンドラメソッド (on_multi_item_drag, on_multi_item_release など) をここに移動 ...
    def on_multi_item_drag(self, event):
        if not self._dragged_item_id or not self.selected_item_ids or self.active_resize_handle:
            return

        if event.widget is not self.canvas_frame:
            abs_x = event.widget.winfo_rootx() + event.x
            abs_y = event.widget.winfo_rooty() + event.y
            current_mouse_x_canvas = abs_x - self.canvas_frame.winfo_rootx()
            current_mouse_y_canvas = abs_y - self.canvas_frame.winfo_rooty()
        else:
            current_mouse_x_canvas = event.x
            current_mouse_y_canvas = event.y

        drag_delta_x = current_mouse_x_canvas - self._drag_start_x
        drag_delta_y = current_mouse_y_canvas - self._drag_start_y
        
        effective_delta_x = drag_delta_x
        effective_delta_y = drag_delta_y
        
        if self._dragged_item_id and self._dragged_item_id in self._drag_selected_items_start_bboxes:
            primary_start_bbox = self._drag_selected_items_start_bboxes[self._dragged_item_id]
            if not primary_start_bbox: # Safety check
                return

            primary_new_top_left_x_raw = primary_start_bbox[0] + drag_delta_x
            primary_new_top_left_y_raw = primary_start_bbox[1] + drag_delta_y
            
            snapped_primary_tl_x, snapped_primary_tl_y = self._snap_to_grid(primary_new_top_left_x_raw, primary_new_top_left_y_raw)
            
            effective_delta_x = snapped_primary_tl_x - primary_start_bbox[0]
            effective_delta_y = snapped_primary_tl_y - primary_start_bbox[1]

        for item_id in self.selected_item_ids:
            if item_id in self._drag_selected_items_start_bboxes:
                start_bbox = self._drag_selected_items_start_bboxes[item_id]
                if not start_bbox: continue # Safety check

                new_top_left_x = start_bbox[0] + effective_delta_x
                new_top_left_y = start_bbox[1] + effective_delta_y

                item_info = next((item for item in self.canvas_items if item['id'] == item_id), None)
                if item_info:
                    if item_info['type'] == 'widget':
                        width = item_info.get('width', start_bbox[2] - start_bbox[0])
                        height = item_info.get('height', start_bbox[3] - start_bbox[1])
                        center_x = new_top_left_x + width / 2
                        center_y = new_top_left_y + height / 2
                        self.canvas_frame.coords(item_id, center_x, center_y)
                    elif item_info['type'] == 'image':
                        self.canvas_frame.coords(item_id, new_top_left_x, new_top_left_y)
        
        self.update_highlight()

    def on_multi_item_release(self, event):
        self._dragged_item_id = None
        self._drag_selected_items_start_bboxes.clear()
        
        self.canvas_frame.unbind("<B1-Motion>")
        self.canvas_frame.unbind("<ButtonRelease-1>")
        
        self.canvas_frame.bind("<ButtonPress-1>", self.on_canvas_press) # Restore general press binding