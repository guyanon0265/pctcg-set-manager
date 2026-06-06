import os
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# --- Single Sub-Path Variables ---
OCTGN_GAMEDB_SUBPATH = (
    "OCTGN",
    "Data",
    "GameDatabase",
    "09f9c76e-be8b-4f68-992e-f23e99348db0",
    "Sets",
)

OCTGN_IMAGEDB_SUBPATH = (
    "OCTGN",
    "Data",
    "ImageDatabase",
    "09f9c76e-be8b-4f68-992e-f23e99348db0",
    "Sets",
)

# --- Master Dropdown Menu Option Pools ---
SUPERTYPES = ["Pokemon", "Trainer", "Energy"]

POKEMON_TYPES = ["Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting", "Dark", "Metal", "Fairy",
                 "Dragon", "Colorless", "Other"]

POKEMON_SUBTYPES = ["Basic", "Stage 1", "Stage 2", "Other"]

TRAINER_TYPES = ["Item", "Supporter", "Stadium", "Tool"]
TRAINER_SUBTYPES = ["None", "Tool"]

ENERGY_SUBTYPES = ["Basic Energy", "Special Energy"]

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def resolve_paths() -> tuple[Path | None, Path | None]:
    """Checks all fallback root paths and returns both GameDB and ImageDB paths."""
    possible_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path.home(),
        Path.cwd(),
    ]
    game_path = None
    image_path = None

    for root in possible_roots:
        g_full = root / Path(*OCTGN_GAMEDB_SUBPATH)
        i_full = root / Path(*OCTGN_IMAGEDB_SUBPATH)
        if g_full.is_dir() and game_path is None:
            game_path = g_full
        if i_full.is_dir() and image_path is None:
            image_path = i_full

    # Fallback if directories aren't created yet but parent roots exist
    if not game_path or not image_path:
        for root in possible_roots:
            if (root / "OCTGN").is_dir():
                game_path = game_path or root / Path(*OCTGN_GAMEDB_SUBPATH)
                image_path = image_path or root / Path(*OCTGN_IMAGEDB_SUBPATH)
                break

    return game_path, image_path


SET_DATABASE_PATH, SET_IMAGE_PATH = resolve_paths()


def get_game_name_from_xml(uuid_dir_path: Path) -> str:
    """Parses set.xml to extract the set's actual name attribute."""
    xml_path = uuid_dir_path / "set.xml"
    if not xml_path.exists():
        return "Unknown (Missing set.xml)"
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        game_name = root.attrib.get("name")
        if game_name:
            return game_name
    except Exception as e:
        return f"Error parsing XML ({e})"
    return "Unknown (Name attribute not found)"


def parse_version(version_str: str) -> tuple[int, int]:
    """Converts a two-number version string into a tuple of integers for comparison."""
    try:
        parts = version_str.split('.')
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return (0, 0)


def update_set_version(root_element: ET.Element, action_type: str):
    """Updates the two-number version attribute based on the action type.

    action_type can be 'major' (add/delete) or 'minor' (edit).
    """
    current_ver = root_element.attrib.get("version", "1.0")
    major, minor = parse_version(current_ver)

    if action_type == "major":
        major += 1
        minor = 0
    elif action_type == "minor":
        minor += 1

    root_element.set("version", f"{major}.{minor}")


def save_xml_changes(xml_path: Path, tree: ET.ElementTree) -> bool:
    """Helper function to cleanly write XML changes back to disk."""
    try:
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        return True
    except Exception as e:
        messagebox.showerror("Save Error", f"Failed to save changes to disk:\n{e}")
        return False


def find_card_image(set_uuid: str, card_uuid: str) -> Path | None:
    """Searches the ImageDatabase directory for matching target file extensions."""
    if not SET_IMAGE_PATH:
        return None
    cards_dir = SET_IMAGE_PATH / set_uuid / "Cards"
    if not cards_dir.is_dir():
        return None

    for ext in [".png", ".jpg", ".jpeg"]:
        img_path = cards_dir / f"{card_uuid}{ext}"
        if img_path.exists():
            return img_path
    return None


def open_file_externally(file_path: Path):
    """Launches the specified file or directory in the user's OS default application."""
    if not file_path or not file_path.exists():
        messagebox.showerror("Error", "The specified asset file or directory could not be found on disk.")
        return
    try:
        if sys.platform == "win32":
            os.startfile(file_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(file_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(file_path)], check=True)
    except Exception as e:
        messagebox.showerror("Launch Error", f"Could not launch native default system explorer application:\n{e}")


