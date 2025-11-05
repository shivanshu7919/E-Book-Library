# gui_fixed.py
import os
import re
import sys
import unicodedata
import webbrowser
import subprocess
import sqlite3
import hashlib
import pandas as pd
import shutil
from datetime import datetime, timedelta
import urllib.request
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import *

# ---------- CONFIG ----------
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Books.xlsx")  # Excel is in the same folder as the script
SHEET_BOOK_PDF = "Book PDF"
SHEET_EBOOK = "E-Book"
DB_PATH = "library_users.db"

# ---------- UI constants ----------
WIN_GEOM = "900x640"
POPUP_W = 1000
POPUP_H = 900
LABEL_FONT = ("Segoe UI", 13)
HEADER_FONT = ("Segoe UI", 18, "bold")
ENTRY_IPADY = 6
BTN_WIDTH = 16

# ---------- Helpers ----------
def normalize_text(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split()).lower().strip()

def sanitize_filename(name: str) -> str:
    # remove characters not allowed in filenames, limit length
    name = (name or "").strip()
    name = re.sub(r'[\/\\\:\*\?"<>\|]', "", name)
    name = re.sub(r'\s+', ' ', name)
    if len(name) > 150:
        name = name[:150]
    return name

def get_downloads_folder():
    # Cross-platform downloads detection (best effort)
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        return os.path.join(home, "Downloads")
    elif sys.platform == "darwin":
        return os.path.join(home, "Downloads")
    else:
        # linux/unix
        return os.path.join(home, "Downloads")

def open_pdf_in_acrobat(filepath):
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        messagebox.showerror("Error", f"File not found:\n{filepath}")
        return
    try:
        if sys.platform.startswith("win"):
            # Prefer Adobe if available
            acrobat_paths = [
                r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                r"C:\Program Files\Adobe\Acrobat\Acrobat.exe",
                r"C:\Program Files (x86)\Adobe\Acrobat\Acrobat.exe",
            ]
            for p in acrobat_paths:
                if os.path.exists(p):
                    subprocess.Popen([p, filepath], shell=False)
                    return
            # fallback
            os.startfile(filepath)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", filepath])
        else:
            # linux - try xdg-open
            subprocess.Popen(["xdg-open", filepath])
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open PDF:\n{e}")

def find_pdf_in_script_dir_by_title(title: str):
    """Search the script directory for a PDF matching the book title (best-effort)."""
    if not title:
        return None
    base = os.path.dirname(__file__) or os.getcwd()
    name = sanitize_filename(title)
    candidates = [
        os.path.join(base, f"{name}.pdf"),
        os.path.join(base, f"{title}.pdf"),
        os.path.join(base, f"{name.replace(' ', '_')}.pdf"),
    ]
    norm_title = normalize_text(title)
    try:
        for fn in os.listdir(base):
            if not fn.lower().endswith(".pdf"):
                continue
            stem = os.path.splitext(fn)[0]
            if norm_title and norm_title in normalize_text(stem):
                p = os.path.join(base, fn)
                if p not in candidates:
                    candidates.insert(0, p)
    except Exception:
        pass
    for c in candidates:
        try:
            if c and os.path.exists(c):
                return os.path.abspath(c)
        except Exception:
            continue
    return None

def open_pdf_in_chrome(filepath: str) -> bool:
    """Try to open the given PDF file with Chrome (fallback to default browser).
       Returns True on success, False otherwise."""
    if not filepath:
        return False
    fp = os.path.abspath(filepath)
    if not os.path.exists(fp):
        return False
    chrome_candidates = []
    if sys.platform.startswith("win"):
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        chrome_candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        chrome_candidates = ["google-chrome", "chrome", "chromium", "chromium-browser"]

    for p in chrome_candidates:
        try:
            if os.path.isabs(p) and os.path.exists(p):
                subprocess.Popen([p, fp], shell=False)
                return True
            else:
                # try by name (may be in PATH)
                subprocess.Popen([p, fp], shell=False)
                return True
        except Exception:
            continue
    # final fallback: open file:// in default browser (Chrome will be used if it's default)
    try:
        url = "file://" + fp.replace("\\", "/")
        webbrowser.open_new_tab(url)
        return True
    except Exception:
        return False


def try_open_url_in_chrome(url):
    # Try to open in Chrome if installed; otherwise fallback to default browser.
    # Search common chrome locations (Windows) or 'google-chrome' binary (linux/mac).
    url = str(url)
    if not (url.startswith("http://") or url.startswith("https://")):
        messagebox.showerror("Invalid URL", f"Invalid URL:\n{url}")
        return
    chrome_candidates = []
    if sys.platform.startswith("win"):
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        chrome_candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        # linux: rely on typical binary names in PATH
        chrome_candidates = ["google-chrome", "chrome", "chromium", "chromium-browser"]

    for p in chrome_candidates:
        try:
            if os.path.isabs(p) and os.path.exists(p):
                subprocess.Popen([p, url], shell=False)
                return
            else:
                # try to run by name (may be in PATH)
                subprocess.Popen([p, url], shell=False)
                return
        except Exception:
            continue
    # final fallback
    webbrowser.open(url)

