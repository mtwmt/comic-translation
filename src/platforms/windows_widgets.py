"""Windows-only sizing and clicks for the translator selection row."""
from __future__ import annotations

from tkinter import ttk


def configure_translator_controls(gui):
    padding = 12
    ttk.Style(gui.root).configure("Model.TCombobox", padding=(padding, 3, padding, 3))
    gui.model_box.configure(style="Model.TCombobox", width=20)
    gui.provider_box.pack_configure(fill="y")
    gui.model_box.pack_configure(fill="both")
    gui.model_refresh_button.pack_configure(side="right", before=gui.model_box, fill="y")
    gui.model_box.bind("<Button-1>", lambda event: open_blank_model_area(event, gui.refresh_model_list), add="+")
    popup = str(gui.model_box.tk.call("ttk::combobox::PopdownWindow", str(gui.model_box)))
    # A flat Listbox border supplies its inset; native posting keeps this value.
    gui.model_box.tk.call(popup + ".f.l", "configure", "-borderwidth", padding, "-relief", "flat")
    from .windows_translation_controls import TranslationControls
    gui.translation_controls = TranslationControls(gui)


def open_blank_model_area(event, load_models):
    """Open the picker from unused entry space; keep text clicks editable."""
    widget = event.widget
    if widget.instate(["disabled"]) or widget.instate(["readonly"]):
        return
    if widget.identify(event.x, event.y) != "textarea":
        return  # The native class binding already handles the arrow.
    text = widget.get()
    if text:
        last = widget.bbox(len(text) - 1)
        if not last or event.x < last[0] + last[2]:
            return
    widget.focus_set()
    if widget.cget("values"):
        widget.tk.call("ttk::combobox::Post", str(widget))
    else:
        load_models()  # Give an empty picker a visible action instead of a blank popdown.
    return "break"