def load_directories(treeview: ttk.Treeview, status_label: tk.Label):
    """Scans the resolved database path and populates the GUI."""
    if not SET_DATABASE_PATH or not SET_DATABASE_PATH.exists():
        messagebox.showerror("Error", "Could not locate the OCTGN GameDatabase path workspace.")
        status_label.config(text="Directory paths not found.", fg="red")
        return

    status_label.config(text=f"Database: {SET_DATABASE_PATH}", fg="black")
    for item in treeview.get_children():
        treeview.delete(item)

    try:
        count = 0
        for entry in SET_DATABASE_PATH.iterdir():
            if entry.is_dir():
                uuid_name = entry.name
                game_name = get_game_name_from_xml(entry)
                treeview.insert("", "end", values=(game_name, uuid_name))
                count += 1
        status_label.config(text=f"Successfully loaded {count} sets.", fg="green")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to read directory:\n{e}")


# --- SET CRUD FUNCTIONS ---

def add_set(treeview: ttk.Treeview, status_label: tk.Label):
    if not SET_DATABASE_PATH:
        return
    set_name = simpledialog.askstring("Add Set", "Enter new Set Name:")
    if not set_name:
        return

    new_uuid = str(uuid.uuid4())
    new_set_dir = SET_DATABASE_PATH / new_uuid
    new_img_dir = SET_IMAGE_PATH / new_uuid / "Cards" if SET_IMAGE_PATH else None

    try:
        new_set_dir.mkdir(parents=True, exist_ok=True)
        if new_img_dir:
            new_img_dir.mkdir(parents=True, exist_ok=True)

        root = ET.Element("set", name=set_name, id=new_uuid, gameId="09f9c76e-be8b-4f68-992e-f23e99348db0",
                          gameVersion="1.0.0.0", version="1.0")
        ET.SubElement(root, "cards")
        tree = ET.ElementTree(root)

        if save_xml_changes(new_set_dir / "set.xml", tree):
            load_directories(treeview, status_label)
            messagebox.showinfo("Success", f"Created new set & image repository folder layouts for: {set_name}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to create complete workspace directory mappings:\n{e}")


def edit_set(treeview: ttk.Treeview, status_label: tk.Label):
    selected = treeview.selection()
    if not selected:
        return
    item = selected[0]
    old_name, set_uuid = treeview.item(item, "values")

    new_name = simpledialog.askstring("Edit Set", "Enter new Set Name:", initialvalue=old_name)
    if not new_name or new_name == old_name:
        return

    xml_path = SET_DATABASE_PATH / set_uuid / "set.xml"
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        root.set("name", new_name)
        update_set_version(root, "minor")
        if save_xml_changes(xml_path, tree):
            treeview.item(item, values=(new_name, set_uuid))
    except Exception as e:
        messagebox.showerror("Error", f"Failed to update set XML:\n{e}")


def delete_set(treeview: ttk.Treeview, status_label: tk.Label):
    selected = treeview.selection()
    if not selected:
        return
    item = selected[0]
    set_name, set_uuid = treeview.item(item, "values")

    confirm = messagebox.askyesno("Confirm Delete",
                                  f"Are you sure you want to completely delete '{set_name}' data & card assets?")
    if not confirm:
        return

    set_dir = SET_DATABASE_PATH / set_uuid
    img_dir = SET_IMAGE_PATH / set_uuid if SET_IMAGE_PATH else None

    try:
        if set_dir.exists():
            shutil.rmtree(set_dir)
        if img_dir and img_dir.exists():
            shutil.rmtree(img_dir)

        treeview.delete(item)
        status_label.config(text=f"Deleted set: {set_name}", fg="orange")
    except Exception as e:
        messagebox.showerror("Delete Error", f"Could not cleanly wipe targeted folders: \n{e}")


def open_all_sets_folder():
    """Opens the main root directory folder containing all database sets."""
    if SET_DATABASE_PATH and SET_DATABASE_PATH.exists():
        open_file_externally(SET_DATABASE_PATH)
    else:
        messagebox.showerror("Folder Error", "The root sets directory path could not be located on disk.")


# --- IMPORT / EXPORT UTILITIES ---

def export_set(treeview: ttk.Treeview):
    """Bundles set.xml and card images into a custom .ptco zip file architecture."""
    selected = treeview.selection()
    if not selected:
        messagebox.showwarning("Export", "Please select a set from the list to export.")
        return

    set_name, set_uuid = treeview.item(selected[0], "values")

    export_filename = filedialog.asksaveasfilename(
        title="Export Set Bundle",
        initialfile=f"{set_name}.ptco",
        filetypes=[("Pokemon Custom TCG Bundle", "*.ptco")]
    )
    if not export_filename:
        return

    xml_file_path = SET_DATABASE_PATH / set_uuid / "set.xml"
    images_dir_path = SET_IMAGE_PATH / set_uuid / "Cards" if SET_IMAGE_PATH else None

    if not xml_file_path.exists():
        messagebox.showerror("Export Error", f"Could not locate critical data configuration layout: {xml_file_path}")
        return

    try:
        with zipfile.ZipFile(export_filename, 'w', zipfile.ZIP_DEFLATED) as ptco_zip:
            ptco_zip.write(xml_file_path, "set.xml")

            if images_dir_path and images_dir_path.is_dir():
                for img_file in images_dir_path.iterdir():
                    if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                        ptco_zip.write(img_file, f"Cards/{img_file.name}")

        messagebox.showinfo("Export Complete", f"Successfully built and exported custom package:\n{export_filename}")
    except Exception as e:
        messagebox.showerror("Export Error", f"An anomaly aborted the collection script assembly sequence:\n{e}")


