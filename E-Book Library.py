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
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *

# ---------- CONFIG ----------
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Books.xlsx")
SHEET_BOOK_PDF = "Book PDF"
SHEET_EBOOK = "E-Book"
DB_PATH = "library_users.db"

# ---------- UI constants ----------
WIN_GEOM = "900x640"
POPUP_W = 620
POPUP_H = 520
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
    name = (name or "").strip()
    name = re.sub(r'[\/\\\:\*\?"<>\|]', "", name)
    name = re.sub(r'\s+', ' ', name)
    if len(name) > 150:
        name = name[:150]
    return name

def open_pdf_in_acrobat(filepath):
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        messagebox.showerror("Error", f"File not found:\n{filepath}")
        return
    try:
        if sys.platform.startswith("win"):
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
            os.startfile(filepath)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open PDF:\n{e}")

def try_open_url_in_chrome(url):
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
        chrome_candidates = ["google-chrome", "chrome", "chromium", "chromium-browser"]
    for p in chrome_candidates:
        try:
            if os.path.isabs(p) and os.path.exists(p):
                subprocess.Popen([p, url], shell=False)
                return
            else:
                subprocess.Popen([p, url], shell=False)
                return
        except Exception:
            continue
    webbrowser.open(url)

def ensure_excel_exists():
    if not os.path.exists(EXCEL_PATH):
        pdf_df = pd.DataFrame(columns=["title", "author", "filepath"])
        ebook_df = pd.DataFrame(columns=["title", "author", "url"])
        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            pdf_df.to_excel(writer, index=False, sheet_name=SHEET_BOOK_PDF)
            ebook_df.to_excel(writer, index=False, sheet_name=SHEET_EBOOK)

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
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()

def load_excel():
    if not os.path.exists(EXCEL_PATH):
        return pd.DataFrame(), pd.DataFrame()
    xls = pd.ExcelFile(EXCEL_PATH)
    pdf_df = pd.read_excel(xls, sheet_name=SHEET_BOOK_PDF)
    ebook_df = pd.read_excel(xls, sheet_name=SHEET_EBOOK)
    pdf_df.columns = [c.lower().strip() for c in pdf_df.columns]
    ebook_df.columns = [c.lower().strip() for c in ebook_df.columns]
    return pdf_df, ebook_df

def save_excel(pdf_df, ebook_df):
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl", mode="w") as writer:
        pdf_df.to_excel(writer, index=False, sheet_name=SHEET_BOOK_PDF)
        ebook_df.to_excel(writer, index=False, sheet_name=SHEET_EBOOK)