def ensure_excel_exists():
    folder = os.path.dirname(EXCEL_PATH)
    if folder and not os.path.exists(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass
    if not os.path.exists(EXCEL_PATH):
        pdf_df = pd.DataFrame(columns=["title", "author", "filepath"])
        ebook_df = pd.DataFrame(columns=["title", "author", "url"])
        try:
            with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
                pdf_df.to_excel(writer, index=False, sheet_name=SHEET_BOOK_PDF)
                ebook_df.to_excel(writer, index=False, sheet_name=SHEET_EBOOK)
        except Exception as e:
            print("Failed to create initial Excel:", e)

# ---------- DB init ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS issued_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    source TEXT,
                    location TEXT,
                    issue_date TEXT,
                    expiry_date TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS purchased_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    source TEXT,
                    location TEXT,
                    purchase_date TEXT,
                    price REAL
                )""")
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    if password is None:
        password = ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

# ---------- Excel helpers ----------
def load_excel():
    if not os.path.exists(EXCEL_PATH):
        messagebox.showerror("Error", f"Excel file not found at:\n{EXCEL_PATH}")
        return pd.DataFrame(), pd.DataFrame()
    try:
        xls = pd.ExcelFile(EXCEL_PATH)
        sheets = xls.sheet_names
        pdf_sheet = SHEET_BOOK_PDF if SHEET_BOOK_PDF in sheets else (sheets[0] if len(sheets) >= 1 else None)
        ebook_sheet = SHEET_EBOOK if SHEET_EBOOK in sheets else (sheets[1] if len(sheets) >= 2 else None)
        pdf_df = pd.read_excel(xls, sheet_name=pdf_sheet) if pdf_sheet else pd.DataFrame()
        ebook_df = pd.read_excel(xls, sheet_name=ebook_sheet) if ebook_sheet else pd.DataFrame()
        pdf_df.columns = [c.lower().strip() for c in pdf_df.columns]
        ebook_df.columns = [c.lower().strip() for c in ebook_df.columns]
        return pdf_df, ebook_df
    except Exception as e:
        messagebox.showerror("Error loading Excel", str(e))
        return pd.DataFrame(), pd.DataFrame()

def save_excel(pdf_df, ebook_df):
    try:
        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl", mode="w") as writer:
            pdf_df.to_excel(writer, index=False, sheet_name=SHEET_BOOK_PDF)
            ebook_df.to_excel(writer, index=False, sheet_name=SHEET_EBOOK)
        messagebox.showinfo("Saved", "Excel file updated.")
    except Exception as e:
        messagebox.showerror("Error saving Excel", str(e))

# ---------- Reusable searchable window ----------
def open_search_window(master, data_list, title="Search Books", on_select=None):
    win = tb.Toplevel(master)
    win.title(title)
    win.geometry(f"{POPUP_W}x{POPUP_H}")
    win.resizable(False, False)

    header = tb.Frame(win, padding=12)
    header.pack(fill="x")
    tb.Label(header, text=title, font=HEADER_FONT).pack(anchor="w")

    search_var = tb.StringVar()
    search_entry = tb.Entry(win, textvariable=search_var)
    search_entry.pack(fill="x", padx=12, pady=(6,8))
    search_entry.configure(font=("Segoe UI", 12))

    list_frame = tb.Frame(win)
    list_frame.pack(fill="both", expand=True, padx=12, pady=(0,8))

    scrollbar = tk.Scrollbar(list_frame, orient="vertical")
    scrollbar.pack(side="right", fill="y")
    listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Segoe UI", 11))
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    working = []
    for item in data_list:
        if isinstance(item, dict):
            working.append(item.copy())
        else:
            working.append({k: (None if pd.isna(v) else v) for k, v in item.items()})

    def render(items):
        listbox.delete(0, "end")
        for idx, rd in enumerate(items):
            t = str(rd.get('title') or "")
            a = str(rd.get('author') or "")
            typ = "PDF" if rd.get('source') == 'pdf' else "Online"
            listbox.insert("end", f"{idx}: {t} — {a}  ({typ})")

    def filter_reorder(_=None):
        q = search_var.get().strip().lower()
        if not q:
            render(working)
            return
        matched = [rd for rd in working if q in str(rd.get('title') or "").lower()]
        others = [rd for rd in working if rd not in matched]
        render(matched + others)

    render(working)
    search_entry.bind("<KeyRelease>", filter_reorder)

    def fill_with_select(evt):
        sel = listbox.curselection()
        if not sel:
            return
        text = listbox.get(sel[0])
        try:
            selected_index = int(text.split(":", 1)[0])
        except Exception:
            selected_index = sel[0]
        if selected_index < 0 or selected_index >= len(working):
            return
        chosen = working[selected_index]
        search_var.set(str(chosen.get('title') or ""))

    listbox.bind("<<ListboxSelect>>", fill_with_select)

    def do_select():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("Select", "Please select a book from the list first.")
            return
        text = listbox.get(sel[0])
        try:
            selected_index = int(text.split(":", 1)[0])
        except Exception:
            selected_index = sel[0]
        chosen = working[selected_index]
        if on_select:
            on_select(chosen)
        win.destroy()

    btns = tb.Frame(win, padding=8)
    btns.pack(fill="x")
    tb.Button(btns, text="Select", bootstyle="success", width=BTN_WIDTH, command=do_select).pack(side="left", padx=6)
    tb.Button(btns, text="Close", bootstyle="secondary", width=BTN_WIDTH, command=win.destroy).pack(side="right", padx=6)

    return win

# ---------- Application ----------
class LibraryApp:
    def __init__(self):
        ensure_excel_exists()
        init_db()
        # Use a dark theme: 'darkly' is a good dark theme in ttkbootstrap
        self.root = tb.Window(themename="darkly")
        self.root.title("E-Book Library System")
        self.root.geometry(WIN_GEOM)
        self.root.resizable(False, False)
        self.current_user = None
        self.cleanup_expired_issues_on_startup()
        self.create_main_menu()

    def create_main_menu(self):
        for w in self.root.winfo_children():
            w.destroy()
        frame = tb.Frame(self.root, padding=26)
        frame.pack(fill="both", expand=True)
        tb.Label(frame, text="📚 E-Book Library System", font=("Segoe UI", 24, "bold")).pack(pady=(8, 18))
        tb.Button(frame, text="Management", bootstyle="info", width=24, command=self.management_login).pack(pady=10)
        tb.Button(frame, text="Customer", bootstyle="primary", width=24, command=self.customer_entry).pack(pady=10)
        tb.Button(frame, text="Exit", bootstyle="danger", width=24, command=self.root.destroy).pack(pady=30)

    # ---------- management ----------
    def management_login(self):
        popup = tb.Toplevel(self.root)
        popup.title("Management Login")
        popup.geometry(f"{POPUP_W}x{POPUP_H}")
        popup.resizable(False, False)
        frm = tb.Frame(popup, padding=18)
        frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Management Login", font=HEADER_FONT).pack(pady=(0,14))
        tb.Label(frm, text="Username", font=LABEL_FONT).pack(anchor="w")
        user_entry = tb.Entry(frm)
        user_entry.pack(fill="x", pady=(0,8))
        user_entry.configure(font=("Segoe UI", 12))
        tb.Label(frm, text="Password", font=LABEL_FONT).pack(anchor="w")
        pwd_entry = tb.Entry(frm, show="*")
        pwd_entry.pack(fill="x", pady=(0,12))
        pwd_entry.configure(font=("Segoe UI", 12))

        def do_login():
            user = (user_entry.get() or "").strip()
            pwd = (pwd_entry.get() or "").strip()
            if not user or not pwd:
                messagebox.showwarning("Input", "Both fields are required.")
                return
            # Simple management check: a specific management username/password
            # NOTE: keep this limited. For production, create admin users in DB with proper privilege management.
            if user.lower() == "shiva_007".lower() and pwd == "12345":
                popup.destroy()
                self.management_panel()
            else:
                messagebox.showerror("Access Denied", "Invalid credentials. Access denied.")

        btns = tb.Frame(frm)
        btns.pack(fill="x", pady=(8,0))
        tb.Button(btns, text="Login", bootstyle="primary", width=BTN_WIDTH, command=do_login).pack(side="left", padx=8)
        tb.Button(btns, text="Back", bootstyle="secondary", width=BTN_WIDTH, command=popup.destroy).pack(side="right", padx=8)

    def management_panel(self):
        for w in self.root.winfo_children():
            w.destroy()
        frm = tb.Frame(self.root, padding=18)
        frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Management Panel", font=HEADER_FONT).pack(pady=(0,12))
        tb.Button(frm, text="Add Book", bootstyle="success", width=22, command=self.add_book_popup).pack(pady=8)
        tb.Button(frm, text="Delete Book", bootstyle="danger", width=22, command=self.delete_book_popup).pack(pady=8)
        tb.Button(frm, text="Modify Book", bootstyle="info", width=22, command=self.modify_book_popup).pack(pady=8)
        tb.Button(frm, text="Search Books", bootstyle="secondary", width=22, command=self.management_search).pack(pady=8)
        tb.Button(frm, text="Show All Books", bootstyle="light", width=22, command=self.show_all_books).pack(pady=8)
        tb.Button(frm, text="🔙 Back", bootstyle="secondary", width=18, command=self.create_main_menu).pack(pady=18)

    # ...existing code...
    def add_book_popup(self):
        popup = tb.Toplevel(self.root)
        popup.title("Add Book")
        popup.geometry(f"{POPUP_W}x{POPUP_H}")
        popup.resizable(False, False)
        frm = tb.Frame(popup, padding=18)
        frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Add Book", font=HEADER_FONT).pack(pady=(0,12))
        tb.Label(frm, text="Title", font=LABEL_FONT).pack(anchor="w")
        title_e = tb.Entry(frm); title_e.pack(fill="x", pady=(0,8)); title_e.configure(font=("Segoe UI",12))
        tb.Label(frm, text="Author", font=LABEL_FONT).pack(anchor="w")
        author_e = tb.Entry(frm); author_e.pack(fill="x", pady=(0,8)); author_e.configure(font=("Segoe UI",12))

        # Type entry with trace so we can hide/show the location field
        tb.Label(frm, text="Type ('pdf' or 'url')", font=LABEL_FONT).pack(anchor="w")
        type_var = tb.StringVar(value="pdf")
        type_e = tb.Entry(frm, textvariable=type_var); type_e.pack(fill="x", pady=(0,12)); type_e.configure(font=("Segoe UI",12))

        # Instruction: for PDFs, file should be placed in the script folder (no filepath required)
        tb.Label(frm, text="For PDFs: place the .pdf file in the script folder. Filepath is optional.", font=("Segoe UI", 9)).pack(anchor="w", pady=(0,6))

        # Location/frame (hidden for 'pdf' by default)
        loc_frame = tb.Frame(frm)
        tb.Label(loc_frame, text="PDF filepath or URL (optional)", font=LABEL_FONT).pack(anchor="w")
        loc_e = tb.Entry(loc_frame); loc_e.pack(fill="x", pady=(0,12)); loc_e.configure(font=("Segoe UI",12))

        def on_type_change(*_):
            t = (type_var.get() or "").strip().lower()
            if t == "pdf":
                # hide explicit location entry (optional) — user can still paste a path if desired later
                try:
                    loc_frame.pack_forget()
                except Exception:
                    pass
            else:
                # show location for URLs or non-pdf types
                try:
                    loc_frame.pack(fill="x", pady=(0,12))
                except Exception:
                    pass

        type_var.trace_add("write", on_type_change)
        # initialize
        on_type_change()

        def do_add():
            # reload the excel fresh to avoid closure/local variable issues
            pdf_df, ebook_df = load_excel()
            title = (title_e.get() or "").strip()
            author = (author_e.get() or "").strip()
            typ = (type_var.get() or "").strip().lower()
            loc = (loc_e.get() or "").strip()
            if not title or not author or not typ:
                messagebox.showwarning("Input", "Please fill title, author and type.")
                return
            if typ == "pdf":
                if 'title' not in pdf_df.columns: pdf_df['title'] = []
                if 'author' not in pdf_df.columns: pdf_df['author'] = []
                if 'filepath' not in pdf_df.columns: pdf_df['filepath'] = []
                # if user didn't provide a filepath, leave it blank — app will search script folder by title when opening
                new = pd.DataFrame([[title, author, loc]], columns=['title','author','filepath'])
                pdf_df = pd.concat([pdf_df, new], ignore_index=True)
            else:
                if 'title' not in ebook_df.columns: ebook_df['title'] = []
                if 'author' not in ebook_df.columns: ebook_df['author'] = []
                if 'url' not in ebook_df.columns: ebook_df['url'] = []
                new = pd.DataFrame([[title, author, loc]], columns=['title','author','url'])
                ebook_df = pd.concat([ebook_df, new], ignore_index=True)
            save_excel(pdf_df, ebook_df)
            popup.destroy()

        btns = tb.Frame(frm)
        btns.pack(fill="x", pady=(6,0))
        tb.Button(btns, text="Add Book", bootstyle="success", width=BTN_WIDTH, command=do_add).pack(side="left", padx=6)
        tb.Button(btns, text="Cancel", bootstyle="secondary", width=BTN_WIDTH, command=popup.destroy).pack(side="right", padx=6)

    def delete_book_popup(self):
        popup = tb.Toplevel(self.root)
        popup.title("Delete Book")
        popup.geometry(f"{POPUP_W}x420")
        popup.resizable(False, False)
        frm = tb.Frame(popup, padding=18)
        frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Delete Book", font=HEADER_FONT).pack(pady=(0,12))
        tb.Label(frm, text="Enter exact Title to delete", font=LABEL_FONT).pack(anchor="w")
        t_e = tb.Entry(frm); t_e.pack(fill="x", pady=(0,12)); t_e.configure(font=("Segoe UI",12))

        def do_delete():
            title = (t_e.get() or "").strip()
            if not title:
                messagebox.showwarning("Input", "Please enter title.")
                return
            pdf_df2, ebook_df2 = load_excel()
            # guard if columns absent
            if 'title' in pdf_df2.columns:
                pdf_df2 = pdf_df2[~(pdf_df2.get('title','').astype(str).str.lower() == title.lower())]
            if 'title' in ebook_df2.columns:
                ebook_df2 = ebook_df2[~(ebook_df2.get('title','').astype(str).str.lower() == title.lower())]
            save_excel(pdf_df2, ebook_df2)
            popup.destroy()

        btns = tb.Frame(frm)
        btns.pack(fill="x", pady=(6,0))
        tb.Button(btns, text="Delete", bootstyle="danger", width=BTN_WIDTH, command=do_delete).pack(side="left", padx=6)
        tb.Button(btns, text="Cancel", bootstyle="secondary", width=BTN_WIDTH, command=popup.destroy).pack(side="right", padx=6)

    def modify_book_popup(self):
        popup = tb.Toplevel(self.root)
        popup.title("Modify Book - Choose & Edit")
        popup.geometry(f"{POPUP_W}x{POPUP_H}")
        popup.resizable(False, False)
        frm = tb.Frame(popup, padding=18); frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Modify Book - Choose & Edit", font=HEADER_FONT).pack(pady=(0,12))
        tb.Label(frm, text="Existing Title", font=LABEL_FONT).pack(anchor="w")
        old_e = tb.Entry(frm); old_e.pack(fill="x", pady=(0,8)); old_e.configure(font=("Segoe UI",12))
        tb.Label(frm, text="New Title (leave blank to keep)", font=LABEL_FONT).pack(anchor="w")
        new_t_e = tb.Entry(frm); new_t_e.pack(fill="x", pady=(0,8)); new_t_e.configure(font=("Segoe UI",12))
        tb.Label(frm, text="New Author (leave blank to keep)", font=LABEL_FONT).pack(anchor="w")
        new_a_e = tb.Entry(frm); new_a_e.pack(fill="x", pady=(0,12)); new_a_e.configure(font=("Segoe UI",12))

        def do_modify():
            old_title = (old_e.get() or "").strip()
            if not old_title:
                messagebox.showwarning("Input", "Existing title required.")
                return
            new_title = (new_t_e.get() or "").strip()
            new_author = (new_a_e.get() or "").strip()
            pdf_df2, ebook_df2 = load_excel()
            modified = False
            if 'title' in pdf_df2.columns:
                mask = pdf_df2['title'].astype(str).str.lower() == old_title.lower()
                if mask.any():
                    if new_title: pdf_df2.loc[mask, 'title'] = new_title
                    if new_author: pdf_df2.loc[mask, 'author'] = new_author
                    modified = True
            if 'title' in ebook_df2.columns:
                mask2 = ebook_df2['title'].astype(str).str.lower() == old_title.lower()
                if mask2.any():
                    if new_title: ebook_df2.loc[mask2, 'title'] = new_title
                    if new_author: ebook_df2.loc[mask2, 'author'] = new_author
                    modified = True
            if modified:
                save_excel(pdf_df2, ebook_df2)
                messagebox.showinfo("Success", "Book updated.")
                popup.destroy()
            else:
                messagebox.showwarning("Not found", "No book found with that title.")

        btns = tb.Frame(frm)
        btns.pack(fill="x", pady=(6,0))
        tb.Button(btns, text="Update", bootstyle="primary", width=BTN_WIDTH, command=do_modify).pack(side="left", padx=6)
        tb.Button(btns, text="Cancel", bootstyle="secondary", width=BTN_WIDTH, command=popup.destroy).pack(side="right", padx=6)

    def management_search(self):
        pdf_df, ebook_df = load_excel()
        if pdf_df.empty and ebook_df.empty:
            messagebox.showinfo("No books", "No books in Excel.")
            return
        if not pdf_df.empty: pdf_df['source'] = 'pdf'
        if not ebook_df.empty: ebook_df['source'] = 'ebook'
        combined = pd.concat([pdf_df, ebook_df], ignore_index=True, sort=False)
        data_list = []
        for _, r in combined.iterrows():
            data_list.append({k:(None if pd.isna(v) else v) for k,v in r.items()})
        def on_select(chosen):
            title = chosen.get('title') or ""
            author = chosen.get('author') or ""
            typ = chosen.get('source') or ""
            loc = chosen.get('filepath') or chosen.get('url') or ""
            messagebox.showinfo("Book Selected", f"Title: {title}\nAuthor: {author}\nType: {typ}\nLocation: {loc}")
        open_search_window(self.root, data_list, title="Management: Search Books", on_select=on_select)

    # ...existing code...
    def show_all_books(self):
        pdf_df, ebook_df = load_excel()
        lines = []
        if not pdf_df.empty:
            lines.append("📘 Book PDFs:")
            for i, row in pdf_df.iterrows():
                title = row.get('title') or ""
                author = row.get('author') or ""
                path = row.get('filepath') or row.get('path') or ""
                lines.append(f"{i+1}. {title} — {author}" + (f" ({path})" if path else ""))
            lines.append("")  # blank line between sections
        if not ebook_df.empty:
            lines.append("🌐 E-Books:")
            for i, row in ebook_df.iterrows():
                title = row.get('title') or ""
                author = row.get('author') or ""
                url = row.get('url') or ""
                lines.append(f"{i+1}. {title} — {author}" + (f" ({url})" if url else ""))
        out = "\n".join(lines) if lines else "No books found."
        messagebox.showinfo("All Books", out)
# ...existing code...

    # ---------- customer ----------
    def customer_entry(self):
        popup = tb.Toplevel(self.root)
        popup.title("Customer - Register / Login")
        popup.geometry(f"{POPUP_W}x{POPUP_H}")
        popup.resizable(False, False)
        frm = tb.Frame(popup, padding=18); frm.pack(fill="both", expand=True)
        tb.Label(frm, text="Customer Portal", font=HEADER_FONT).pack(pady=(0,12))
        tb.Label(frm, text="Username", font=LABEL_FONT).pack(anchor="w")
        user_e = tb.Entry(frm); user_e.pack(fill="x", pady=(0,8)); user_e.configure(font=("Segoe UI",12))
        tb.Label(frm, text="Password", font=LABEL_FONT).pack(anchor="w")
        pwd_e = tb.Entry(frm, show="*"); pwd_e.pack(fill="x", pady=(0,12)); pwd_e.configure(font=("Segoe UI",12))

        def do_register():
            user = (user_e.get() or "").strip()
            pwd = (pwd_e.get() or "").strip()
            if not user or not pwd:
                messagebox.showwarning("Input", "Provide username and password.")
                return
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            try:
                hashed = hash_password(pwd)
                c.execute("INSERT INTO users (username, password) VALUES (?,?)", (user, hashed))
                conn.commit()
                messagebox.showinfo("Registered", "Registration successful. Please login.")
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Username exists.")
            finally:
                conn.close()

        def do_login():
            user = (user_e.get() or "").strip()
            pwd = (pwd_e.get() or "").strip()
            if not user or not pwd:
                messagebox.showwarning("Input", "Provide username and password.")
                return
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            try:
                c.execute("SELECT password FROM users WHERE username=?", (user,))
                row = c.fetchone()
                if not row:
                    messagebox.showerror("Error", "Invalid credentials.")
                    return
                stored = row[0] or ""
                hashed_input = hash_password(pwd)
                # If stored value length is 64 assume it's already a SHA-256 hash
                if len(stored) == 64:
                    ok = stored == hashed_input
                else:
                    # fallback: compare plaintext (for legacy DBs); then upgrade by storing hash
                    ok = stored == pwd
                    if ok:
                        c.execute("UPDATE users SET password=? WHERE username=?", (hashed_input, user))
                        conn.commit()
                if ok:
                    self.current_user = user
                    self.cleanup_expired_issues_for_user(user)
                    messagebox.showinfo("Welcome", f"Welcome {user}!")
                    popup.destroy()
                    self.customer_dashboard()
                else:
                    messagebox.showerror("Error", "Invalid credentials.")
            finally:
                conn.close()

        btns = tb.Frame(frm); btns.pack(fill="x", pady=(6,0))
        tb.Button(btns, text="Register", bootstyle="success", width=BTN_WIDTH, command=do_register).pack(side="left", padx=6)
        tb.Button(btns, text="Login", bootstyle="primary", width=BTN_WIDTH, command=do_login).pack(side="left", padx=6)
        tb.Button(btns, text="Back", bootstyle="secondary", width=BTN_WIDTH, command=popup.destroy).pack(side="right", padx=6)

    def customer_dashboard(self):
        for w in self.root.winfo_children():
            w.destroy()
        frm = tb.Frame(self.root, padding=18); frm.pack(fill="both", expand=True)
        tb.Label(frm, text=f"Welcome, {self.current_user}", font=HEADER_FONT).pack(pady=(0,12))
        tb.Button(frm, text="Search / Read / Issue / Buy Books", bootstyle="primary", width=36, command=self.customer_read_book).pack(pady=8)
        tb.Button(frm, text="My Issued / Purchased", bootstyle="info", width=36, command=self.view_my_books).pack(pady=8)
        tb.Button(frm, text="🔙 Logout", bootstyle="secondary", width=18, command=self.logout).pack(pady=18)

    def logout(self):
        self.current_user = None
        self.create_main_menu()

    def cleanup_expired_issues_on_startup(self):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        try:
            now_iso = datetime.now().isoformat()
            c.execute("DELETE FROM issued_books WHERE expiry_date <= ?", (now_iso,))
            conn.commit()
        finally:
            conn.close()

    def cleanup_expired_issues_for_user(self, username):
        # Remove expired issues for everyone (keeps logic same as original) but we could restrict to username if desired
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        try:
            now_iso = datetime.now().isoformat()
            c.execute("DELETE FROM issued_books WHERE expiry_date <= ?", (now_iso,))
            conn.commit()
        finally:
            conn.close()

    # ---------- Read / Issue / Buy ----------
    def customer_read_book(self):
        pdf_df, ebook_df = load_excel()
        pdf_df.columns = [c.lower().strip() for c in pdf_df.columns] if not pdf_df.empty else pdf_df.columns
        ebook_df.columns = [c.lower().strip() for c in ebook_df.columns] if not ebook_df.empty else ebook_df.columns
        if not pdf_df.empty: pdf_df['source'] = 'pdf'
        if not ebook_df.empty: ebook_df['source'] = 'ebook'
        combined = pd.concat([pdf_df, ebook_df], ignore_index=True, sort=False) if (not pdf_df.empty or not ebook_df.empty) else pd.DataFrame()
        if combined.empty:
            messagebox.showinfo("No books", "No books available.")
            return
        display_list = []
        for _, r in combined.iterrows():
            display_list.append({k:(None if pd.isna(v) else v) for k,v in r.items()})

        win = tb.Toplevel(self.root)
        win.title("Read / Issue / Buy")
        win.geometry(f"{POPUP_W}x{POPUP_H}")
        win.resizable(False, False)
        topf = tb.Frame(win, padding=12); topf.pack(fill="x")
        tb.Label(topf, text="Search by Title:", font=HEADER_FONT).pack(anchor="w")
        search_var = tb.StringVar()
        search_entry = tb.Entry(win, textvariable=search_var)
        search_entry.pack(fill="x", padx=12, pady=(6,8))
        list_frame = tb.Frame(win); list_frame.pack(fill="both", expand=True, padx=12, pady=(0,8))
        sbar = tk.Scrollbar(list_frame, orient="vertical"); sbar.pack(side="right", fill="y")
        lbox = tk.Listbox(list_frame, yscrollcommand=sbar.set, font=("Segoe UI", 11)); lbox.pack(side="left", fill="both", expand=True)
        sbar.config(command=lbox.yview)


        # ...existing code...
        # keep track of the currently shown (rendered) items so selection maps correctly
        shown = []

        def render(data):
            nonlocal shown
            shown.clear()
            lbox.delete(0, "end")
            for i, rd in enumerate(data):
                shown.append(rd)
                t = str(rd.get('title') or "")
                a = str(rd.get('author') or "")
                typ = "PDF" if rd.get('source') == 'pdf' else "Online"
                lbox.insert("end", f"{i}: {t} — {a}  ({typ})")

        render(display_list)

        def filter_reorder(_=None):
            q = (search_var.get() or "").strip().lower()
            if not q:
                render(display_list); return
            matched = [rd for rd in display_list if q in str(rd.get('title') or "").lower()]
            others = [rd for rd in display_list if rd not in matched]
            render(matched + others)

        search_entry.bind("<KeyRelease>", filter_reorder)

        def fill_from_select(evt):
            sel = lbox.curselection()
            if not sel:
                return
            idx = sel[0]  # index into the currently shown list
            if 0 <= idx < len(shown):
                search_var.set(str(shown[idx].get('title') or ""))
        lbox.bind("<<ListboxSelect>>", fill_from_select)

        def get_chosen_by_title():
            q = (search_var.get() or "").strip().lower()
            if not q:
                messagebox.showwarning("Select", "Type or choose a book title in the search box first.")
                return None
            # prefer exact match among currently shown items, then fall back to full list
            for rd in shown:
                if q == str(rd.get('title') or "").strip().lower():
                    return rd
            for rd in display_list:
                if q == str(rd.get('title') or "").strip().lower():
                    return rd
            # then try partial matches (shown first)
            for rd in shown:
                if q in str(rd.get('title') or "").strip().lower():
                    return rd
            for rd in display_list:
                if q in str(rd.get('title') or "").strip().lower():
                    return rd
            messagebox.showerror("Not found", "No book matching the search entry.")
            return None

        # ...existing code...
        def action_read():
            rd = get_chosen_by_title()
            if not rd: return
            if rd.get('source') == 'pdf':
                filepath = ""
                for col in ['filepath','path','file path','file','file_path']:
                    if col in rd and rd.get(col):
                        filepath = str(rd.get(col)).strip()
                        break
                if filepath and os.path.exists(filepath):
                    if not open_pdf_in_chrome(filepath):
                        open_pdf_in_acrobat(filepath)
                    return
                # fallback: search script directory by title only
                title = str(rd.get('title') or "").strip()
                found = find_pdf_in_script_dir_by_title(title)
                if found:
                    if not open_pdf_in_chrome(found):
                        open_pdf_in_acrobat(found)
                    return
                messagebox.showerror("Not found", f"PDF not found:\n{filepath or '(no stored path)'}\nSearched script folder for '{title}'.")
            else:
                url = ""
                for col in ['url','link','website']:
                    if col in rd and rd.get(col):
                        url = str(rd.get(col)).strip(); break
                if url and (url.startswith("http://") or url.startswith("https://")):
                    try_open_url_in_chrome(url)
                else:
                    messagebox.showerror("Invalid URL", f"URL missing or invalid:\n{url}")

        def action_issue():
            rd = get_chosen_by_title()
            if not rd: return
            title = str(rd.get('title') or "").strip(); author = str(rd.get('author') or "").strip()
            source = rd.get('source') or 'pdf'
            location = ""
            for col in ['filepath','path','file path','file','file_path','url','link','website']:
                if col in rd and rd.get(col):
                    location = str(rd.get(col)).strip(); break
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id, expiry_date FROM issued_books WHERE username=? AND title=?", (self.current_user, title))
            r = c.fetchone(); now = datetime.now()
            if r:
                try: expiry = datetime.fromisoformat(r[1])
                except: expiry = None
                if expiry and expiry > now:
                    messagebox.showinfo("Already issued", f"You already issued '{title}' until {expiry.date()}.")
                    conn.close(); return
                else:
                    c.execute("DELETE FROM issued_books WHERE id=?", (r[0],)); conn.commit()
            issue_date = now; expiry_date = now + timedelta(days=10)
            c.execute("""INSERT INTO issued_books (username, title, author, source, location, issue_date, expiry_date)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""", (self.current_user, title, author, source, location, issue_date.isoformat(), expiry_date.isoformat()))
            conn.commit(); conn.close()
            messagebox.showinfo("Issued", f"'{title}' issued for 10 days until {expiry_date.date()}.")

        def action_buy():
            rd = get_chosen_by_title()
            if not rd: return
            title = str(rd.get('title') or "").strip(); author = str(rd.get('author') or "").strip()
            source = rd.get('source') or 'pdf'
            location = ""
            for col in ['filepath','path','file path','file','file_path','url','link','website']:
                if col in rd and rd.get(col):
                    location = str(rd.get(col)).strip(); break
            confirm = messagebox.askyesno("Confirm Payment", f"Buy '{title}' for ₹100?")
            if not confirm: return
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("""INSERT INTO purchased_books (username, title, author, source, location, purchase_date, price)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""", (self.current_user, title, author, source, location, datetime.now().isoformat(), 100.0))
            conn.commit(); conn.close()
            messagebox.showinfo("Payment Success", f"You purchased '{title}'.")
            if source == 'pdf' and location:
                downloads = get_downloads_folder()
                try:
                    if os.path.exists(location):
                        dst_name = sanitize_filename(title) + ".pdf"
                        dst_path = os.path.join(downloads, dst_name)
                        shutil.copy2(location, dst_path)
                        messagebox.showinfo("Downloaded", f"✅ Book downloaded to:\n{dst_path}")
                    else:
                        messagebox.showerror("File missing", f"PDF path not found:\n{location}")
                except Exception as e:
                    messagebox.showerror("Download error", str(e))

        actf = tb.Frame(win); actf.pack(pady=8)
        tb.Button(actf, text="Read Selected", bootstyle="primary", width=BTN_WIDTH, command=action_read).grid(row=0, column=0, padx=6)
        tb.Button(actf, text="Issue Selected", bootstyle="info", width=BTN_WIDTH, command=action_issue).grid(row=0, column=1, padx=6)
        tb.Button(actf, text="Buy Selected (₹100)", bootstyle="success", width=BTN_WIDTH, command=action_buy).grid(row=0, column=2, padx=6)
        tb.Button(actf, text="Close", bootstyle="secondary", width=BTN_WIDTH, command=win.destroy).grid(row=0, column=3, padx=6)

    # ---------- My Issued / Purchased ----------
    def view_my_books(self):
        self.cleanup_expired_issues_for_user(self.current_user)
        win = tb.Toplevel(self.root)
        win.title("My Issued / Purchased")
        win.geometry(f"{POPUP_W}x{POPUP_H}")
        win.resizable(False, False)
        frm = tb.Frame(win, padding=12); frm.pack(fill="both", expand=True)
        tb.Label(frm, text=f"My books — {self.current_user}", font=HEADER_FONT).pack(pady=(0,10))

        # --- Modified layout: use grid with equal-weight columns so Issued and Purchased get equal width ---
        content_frame = tb.Frame(frm)
        # pack content_frame first so it expands vertically; bottom button frame will be packed afterwards
        content_frame.pack(fill="both", expand=True, padx=4, pady=(4,0))

        # configure equal weights so left and right expand equally
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)

        left = tb.Frame(content_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)

        right = tb.Frame(content_frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)

        tb.Label(left, text="Issued (active)", font=LABEL_FONT).pack(anchor="n")
        lb_issued = tk.Listbox(left, width=50, height=20); lb_issued.pack(fill="both", expand=True, padx=4, pady=(6,4))

        tb.Label(right, text="Purchased", font=LABEL_FONT).pack(anchor="n")
        lb_purchased = tk.Listbox(right, width=50, height=20); lb_purchased.pack(fill="both", expand=True, padx=4, pady=(6,4))

        # load data from DB
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT id, title, author, source, location, issue_date, expiry_date FROM issued_books WHERE username=?", (self.current_user,))
        issued_rows = c.fetchall()
        c.execute("SELECT id, title, author, source, location, purchase_date, price FROM purchased_books WHERE username=?", (self.current_user,))
        purchased_rows = c.fetchall()
        conn.close()

        issued_map = {}; purchased_map = {}
        for r in issued_rows:
            _id, title, author, source, location, issue_date, expiry_date = r
            try: expiry_dt = datetime.fromisoformat(expiry_date)
            except: expiry_dt = None
            label = f"{title} — {author} (until {expiry_dt.date() if expiry_dt else expiry_date})"
            lb_issued.insert("end", label)
            issued_map[label] = {'id':_id,'title':title,'author':author,'source':source,'location':location}
        for r in purchased_rows:
            _id, title, author, source, location, purchase_date, price = r
            label = f"{title} — {author} (bought)"
            lb_purchased.insert("end", label)
            purchased_map[label] = {'id':_id,'title':title,'author':author,'source':source,'location':location}

        def open_issued():
            sel = lb_issued.curselection()
            if not sel:
                messagebox.showwarning("Select", "Select an issued book.")
                return
            label = lb_issued.get(sel[0]); info = issued_map.get(label)
            if not info:
                messagebox.showerror("Error", "Info missing."); return
            if info['source'] == 'pdf':
                loc = info.get('location') or ""
                if loc and os.path.exists(loc):
                    if not open_pdf_in_chrome(loc):
                        open_pdf_in_acrobat(loc)
                    return
                # fallback: search script directory by title only
                found = find_pdf_in_script_dir_by_title(info.get('title'))
                if found:
                    if not open_pdf_in_chrome(found):
                        open_pdf_in_acrobat(found)
                    return
                messagebox.showerror("Missing", f"PDF not found for '{info.get('title')}'.\nSearched stored path and script folder.")
            else:
                if info.get('location') and (info['location'].startswith("http://") or info['location'].startswith("https://")):
                    try_open_url_in_chrome(info['location'])
                else:
                    messagebox.showerror("Missing", "URL missing/invalid.")

        
        def return_issued():
            sel = lb_issued.curselection()
            if not sel: messagebox.showwarning("Select", "Select an issued book to return."); return
            label = lb_issued.get(sel[0]); info = issued_map.get(label)
            if not info: messagebox.showerror("Error", "Info missing."); return
            conn = sqlite3.connect(DB_PATH); c = conn.cursor(); c.execute("DELETE FROM issued_books WHERE id=?", (info['id'],)); conn.commit(); conn.close()
            messagebox.showinfo("Returned", f"'{info['title']}' returned successfully."); lb_issued.delete(sel[0])


        def open_purchased():
            sel = lb_purchased.curselection()
            if not sel:
                messagebox.showwarning("Select", "Select a purchased book.")
                return
            label = lb_purchased.get(sel[0]); info = purchased_map.get(label)
            if not info:
                messagebox.showerror("Error", "Info missing."); return
            if info['source'] == 'pdf':
                loc = info.get('location') or ""
                if loc and os.path.exists(loc):
                    if not open_pdf_in_chrome(loc):
                        open_pdf_in_acrobat(loc)
                    return
                # try Downloads by sanitized title
                downloads = get_downloads_folder()
                candidate = os.path.join(downloads, f"{sanitize_filename(info.get('title'))}.pdf")
                if os.path.exists(candidate):
                    if not open_pdf_in_chrome(candidate):
                        open_pdf_in_acrobat(candidate)
                    return
                # final fallback: search script folder by title
                found = find_pdf_in_script_dir_by_title(info.get('title'))
                if found:
                    if not open_pdf_in_chrome(found):
                        open_pdf_in_acrobat(found)
                    return
                messagebox.showerror("Missing", f"PDF not found for '{info.get('title')}'.")
            else:
                if info.get('location') and (info['location'].startswith("http://") or info['location'].startswith("https://")):
                    try_open_url_in_chrome(info['location'])
                else:
                    messagebox.showerror("Missing", "URL missing/invalid.")

        def download_purchased():
            sel = lb_purchased.curselection()
            if not sel:
                messagebox.showwarning("Select", "Select a purchased book."); return
            label = lb_purchased.get(sel[0]); info = purchased_map.get(label)
            if not info:
                messagebox.showerror("Error", "Info missing."); return
            if info.get('source') != 'pdf':
                messagebox.showinfo("Not Available", "This item is not a downloadable PDF."); return

            title = str(info.get('title') or "book").strip()
            src = (info.get('location') or "").strip()
            downloads = get_downloads_folder()
            try:
                os.makedirs(downloads, exist_ok=True)
            except Exception:
                pass
            dst = os.path.join(downloads, f"{sanitize_filename(title)}.pdf")

            tried = []
            try:
                # 1) Try stored path (absolute or relative to script dir)
                if src:
                    candidate = os.path.expanduser(src)
                    if not os.path.isabs(candidate):
                        base = os.path.dirname(__file__) or os.getcwd()
                        candidate = os.path.join(base, candidate)
                    tried.append(candidate)
                    if os.path.exists(candidate) and os.path.isfile(candidate):
                        shutil.copy2(candidate, dst)
                        messagebox.showinfo("Downloaded", f"✅ Book downloaded to:\n{dst}")
                        return

                # 2) If src is a URL, attempt to download it
                if src and (src.startswith("http://") or src.startswith("https://")):
                    try:
                        urllib.request.urlretrieve(src, dst)
                        messagebox.showinfo("Downloaded", f"✅ Book downloaded to:\n{dst}")
                        return
                    except Exception as e:
                        tried.append(src)

                # 3) Fallback: search script directory by title (best-effort)
                found = find_pdf_in_script_dir_by_title(title)
                if found:
                    shutil.copy2(found, dst)
                    messagebox.showinfo("Downloaded", f"✅ Book downloaded to:\n{dst}")
                    return

                # Nothing worked
                details = "\n".join(tried) if tried else "(no candidate paths)"
                messagebox.showerror("Missing", f"Could not locate original PDF for '{title}'.\nTried:\n{details}")
            except Exception as e:
                messagebox.showerror("Error", f"Download failed:\n{e}")

        # bottom button frame (packed AFTER content_frame so it appears under the lists)
        # ...existing code...
        # bottom button frame (packed AFTER content_frame so it appears under the lists)
        bframe = tb.Frame(frm)
        bframe.pack(fill="x", pady=(6,4), padx=6)
        tb.Button(bframe, text="Read Issued", bootstyle="primary", width=BTN_WIDTH, command=open_issued).grid(row=0,column=0,padx=6)
        tb.Button(bframe, text="Return Issued", bootstyle="secondary", width=BTN_WIDTH, command=return_issued).grid(row=0,column=1,padx=6)
        tb.Button(bframe, text="Read Purchased", bootstyle="primary", width=BTN_WIDTH, command=open_purchased).grid(row=0,column=2,padx=6)
        tb.Button(bframe, text="Download Purchased", bootstyle="success", width=BTN_WIDTH, command=download_purchased).grid(row=0,column=3,padx=6)
        tb.Button(bframe, text="Close", bootstyle="light", width=BTN_WIDTH, command=win.destroy).grid(row=0,column=4,padx=6)

    # ---------- run ----------
    def run(self):
        self.root.mainloop()

# ---------- main ----------
if __name__ == "__main__":
    app = LibraryApp()
    app.run()