def import_set(treeview: ttk.Treeview, status_label: tk.Label):
    """Unpacks a .ptco custom package safely adjusting mapping references or overwriting based on versioning numbers."""
    if not SET_DATABASE_PATH or not SET_IMAGE_PATH:
        messagebox.showerror("Import Error", "OCTGN destination path configurations are incomplete.")
        return

    import_file = filedialog.askopenfilename(
        title="Select Package Bundle to Import",
        filetypes=[("Pokemon Custom TCG Bundle", "*.ptco")]
    )
    if not import_file:
        return

    try:
        with zipfile.ZipFile(import_file, 'r') as ptco_zip:
            file_list = ptco_zip.namelist()

            if "set.xml" not in file_list:
                messagebox.showerror("Import Error", "Invalid bundle format: Missing configuration core 'set.xml'.")
                return

            xml_data = ptco_zip.read("set.xml")
            root = ET.fromstring(xml_data)

            imported_name = root.attrib.get("name", "Unnamed Imported Set")
            imported_uuid = root.attrib.get("id")
            imported_version_str = root.attrib.get("version", "1.0")

            if not imported_uuid:
                imported_uuid = str(uuid.uuid4())
                root.set("id", imported_uuid)
                root.set("version", imported_version_str)
                xml_data = ET.tostring(root, encoding="utf-8")

            target_db_dir = SET_DATABASE_PATH / imported_uuid
            target_img_dir = SET_IMAGE_PATH / imported_uuid / "Cards"

            execute_overwrite = False

            if target_db_dir.exists():
                local_xml_path = target_db_dir / "set.xml"
                local_version_str = "1.0"
                local_name = ""

                if local_xml_path.exists():
                    try:
                        local_tree = ET.parse(local_xml_path)
                        local_root = local_tree.getroot()
                        local_version_str = local_root.attrib.get("version", "1.0")
                        local_name = local_root.attrib.get("name", "")
                    except Exception:
                        pass

                if local_name == imported_name:
                    if parse_version(imported_version_str) > parse_version(local_version_str):
                        execute_overwrite = True
                    else:
                        overwrite = messagebox.askyesno(
                            "Collision Detected",
                            f"Set '{imported_name}' already exists with an equal or higher version ({local_version_str} >= {imported_version_str}).\n"
                            f"Do you want to force overwrite it anyway?"
                        )
                        if overwrite:
                            execute_overwrite = True
                        else:
                            imported_uuid = str(uuid.uuid4())
                            root.set("id", imported_uuid)
                            xml_data = ET.tostring(root, encoding="utf-8")
                            target_db_dir = SET_DATABASE_PATH / imported_uuid
                            target_img_dir = SET_IMAGE_PATH / imported_uuid / "Cards"
                else:
                    overwrite = messagebox.askyesno(
                        "Collision Detected",
                        f"A set with UUID '{imported_uuid}' already exists but has a different name ('{local_name}').\nDo you want to overwrite it?"
                    )
                    if overwrite:
                        execute_overwrite = True
                    else:
                        imported_uuid = str(uuid.uuid4())
                        root.set("id", imported_uuid)
                        xml_data = ET.tostring(root, encoding="utf-8")
                        target_db_dir = SET_DATABASE_PATH / imported_uuid
                        target_img_dir = SET_IMAGE_PATH / imported_uuid / "Cards"

            if execute_overwrite:
                if target_db_dir.exists():
                    shutil.rmtree(target_db_dir)
                if target_img_dir.parent.exists():
                    shutil.rmtree(target_img_dir.parent)

            target_db_dir.mkdir(parents=True, exist_ok=True)
            target_img_dir.mkdir(parents=True, exist_ok=True)

            with open(target_db_dir / "set.xml", "wb") as f:
                f.write(xml_data)

            for member in file_list:
                if member.startswith("Cards/") and member != "Cards/":
                    filename = os.path.basename(member)
                    if filename:
                        source_bytes = ptco_zip.read(member)
                        with open(target_img_dir / filename, "wb") as f:
                            f.write(source_bytes)

        load_directories(treeview, status_label)
        messagebox.showinfo("Import Success", f"Imported successfully:\n'{imported_name}' (v{imported_version_str})")
    except Exception as e:
        messagebox.showerror("Import Error", f"Extraction processing framework crashed prematurely:\n{e}")


# --- CONDITIONAL INTERACTIVE DROPDOWN DIALOG FORM ---