# ---------- App ----------
class LibraryApp:
    def __init__(self):
        ensure_excel_exists()
        init_db()
        self.root = tb.Window(themename="darkly")
        self.root.title("E-Book Library System")
        self.root.geometry(WIN_GEOM)
        self.root.resizable(False, False)
        self.current_user = None
        self.cleanup_expired_issues_on_startup()
        self.create_main_menu()

    def run(self):
        self.root.mainloop()

    def create_main_menu(self):
        for w in self.root.winfo_children():
            w.destroy()
        frame = tb.Frame(self.root, padding=26)
        frame.pack(fill="both", expand=True)
        tb.Label(frame, text="📚 E-Book Library System", font=("Segoe UI", 24, "bold")).pack(pady=(8, 18))
        tb.Button(frame, text="Management", bootstyle="info", width=24, command=self.management_menu).pack(pady=10)
        tb.Button(frame, text="Customer", bootstyle="primary", width=24, command=self.customer_menu).pack(pady=10)
        tb.Button(frame, text="Exit", bootstyle="danger", width=24, command=self.root.destroy).pack(pady=30)

    # ---------- MANAGEMENT ----------
    def management_menu(self):
        win = tb.Toplevel(self.root)
        win.title("Management Menu")
        win.geometry(f"{POPUP_W}x{POPUP_H}")
        tb.Label(win, text="Management Options", font=HEADER_FONT).pack(pady=10)
        tb.Button(win, text="Add Book", width=BTN_WIDTH, command=self.add_book).pack(pady=5)
        tb.Button(win, text="Delete Book", width=BTN_WIDTH, command=self.delete_book).pack(pady=5)
        tb.Button(win, text="Search Book", width=BTN_WIDTH, command=self.search_book).pack(pady=5)
        tb.Button(win, text="Show All Books", width=BTN_WIDTH, command=self.show_all_books).pack(pady=5)
        tb.Button(win, text="Close", bootstyle="danger", width=BTN_WIDTH, command=win.destroy).pack(pady=15)

    def add_book(self):
        win = tb.Toplevel(self.root)
        win.title("Add Book")
        win.geometry("520x420")
        tb.Label(win, text="Add Book", font=HEADER_FONT).pack(pady=10)
        tb.Label(win, text="Type:").pack()
        type_var = tb.StringVar(value="pdf")
        tb.Radiobutton(win, text="PDF", variable=type_var, value="pdf").pack()
        tb.Radiobutton(win, text="E-Book", variable=type_var, value="ebook").pack()
        tb.Label(win, text="Title:").pack()
        title_entry = tb.Entry(win)
        title_entry.pack()
        tb.Label(win, text="Author:").pack()
        author_entry = tb.Entry(win)
        author_entry.pack()
        tb.Label(win, text="Filepath or URL:").pack()
        loc_entry = tb.Entry(win)
        loc_entry.pack()

        def save_book():
            title, author, loc = title_entry.get().strip(), author_entry.get().strip(), loc_entry.get().strip()
            if not title or not author or not loc:
                messagebox.showerror("Error", "All fields are required.")
                return
            pdf_df, ebook_df = load_excel()
            if type_var.get() == "pdf":
                pdf_df.loc[len(pdf_df)] = [title, author, loc]
            else:
                ebook_df.loc[len(ebook_df)] = [title, author, loc]
            save_excel(pdf_df, ebook_df)
            messagebox.showinfo("Success", "Book added successfully.")
            win.destroy()

        tb.Button(win, text="Save", bootstyle="success", command=save_book).pack(pady=15)

    def delete_book(self):
        pdf_df, ebook_df = load_excel()
        win = tb.Toplevel(self.root)
        win.title("Delete Book")
        win.geometry("400x300")
        tb.Label(win, text="Enter Title to Delete:", font=LABEL_FONT).pack(pady=10)
        title_var = tb.StringVar()
        tb.Entry(win, textvariable=title_var).pack(pady=5)

        def confirm_delete():
            title = normalize_text(title_var.get())
            pdf_df2 = pdf_df[~pdf_df["title"].apply(normalize_text).str.contains(title, na=False)]
            ebook_df2 = ebook_df[~ebook_df["title"].apply(normalize_text).str.contains(title, na=False)]
            save_excel(pdf_df2, ebook_df2)
            messagebox.showinfo("Deleted", "Book deleted (if existed).")
            win.destroy()

        tb.Button(win, text="Delete", bootstyle="danger", command=confirm_delete).pack(pady=15)

    def search_book(self):
        pdf_df, ebook_df = load_excel()
        win = tb.Toplevel(self.root)
        win.title("Search Book")
        win.geometry("400x350")
        tb.Label(win, text="Search by Title:", font=LABEL_FONT).pack(pady=10)
        q_var = tb.StringVar()
        tb.Entry(win, textvariable=q_var).pack(pady=5)
        text_box = tk.Text(win, wrap="word", height=10)
        text_box.pack(fill="both", expand=True, pady=5)

        def perform_search():
            q = normalize_text(q_var.get())
            pdf_res = pdf_df[pdf_df["title"].apply(lambda x: q in normalize_text(x))]
            ebook_res = ebook_df[ebook_df["title"].apply(lambda x: q in normalize_text(x))]
            out = ""
            if not pdf_res.empty:
                out += "📘 Book PDFs:\n"
                for i, r in pdf_res.iterrows():
                    out += f"{r['title']} — {r['author']}\n"
            if not ebook_res.empty:
                out += "\n🌐 E-Books:\n"
                for i, r in ebook_res.iterrows():
                    out += f"{r['title']} — {r['author']}\n"
            text_box.delete(1.0, "end")
            text_box.insert("end", out or "No match found.")

        tb.Button(win, text="Search", bootstyle="primary", command=perform_search).pack(pady=10)

    # ✅ Modified Show All Books
    def show_all_books(self):
        pdf_df, ebook_df = load_excel()
        out = ""
        if not pdf_df.empty:
            out += "📘 Book PDFs:\n"
            for i, r in pdf_df.iterrows():
                out += f"{i+1}. {r.get('title','')} — {r.get('author','')}\n"
            out += "\n"
        if not ebook_df.empty:
            out += "🌐 E-Books:\n"
            for i, r in ebook_df.iterrows():
                out += f"{i+1}. {r.get('title','')} — {r.get('author','')}\n"
        messagebox.showinfo("All Books", out or "No books found.")


        # ---------- CUSTOMER (continued) ----------
    def customer_menu(self):
        # Popup for Register / Login - matches original behavior
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

        def render(data):
            lbox.delete(0, "end")
            for i, rd in enumerate(data):
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
            if not sel: return
            text = lbox.get(sel[0])
            try: idx = int(text.split(":",1)[0])
            except: idx = sel[0]
            if 0 <= idx < len(display_list):
                search_var.set(str(display_list[idx].get('title') or ""))
        lbox.bind("<<ListboxSelect>>", fill_from_select)

        def get_chosen_by_title():
            q = (search_var.get() or "").strip().lower()
            if not q:
                messagebox.showwarning("Select", "Type or choose a book title in the search box first.")
                return None
            for rd in display_list:
                if q == str(rd.get('title') or "").strip().lower():
                    return rd
            for rd in display_list:
                if q in (str(rd.get('title') or "").strip().lower()):
                    return rd
            messagebox.showerror("Not found", "No book exactly matching the search entry.")
            return None

        def action_read():
            rd = get_chosen_by_title()
            if not rd: return
            if rd.get('source') == 'pdf':
                # === MODIFIED: search only in same directory by title ===
                title = sanitize_filename(str(rd.get('title') or "").strip())
                same_dir = os.path.dirname(__file__)
                filepath = os.path.join(same_dir, f"{title}.pdf")
                if filepath and os.path.exists(filepath):
                    open_pdf_in_acrobat(filepath)
                else:
                    messagebox.showerror("Not found", f"PDF not found in same directory:\n{filepath}")
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

        content_frame = tb.Frame(frm)
        content_frame.pack(fill="both", expand=True, padx=4, pady=(4,0))
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
            if not sel: messagebox.showwarning("Select", "Select an issued book."); return
            label = lb_issued.get(sel[0]); info = issued_map.get(label)
            if not info: messagebox.showerror("Error", "Info missing."); return
            if info['source']=='pdf':
                # read from same directory by title as fallback if stored path missing
                if info['location'] and os.path.exists(info['location']):
                    open_pdf_in_acrobat(info['location'])
                else:
                    candidate = os.path.join(os.path.dirname(__file__), f"{sanitize_filename(info['title'])}.pdf")
                    if os.path.exists(candidate):
                        open_pdf_in_acrobat(candidate)
                    else:
                        messagebox.showerror("Missing", "PDF file not found.")
            else:
                if info['location'] and (info['location'].startswith("http://") or info['location'].startswith("https://")):
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
            if not sel: messagebox.showwarning("Select", "Select a purchased book."); return
            label = lb_purchased.get(sel[0]); info = purchased_map.get(label)
            if not info: messagebox.showerror("Error", "Info missing."); return
            if info['source']=='pdf':
                if info['location'] and os.path.exists(info['location']): open_pdf_in_acrobat(info['location'])
                else:
                    downloads = get_downloads_folder(); candidate = os.path.join(downloads, f"{sanitize_filename(info['title'])}.pdf")
                    if os.path.exists(candidate): open_pdf_in_acrobat(candidate)
                    else:
                        # fallback: check same directory by title
                        candidate2 = os.path.join(os.path.dirname(__file__), f"{sanitize_filename(info['title'])}.pdf")
                        if os.path.exists(candidate2): open_pdf_in_acrobat(candidate2)
                        else: messagebox.showerror("Missing", "PDF not found locally.")
            else:
                if info['location'] and (info['location'].startswith("http://") or info['location'].startswith("https://")): try_open_url_in_chrome(info['location'])
                else: messagebox.showerror("Missing", "URL missing/invalid.")

        def download_purchased():
            sel = lb_purchased.curselection()
            if not sel: messagebox.showwarning("Select", "Select a purchased book."); return
            label = lb_purchased.get(sel[0]); info = purchased_map.get(label)
            if not info: messagebox.showerror("Error", "Info missing."); return
            if info['source']!='pdf': messagebox.showinfo("Not Available", "This item is not a downloadable PDF."); return
            src = info['location']
            if not src or not os.path.exists(src): messagebox.showerror("Missing", "Original PDF path missing."); return
            downloads = get_downloads_folder(); dst = os.path.join(downloads, f"{sanitize_filename(info['title'])}.pdf")
            try: shutil.copy2(src, dst); messagebox.showinfo("Downloaded", f"✅ Book downloaded to:\n{dst}")
            except Exception as e: messagebox.showerror("Error", f"Download failed:\n{e}")

        bframe = tb.Frame(frm)
        bframe.pack(fill="x", pady=(6,4), padx=6)
        tb.Button(bframe, text="Open Issued", bootstyle="primary", width=BTN_WIDTH, command=open_issued).grid(row=0,column=0,padx=6)
        tb.Button(bframe, text="Return Issued", bootstyle="secondary", width=BTN_WIDTH, command=return_issued).grid(row=0,column=1,padx=6)
        tb.Button(bframe, text="Open Purchased", bootstyle="primary", width=BTN_WIDTH, command=open_purchased).grid(row=0,column=2,padx=6)
        tb.Button(bframe, text="Download Purchased", bootstyle="success", width=BTN_WIDTH, command=download_purchased).grid(row=0,column=3,padx=6)
        tb.Button(bframe, text="Close", bootstyle="light", width=BTN_WIDTH, command=win.destroy).grid(row=0,column=4,padx=6)


# ---------- run ----------
if __name__ == "__main__":
    app = LibraryApp()
    app.run()