class CardFormDialog(simpledialog.Dialog):
    """Custom popup window enforcing dynamic conditional choices along with mandatory name and image validation."""

    def __init__(self, parent, title, initial_name="", initial_props=None, set_uuid=""):
        self.initial_name = initial_name
        self.initial_props = initial_props or {"Supertype": "Pokemon", "Type": "", "Dual Type": "", "Subtype": ""}
        self.set_uuid = set_uuid
        self.selected_img_src = None

        if initial_props and "id" in initial_props:
            self.selected_img_src = find_card_image(set_uuid, initial_props["id"])

        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="Card Name:").grid(row=0, column=0, sticky="w", pady=5, padx=5)
        self.entry_name = tk.Entry(master, width=30)
        self.entry_name.insert(0, self.initial_name)
        self.entry_name.grid(row=0, column=1, pady=5, padx=5)

        tk.Label(master, text="Supertype:").grid(row=1, column=0, sticky="w", pady=5, padx=5)
        self.combo_super = ttk.Combobox(master, values=SUPERTYPES, state="readonly", width=27)
        self.combo_super.grid(row=1, column=1, pady=5, padx=5)

        tk.Label(master, text="Type:").grid(row=2, column=0, sticky="w", pady=5, padx=5)
        self.combo_type = ttk.Combobox(master, state="readonly", width=27)
        self.combo_type.grid(row=2, column=1, pady=5, padx=5)

        tk.Label(master, text="Dual Type:").grid(row=3, column=0, sticky="w", pady=5, padx=5)
        self.combo_dual = ttk.Combobox(master, state="readonly", width=27)
        self.combo_dual.grid(row=3, column=1, pady=5, padx=5)

        tk.Label(master, text="Subtype:").grid(row=4, column=0, sticky="w", pady=5, padx=5)
        self.combo_sub = ttk.Combobox(master, state="readonly", width=27)
        self.combo_sub.grid(row=4, column=1, pady=5, padx=5)

        tk.Label(master, text="Card Image Source:").grid(row=5, column=0, sticky="w", pady=5, padx=5)
        self.btn_img = tk.Button(master, text="📸 Choose Image Asset File...", command=self.select_image_file, width=25)
        self.btn_img.grid(row=5, column=1, pady=5, padx=5)

        self.lbl_img_status = tk.Label(master, text="No new image staged", fg="gray", font=("Arial", 8, "italic"))
        self.lbl_img_status.grid(row=6, column=0, columnspan=2, pady=(0, 5))

        if self.selected_img_src:
            self.lbl_img_status.config(text=f"Current Asset: {self.selected_img_src.name}", fg="green")

        start_super = self.initial_props.get("Supertype", "Pokemon")
        if start_super in SUPERTYPES:
            self.combo_super.set(start_super)
        else:
            self.combo_super.current(0)

        self.combo_super.bind("<<ComboboxSelected>>", self.handle_supertype_change)
        self.combo_type.bind("<<ComboboxSelected>>", self.handle_type_change)

        self.handle_supertype_change(None, initial_load=True)

        return self.entry_name

    def select_image_file(self):
        """Launches file selection dialog framework filtering for valid image files."""
        file_path = filedialog.askopenfilename(
            title="Select Card Image Source",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg"), ("PNG Images", "*.png"), ("JPEG Images", "*.jpg;*.jpeg")]
        )
        if file_path:
            self.selected_img_src = Path(file_path)
            self.lbl_img_status.config(text=f"Staged: {self.selected_img_src.name}", fg="blue")

    def handle_supertype_change(self, event, initial_load=False):
        choice = self.combo_super.get()

        if choice == "Pokemon":
            self.combo_type.config(state="readonly", values=POKEMON_TYPES)
            self.combo_dual.config(state="readonly", values=["None"] + POKEMON_TYPES)
            self.combo_sub.config(state="readonly", values=POKEMON_SUBTYPES)

            if initial_load:
                self.combo_type.set(self.initial_props.get("Type", POKEMON_TYPES[0]))
                self.combo_dual.set(self.initial_props.get("Dual Type", "None"))
                self.combo_sub.set(self.initial_props.get("Subtype", POKEMON_SUBTYPES[0]))
            else:
                self.combo_type.current(0)
                self.combo_dual.set("None")
                self.combo_sub.current(0)

        elif choice == "Trainer":
            self.combo_type.config(state="readonly", values=TRAINER_TYPES)
            self.combo_dual.config(values=["None"])
            self.combo_dual.set("None")
            self.combo_dual.config(state=tk.DISABLED)

            if initial_load:
                self.combo_type.set(self.initial_props.get("Type", TRAINER_TYPES[0]))
            else:
                self.combo_type.current(0)

            self.handle_type_change(None, initial_load=initial_load)

        elif choice == "Energy":
            self.combo_type.config(state="readonly", values=POKEMON_TYPES)
            self.combo_dual.config(values=["None"])
            self.combo_dual.set("None")
            self.combo_dual.config(state=tk.DISABLED)

            self.combo_sub.config(state="readonly", values=ENERGY_SUBTYPES)
            if initial_load:
                self.combo_type.set(self.initial_props.get("Type", POKEMON_TYPES[0]))
                self.combo_sub.set(self.initial_props.get("Subtype", ENERGY_SUBTYPES[0]))
            else:
                self.combo_type.current(0)
                self.combo_sub.current(0)

    def handle_type_change(self, event, initial_load=False):
        if self.combo_super.get() != "Trainer":
            return

        trainer_type = self.combo_type.get()

        if trainer_type == "Item":
            self.combo_sub.config(state="readonly", values=TRAINER_SUBTYPES)
            if initial_load:
                self.combo_sub.set(self.initial_props.get("Subtype", "None"))
            else:
                self.combo_sub.set("None")
        else:
            self.combo_sub.config(values=["None"])
            self.combo_sub.set("None")
            self.combo_sub.config(state=tk.DISABLED)

    def validate(self) -> bool:
        """Enforces strict criteria rules requiring names and file references before allowing window closing."""
        name_val = self.entry_name.get().strip()
        if not name_val:
            messagebox.showwarning("Validation Error", "A Card Name is required.")
            return False

        if not self.selected_img_src or not Path(self.selected_img_src).exists():
            messagebox.showwarning("Validation Error", "An image file must be selected to create or update this card.")
            return False

        return True

    def apply(self):
        name_val = self.entry_name.get().strip()
        super_val = self.combo_super.get()

        type_val = self.combo_type.get()
        dual_val = self.combo_dual.get()
        sub_val = self.combo_sub.get()

        valid_properties = {"Supertype": super_val}

        if super_val == "Pokemon":
            valid_properties["Type"] = type_val
            if dual_val and dual_val != "None":
                valid_properties["Dual Type"] = dual_val
            if sub_val and sub_val != "None":
                valid_properties["Subtype"] = sub_val

        elif super_val == "Trainer":
            valid_properties["Type"] = type_val
            if type_val == "Item" and sub_val and sub_val != "None":
                valid_properties["Subtype"] = sub_val

        elif super_val == "Energy":
            valid_properties["Type"] = type_val
            if sub_val and sub_val != "None":
                valid_properties["Subtype"] = sub_val

        self.result = {
            "name": name_val,
            "properties": valid_properties,
            "staged_image": Path(self.selected_img_src)
        }


# --- CARDS MANAGEMENT SYSTEM WITH LIVE PREVIEW RENDERING ---

def show_cards_popup(parent: tk.Tk, set_name: str, set_uuid: str):
    """Creates secondary window displaying cards with a structural canvas asset preview window."""
    if not SET_DATABASE_PATH:
        return

    xml_path = SET_DATABASE_PATH / set_uuid / "set.xml"
    if not xml_path.exists():
        messagebox.showerror("Error", f"Could not find set.xml for {set_name}")
        return

    popup = tk.Toplevel(parent)
    popup.title(f"Editing Set: {set_name}")
    popup.geometry("1100x750")
    popup.grab_set()

    try:
        # Uses the resource_path function we added to your main script
        icon_file = resource_path("icon.ico")
        popup.iconbitmap(icon_file)
    except Exception as e:
        print(f"Popup icon error: {e}")

    lbl = tk.Label(popup, text=f"Cards Management: {set_name}", font=("Arial", 11, "bold"))
    lbl.pack(pady=10)

    main_container = tk.Frame(popup)
    main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    table_frame = tk.Frame(main_container)
    table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    columns = ("value_column",)
    tree = ttk.Treeview(table_frame, columns=columns, show="tree headings")
    tree.heading("#0", text="Card / Property Element")
    tree.heading("value_column", text="Value / ID")
    tree.column("#0", width=350, anchor=tk.W)
    tree.column("value_column", width=220, anchor=tk.W)

    scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    image_preview_frame = tk.Frame(main_container, width=280, bd=2, relief=tk.SUNKEN, bg="#f0f0f0")
    image_preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
    image_preview_frame.pack_propagate(False)

    lbl_img_title = tk.Label(image_preview_frame, text="Card Display", font=("Arial", 10, "bold"), bg="#f0f0f0")
    lbl_img_title.pack(pady=5)

    canvas_img = tk.Label(image_preview_frame, text="[ No Card Selected ]", bg="#e0e0e0", bd=1, relief=tk.SOLID)
    canvas_img.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    btn_open_external = tk.Button(
        image_preview_frame,
        text="🖼️ Open in Photo App",
        command=lambda: open_file_externally(active_card_image_path[0]),
        state=tk.DISABLED,
        bg="#f5f5f5"
    )
    btn_open_external.pack(fill=tk.X, padx=10, pady=5)

    panel_frame = tk.Frame(main_container, width=140, padx=10)
    panel_frame.pack(side=tk.RIGHT, fill=tk.Y)

    preview_toggle_frame = tk.Frame(popup)
    preview_toggle_frame.pack(fill=tk.X, padx=15, pady=(5, 0))

    xml_preview_visible = tk.BooleanVar(value=False)

    def toggle_xml_view():
        if xml_preview_visible.get():
            xml_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 5))
        else:
            xml_container.pack_forget()

    chk_xml = tk.Checkbutton(preview_toggle_frame, text="Show XML Source Code Live Preview",
                             variable=xml_preview_visible, command=toggle_xml_view, font=("Arial", 9, "italic"))
    chk_xml.pack(side=tk.LEFT)

    xml_container = tk.LabelFrame(popup, text="set.xml Core Hierarchy Preview", font=("Arial", 9, "bold"))

    xml_text_box = tk.Text(xml_container, height=8, font=("Consolas", 10), bg="#fafafa", wrap=tk.NONE)
    xml_scroll_v = ttk.Scrollbar(xml_container, orient=tk.VERTICAL, command=xml_text_box.yview)
    xml_scroll_h = ttk.Scrollbar(xml_container, orient=tk.HORIZONTAL, command=xml_text_box.xview)
    xml_text_box.configure(yscrollcommand=xml_scroll_v.set, xscrollcommand=xml_scroll_h.set)

    xml_scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
    xml_scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
    xml_text_box.pack(fill=tk.BOTH, expand=True)

    xml_mapping = {}
    current_photo_wrapper = [None]
    active_card_image_path = [None]

    xml_tree = ET.parse(xml_path)
    xml_root = xml_tree.getroot()
    cards_block = xml_root.find("cards")
    if cards_block is None:
        cards_block = ET.SubElement(xml_root, "cards")

    def update_raw_xml_textbox():
        """Refreshes the live code preview window view formatting content blocks nicely."""
        try:
            ET.indent(xml_tree, space="    ", level=0)
            raw_bytes = ET.tostring(xml_root, encoding="utf-8")
            decoded_str = raw_bytes.decode("utf-8")

            xml_text_box.config(state=tk.NORMAL)
            xml_text_box.delete("1.0", tk.END)
            xml_text_box.insert(tk.END, decoded_str)
            xml_text_box.config(state=tk.DISABLED)
        except Exception as e:
            xml_text_box.config(state=tk.NORMAL)
            xml_text_box.delete("1.0", tk.END)
            xml_text_box.insert(tk.END, f"Error rendering XML display: {e}")
            xml_text_box.config(state=tk.DISABLED)

    def render_selected_image(*args):
        """Intercepts selection changes, calculating scaling ratios to dynamically fit the full card image into view."""
        canvas_img.config(image="", text="[ No Card Selected ]")
        btn_open_external.config(state=tk.DISABLED)
        current_photo_wrapper[0] = None
        active_card_image_path[0] = None

        selected = tree.selection()
        if not selected:
            return

        row_id = selected[0]
        node_data = xml_mapping.get(row_id)
        if not node_data:
            return

        card_el = node_data["element"] if node_data["type"] == "card" else node_data["parent_card"]
        c_id = card_el.attrib.get("id")

        if c_id:
            found_path = find_card_image(set_uuid, c_id)
            if found_path:
                active_card_image_path[0] = found_path
                btn_open_external.config(state=tk.NORMAL)
                try:
                    orig_img = tk.PhotoImage(file=str(found_path))
                    orig_w = orig_img.width()
                    orig_h = orig_img.height()

                    target_w = 240
                    target_h = 340

                    factor_w = max(1, orig_w // target_w)
                    factor_h = max(1, orig_h // target_h)
                    scale_factor = max(factor_w, factor_h)

                    if scale_factor > 1:
                        fitted_img = orig_img.subsample(scale_factor, scale_factor)
                    else:
                        fitted_img = orig_img

                    current_photo_wrapper[0] = fitted_img
                    canvas_img.config(image=fitted_img, text="")
                except Exception:
                    canvas_img.config(image="", text="[ Image Format Error ]")
            else:
                canvas_img.config(image="", text="[ Missing Image Asset ]")

    def refresh_cards_display():
        for item in tree.get_children():
            tree.delete(item)
        xml_mapping.clear()

        for card in cards_block.findall("card"):
            c_name = card.attrib.get("name", "Unknown Card")
            c_id = card.attrib.get("id", "Unknown ID")

            card_node = tree.insert("", "end", text=c_name, values=(c_id,))
            xml_mapping[card_node] = {"type": "card", "element": card}

            for prop in card.findall("property"):
                p_name = prop.attrib.get("name", "Unknown")
                p_val = prop.attrib.get("value") or (prop.text.strip() if prop.text else "")

                prop_node = tree.insert(card_node, "end", text=p_name, values=(p_val,))
                xml_mapping[prop_node] = {"type": "prop", "element": prop, "parent_card": card, "prop_name": p_name}

        update_button_states()
        render_selected_image()
        update_raw_xml_textbox()

    def update_button_states(*args):
        selected = tree.selection()
        if not selected:
            btn_edit_card.config(state=tk.DISABLED)
            btn_delete_card.config(state=tk.DISABLED)
            return

        row_id = selected[0]
        btn_edit_card.config(state=tk.NORMAL if xml_mapping.get(row_id) else tk.DISABLED)
        btn_delete_card.config(state=tk.NORMAL if xml_mapping.get(row_id) else tk.DISABLED)

    tree.bind("<<TreeviewSelect>>", lambda event: [update_button_states(), render_selected_image()])

    # --- Button Functional Actions ---

    def execute_add_card():
        dialog = CardFormDialog(popup, "Create New Card", set_uuid=set_uuid)
        if not dialog.result:
            return

        card_id = str(uuid.uuid4())
        new_card = ET.SubElement(cards_block, "card", name=dialog.result["name"], id=card_id)

        for p_key, p_val in dialog.result["properties"].items():
            ET.SubElement(new_card, "property", name=p_key, value=p_val)

        if dialog.result["staged_image"] and SET_IMAGE_PATH:
            src_path = dialog.result["staged_image"]
            dest_dir = SET_IMAGE_PATH / set_uuid / "Cards"
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_file = dest_dir / f"{card_id}{src_path.suffix}"
            try:
                shutil.copy2(src_path, dest_file)
            except Exception as e:
                messagebox.showerror("Image Save Error", f"XML database updated but asset generation failed:\n{e}")

        update_set_version(xml_root, "major")
        if save_xml_changes(xml_path, xml_tree):
            refresh_cards_display()

    def execute_edit_card():
        selected = tree.selection()
        if not selected:
            return
        row_id = selected[0]
        node_data = xml_mapping.get(row_id)
        if not node_data:
            return

        card_el = node_data["element"] if node_data["type"] == "card" else node_data["parent_card"]
        card_id = card_el.attrib.get("id")

        current_name = card_el.attrib.get("name", "")
        current_props = {"id": card_id}
        for prop in card_el.findall("property"):
            p_name = prop.attrib.get("name")
            if p_name:
                current_props[p_name] = prop.attrib.get("value") or ""

        dialog = CardFormDialog(popup, f"Edit Card: {current_name}", initial_name=current_name,
                                initial_props=current_props, set_uuid=set_uuid)
        if not dialog.result:
            return

        card_el.set("name", dialog.result["name"])

        for old_prop in card_el.findall("property"):
            card_el.remove(old_prop)

        for p_key, p_val in dialog.result["properties"].items():
            ET.SubElement(card_el, "property", name=p_key, value=p_val)

        if dialog.result["staged_image"] and SET_IMAGE_PATH:
            src_path = dialog.result["staged_image"]
            dest_dir = SET_IMAGE_PATH / set_uuid / "Cards"
            dest_dir.mkdir(parents=True, exist_ok=True)

            if src_path.is_file() and src_path.parent != dest_dir:
                for ext in [".png", ".jpg", ".jpeg"]:
                    old_img = dest_dir / f"{card_id}{ext}"
                    if old_img.exists():
                        old_img.unlink()

                dest_file = dest_dir / f"{card_id}{src_path.suffix}"
                try:
                    shutil.copy2(src_path, dest_file)
                except Exception as e:
                    messagebox.showerror("Image Update Error",
                                         f"Properties saved but file replacement encountered issues:\n{e}")

        update_set_version(xml_root, "minor")
        if save_xml_changes(xml_path, xml_tree):
            refresh_cards_display()

    def execute_delete_card():
        selected = tree.selection()
        if not selected:
            return
        row_id = selected[0]
        node_data = xml_mapping.get(row_id)
        if not node_data:
            return

        card_el = node_data["element"] if node_data["type"] == "card" else node_data["parent_card"]
        card_id = card_el.attrib.get("id")
        c_name = card_el.attrib.get("name", "this card")

        confirm = messagebox.askyesno("Confirm Delete", f"Permanently delete '{c_name}' data and matching asset files?")
        if not confirm:
            return

        if SET_IMAGE_PATH and card_id:
            cards_dir = SET_IMAGE_PATH / set_uuid / "Cards"
            for ext in [".png", ".jpg", ".jpeg"]:
                target_img = cards_dir / f"{card_id}{ext}"
                if target_img.exists():
                    try:
                        target_img.unlink()
                    except Exception:
                        pass

        cards_block.remove(card_el)
        update_set_version(xml_root, "major")
        if save_xml_changes(xml_path, xml_tree):
            refresh_cards_display()

    def open_editor_data_folder():
        set_dir = SET_DATABASE_PATH / set_uuid
        if set_dir.exists():
            open_file_externally(set_dir)
        else:
            messagebox.showerror("Error",
                                 "The specific data tracking directory configuration folder could not be found.")

    def open_editor_images_folder():
        if not SET_IMAGE_PATH:
            return
        img_dir = SET_IMAGE_PATH / set_uuid / "Cards"
        if img_dir.exists():
            open_file_externally(img_dir)
        else:
            parent_img_dir = SET_IMAGE_PATH / set_uuid
            if parent_img_dir.exists():
                open_file_externally(parent_img_dir)
            else:
                messagebox.showerror("Error", "The explicit image assets folder location could not be located on disk.")

    # --- Panel Layout ---
    tk.Label(panel_frame, text="Controls", font=("Arial", 10, "bold")).pack(pady=(0, 10))
    tk.Button(panel_frame, text="➕ Add Card", command=execute_add_card, width=16, bg="#e1f5fe").pack(pady=4)
    btn_edit_card = tk.Button(panel_frame, text="📝 Edit Card Form", command=execute_edit_card, width=16,
                              state=tk.DISABLED)
    btn_edit_card.pack(pady=4)
    btn_delete_card = tk.Button(panel_frame, text="❌ Delete Card", command=execute_delete_card, width=16,
                                state=tk.DISABLED, fg="red")
    btn_delete_card.pack(pady=4)

    tk.Label(panel_frame, text="Workspaces", font=("Arial", 9, "bold")).pack(pady=(15, 5))
    tk.Button(panel_frame, text="📂 Open Data Dir", command=open_editor_data_folder, width=16, bg="#f5f5f5").pack(pady=3)
    tk.Button(panel_frame, text="🖼️ Open Image Dir", command=open_editor_images_folder, width=16, bg="#f5f5f5").pack(
        pady=3)

    refresh_cards_display()

    footer_frame = tk.Frame(popup)
    footer_frame.pack(side=tk.BOTTOM, pady=10)
    tk.Button(footer_frame, text="Close Workspace Panel", command=popup.destroy, width=24).pack()


def on_item_select(event: tk.Event, parent: tk.Tk):
    tree = event.widget
    selected_items = tree.selection()
    if not selected_items:
        return
    item = selected_items[0]
    values = tree.item(item, "values")
    if values:
        set_name, set_uuid = values[0], values[1]
        show_cards_popup(parent, set_name, set_uuid)

# --- Main Window GUI Setup ---
def create_gui():
    root = tk.Tk()
    root.title("OCTGN PCTCG Set Editor")
    root.geometry("780x540")

    try:
        import ctypes
        myappid = 'mycompany.myproduct.subproduct.version'  # Custom arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    try:
        # Resolves path dynamically during raw execution or compiled execution
        icon_file = resource_path("icon.ico")
        root.iconbitmap(icon_file)
        root.update_idletasks()
    except Exception as e:
        # Prevents crashing if the icon is missing locally during development
        print(f"Icon error: {e}")

    title_label = tk.Label(root, text="PCTCG Set Editor Workspace", font=("Arial", 14, "bold"))
    title_label.pack(pady=10)

    status_label = tk.Label(root, text="Loading directory...", fg="gray", wraplength=650)
    status_label.pack(pady=5)

    frame = tk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    columns = ("game_name", "uuid")
    tree = ttk.Treeview(frame, columns=columns, show="headings")
    tree.heading("game_name", text="Set Name")
    tree.heading("uuid", text="Set UUID / Folder")
    tree.column("game_name", width=350, anchor=tk.W)
    tree.column("uuid", width=300, anchor=tk.W)

    scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    tree.bind("<Double-1>", lambda event: on_item_select(event, root))
    tree.bind("<Return>", lambda event: on_item_select(event, root))

    # Control Grid System
    btn_panel = tk.Frame(root)
    btn_panel.pack(pady=10)

    # First row of management buttons
    tk.Button(btn_panel, text="➕ Add Set", command=lambda: add_set(tree, status_label), width=12).grid(row=0, column=0,
                                                                                                       padx=4, pady=2)
    tk.Button(btn_panel, text="📝 Rename Set", command=lambda: edit_set(tree, status_label), width=12).grid(row=0,
                                                                                                           column=1,
                                                                                                           padx=4,
                                                                                                           pady=2)
    tk.Button(btn_panel, text="❌ Delete Set", command=lambda: delete_set(tree, status_label), width=12).grid(row=0,
                                                                                                             column=2,
                                                                                                             padx=4,
                                                                                                             pady=2)

    tk.Button(btn_panel, text="📂 Open Folder", command=open_all_sets_folder, width=12, bg="#efebe9").grid(row=0,
                                                                                                          column=3,
                                                                                                          padx=4,
                                                                                                          pady=2)
    tk.Button(btn_panel, text="🔄 Refresh", command=lambda: load_directories(tree, status_label), width=12).grid(row=0,
                                                                                                                column=4,
                                                                                                                padx=4,
                                                                                                                pady=2)

    # Second row for the sharing ecosystem
    io_panel = tk.Frame(root)
    io_panel.pack(pady=(0, 15))
    tk.Button(io_panel, text="📤 Export Bundle", command=lambda: export_set(tree), width=18, bg="#fff3e0").pack(
        side=tk.LEFT, padx=5)
    tk.Button(io_panel, text="📥 Import Bundle", command=lambda: import_set(tree, status_label), width=18,
              bg="#e8f5e9").pack(side=tk.LEFT, padx=5)

    root.after(100, lambda: load_directories(tree, status_label))
    root.mainloop()


if __name__ == "__main__":
    create_gui()