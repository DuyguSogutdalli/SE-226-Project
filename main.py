import io
import json
import math
import os
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

import requests
from PIL import Image, ImageTk, ImageDraw
from google import genai

#API Configuration

GEMINI_API_KEY  = " "
LASTFM_API_KEY  = "50141b3f6ee3de00f074dac1a5c2922d"
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"

#Genre visual style hints sent to image generator

GENRE_VISUAL_HINTS = {
    "Pop":          "vibrant colors, glossy aesthetic, pop art style",
    "Rock":         "gritty textures, dark tones, electric energy",
    "Hip-Hop / Rap":"urban streetwear, graffiti, bold typography",
    "Electronic":   "neon lights, digital glitch, futuristic synth-wave",
    "Indie":        "vintage film grain, muted pastels, lo-fi warmth",
    "R&B / Soul":   "moody lighting, velvet textures, rich warm tones",
    "Jazz":         "smoky atmosphere, sepia tones, noir elegance",
    "Metal":        "dark and heavy, skull motifs, fire and metal textures",
    "Türk Pop":     "Mediterranean warmth, cultural patterns, vibrant hues",
    "Klasik":       "ornate classical frames, oil painting style, timeless",
}

# Per-genre neon accent color pairs
GENRE_COLORS = {
    "Pop":          ("#ff6ec7", "#ffb347"),
    "Rock":         ("#ff4444", "#ff8800"),
    "Hip-Hop / Rap":("#a855f7", "#ec4899"),
    "Electronic":   ("#00ffff", "#7c3aed"),
    "Indie":        ("#86efac", "#fde68a"),
    "R&B / Soul":   ("#fb923c", "#f472b6"),
    "Jazz":         ("#fbbf24", "#f87171"),
    "Metal":        ("#94a3b8", "#ef4444"),
    "Türk Pop":     ("#f97316", "#facc15"),
    "Klasik":       ("#d4af37", "#c084fc"),
}

#Design tokens

BG_BASE    = "#080810"
BG_PANEL   = "#0f0f1a"
BG_CARD    = "#13131f"
BG_INPUT   = "#1a1a2e"
BG_ROW_A   = "#111120"
BG_ROW_B   = "#0e0e1c"

NEON_PINK  = "#ff2d78"
NEON_CYAN  = "#00e5ff"
NEON_LIME  = "#39ff14"
NEON_GOLD  = "#ffd700"
WHITE      = "#ffffff"
GRAY_1     = "#e2e2f0"
GRAY_2     = "#9090b0"
GRAY_3     = "#505070"
GRAY_4     = "#252535"

FONT_BODY  = ("Helvetica", 10)
FONT_SMALL = ("Helvetica", 9)
FONT_TINY  = ("Helvetica", 8)
FONT_HEAD  = ("Helvetica", 11, "bold")
FONT_MONO  = ("Courier", 9, "bold")


#  Back-end helpers

def call_gemini(journal_text, genre, era, track_count):
    """Ask Gemini to generate fictional album metadata as JSON."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""You are a creative music director. Based on the user's mood or journal entry below,
create a completely FICTIONAL album concept.

Return ONLY a valid JSON object — no markdown fences, no extra text — with this exact schema:
{{
  "album_name": "string",
  "artist_name": "string",
  "year": "string",
  "label": "string",
  "mood_description": "string (1-2 sentences)",
  "cover_prompt": "string (50-80 word visual prompt for album cover art)",
  "lastfm_tags": ["5-7 lowercase Last.fm tag strings"]
}}

Genre: {genre} | Era: {era} | Tracks: {track_count}

Journal:
\"\"\"{journal_text}\"\"\"
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw = response.text.strip()
    # Strip markdown code fences if Gemini added them
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def fetch_tracks_by_tag(tag, limit=15):
    """Query Last.fm tag.gettoptracks and return a list of track dicts."""
    params = {
        "method": "tag.gettoptracks",
        "tag": tag, "limit": limit,
        "api_key": LASTFM_API_KEY, "format": "json",
    }
    headers = {"User-Agent": "AlbumCoverStudio-PDA226/1.0"}
    resp = requests.get(LASTFM_BASE_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("tracks", {}).get("track", [])


def build_tracklist(tags, target_count):
    """Combine tracks from multiple tags, deduplicate, return exact count."""
    seen, tracks = set(), []
    for tag in tags:
        if len(tracks) >= target_count * 2:
            break
        try:
            raw = fetch_tracks_by_tag(tag, limit=20)
        except Exception:
            continue
        for t in raw:
            title  = t.get("name", "Unknown")
            artist = t.get("artist", {}).get("name", "Unknown")
            url    = t.get("url", "")
            key    = f"{title.lower()}|{artist.lower()}"
            if key not in seen:
                seen.add(key)
                tracks.append({"title": title, "artist": artist, "url": url})
            if len(tracks) >= target_count * 2:
                break
    return tracks[:target_count]


def generate_cover_image(cover_prompt, genre):
    """
    Generate album cover using Pollinations.ai (free, no API key needed).
    Falls back to a colored placeholder if the request fails.
    """
    visual_hint = GENRE_VISUAL_HINTS.get(genre, "artistic album cover")
    full_prompt = f"album cover art, {cover_prompt}, {visual_hint}, high quality, square format"

    try:
        from urllib.parse import quote
        encoded = quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=600&height=600&nologo=true"
        resp = requests.get(url, timeout=90)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        img = Image.new("RGB", (600, 600), color=(20, 20, 40))
        return img

#  Custom Widgets

class NeonButton(tk.Button):
    """Styled tk.Button that mimics a neon bordered button. Simple and reliable."""

    def __init__(self, parent, text, command,
                 color1=NEON_PINK, color2=NEON_CYAN,
                 width=220, height=44,
                 font=("Helvetica", 11, "bold"), **kwargs):
        # Remove canvas-only kwargs that Button does not accept
        kwargs.pop("width", None)
        kwargs.pop("height", None)
        super().__init__(
            parent,
            text=text,
            command=command,
            font=font,
            bg=BG_CARD,
            fg=color1,
            activebackground=color1,
            activeforeground=BG_BASE,
            relief="flat",
            bd=0,
            cursor="hand2",
            highlightthickness=2,
            highlightbackground=color1,
            highlightcolor=color2,
            pady=10,
            **kwargs,
        )
        self._color1  = color1
        self._color2  = color2
        self._enabled = True
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))

    def _hover(self, on: bool):
        if not self._enabled:
            return
        if on:
            self.configure(bg=self._color1, fg=BG_BASE)
        else:
            self.configure(bg=BG_CARD, fg=self._color1)

    def set_enabled(self, val: bool):
        self._enabled = val
        state = tk.NORMAL if val else tk.DISABLED
        self.configure(state=state)
        if val:
            self.configure(bg=BG_CARD, fg=self._color1, cursor="hand2")
        else:
            self.configure(bg=GRAY_4, fg=GRAY_3, cursor="")


class VinylRecord(tk.Canvas):
    """Animated spinning vinyl record with circular album art in the center."""

    def __init__(self, parent, size=260, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=BG_BASE, highlightthickness=0, **kwargs)
        self._size     = size
        self._angle    = 0.0
        self._spinning = False
        self._pil_img  = None
        self._tk_img   = None
        self._draw(self._angle)

    def _cx(self): return self._size // 2
    def _cy(self): return self._size // 2

    def _draw(self, angle_deg=0.0):
        self.delete("all")
        cx, cy = self._cx(), self._cy()
        r = self._size // 2 - 6

        # Vinyl disc
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill="#100800", outline="#2a2a2a", width=2)

        # Groove rings
        for i in range(9, 1, -1):
            rr = int(r * (0.33 + i * 0.077))
            shade = format(20 + i * 5, '02x')
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                             fill="", outline=f"#{shade}{shade}{shade}", width=1)


        # Center circle (album art or placeholder)
        label_r = int(r * 0.85)
        if self._pil_img:
            dia = label_r * 2
            rotated = self._pil_img.rotate(-angle_deg, resample=Image.NEAREST)
            thumb = rotated.resize((dia, dia), Image.LANCZOS)
            mask = Image.new("L", (dia, dia), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, dia, dia), fill=255)
            circ = Image.new("RGBA", (dia, dia))
            circ.paste(thumb, (0, 0))
            circ.putalpha(mask)
            self._tk_img = ImageTk.PhotoImage(circ)
            self.create_image(cx - label_r, cy - label_r,
                              anchor="nw", image=self._tk_img)
        else:
            self.create_oval(cx - label_r, cy - label_r,
                             cx + label_r, cy + label_r,
                             fill=BG_CARD, outline=GRAY_3, width=1)
            self.create_text(cx, cy, text="♫", fill=GRAY_3,
                             font=("Helvetica", 28))

        self.create_line(cx, cy, cx, cy - int(r * 0.85),
                         fill="#ffffff", width=3)

        # Spindle hole

        # Spindle hole
        self.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                         fill=BG_BASE, outline=GRAY_4)

    def set_cover(self, pil_img: Image.Image):
        self._pil_img = pil_img
        self._draw(self._angle)

    def start_spin(self):
        self._spinning = True
        self._tick()

    def stop_spin(self):
        self._spinning = False

    def _tick(self):
        if not self._spinning:
            return
        self._angle = (self._angle + 3.6) % 360
        self._draw(self._angle)
        self.after(40, self._tick)


#  Main Application Window

class AlbumCoverStudio(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Album Cover Studio  ◈  PDA-226")
        self.configure(bg=BG_BASE)
        self.geometry("1220x800")
        self.minsize(1050, 700)

        # App state
        self._album_data  = None
        self._tracklist   = []
        self._cover_image = None
        self._accent1     = NEON_PINK
        self._accent2     = NEON_CYAN

        self._build_bg()
        self._build_layout()

    #Dot-grid background

    def _build_bg(self):
        self._bg = tk.Canvas(self, bg=BG_BASE, highlightthickness=0)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        # Draw a subtle dot grid
        for x in range(0, 1400, 30):
            for y in range(0, 900, 30):
                self._bg.create_oval(x, y, x + 1, y + 1, fill="#18183a", outline="")

    #Two-column layout

    def _build_layout(self):
        wrap = tk.Frame(self, bg=BG_BASE)
        wrap.place(x=0, y=0, relwidth=1, relheight=1)

        self._col_left  = tk.Frame(wrap, bg=BG_BASE, width=400)
        self._col_right = tk.Frame(wrap, bg=BG_BASE)
        self._col_left.pack(side=tk.LEFT, fill=tk.Y, padx=(22, 0), pady=22)
        self._col_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=22, pady=22)
        self._col_left.pack_propagate(False)

        self._build_left()
        self._build_right()

    #Left panel

    def _build_left(self):
        p = self._col_left

        # Logo row
        logo = tk.Frame(p, bg=BG_BASE)
        logo.pack(fill=tk.X)
        tk.Label(logo, text="ALBUM", fg=NEON_PINK, bg=BG_BASE,
                 font=("Georgia", 34, "bold")).pack(side=tk.LEFT)
        tk.Label(logo, text=" COVER", fg=NEON_CYAN, bg=BG_BASE,
                 font=("Georgia", 34, "bold")).pack(side=tk.LEFT)
        tk.Label(p, text="S T U D I O  ◈  PDA-226",
                 fg=GRAY_3, bg=BG_BASE, font=FONT_MONO).pack(anchor="w", pady=(0, 4))

        # Accent line
        tk.Frame(p, bg=NEON_PINK, height=2).pack(fill=tk.X, pady=(4, 18))

        # Mood text area
        self._field_label(p, "YOUR MOOD / RUH HALİN", NEON_PINK)
        journal_border = tk.Frame(p, bg=NEON_PINK, padx=1, pady=1)
        journal_border.pack(fill=tk.X, pady=(4, 14))
        journal_inner = tk.Frame(journal_border, bg=BG_INPUT)
        journal_inner.pack(fill=tk.BOTH)
        self._journal = tk.Text(
            journal_inner, height=7, wrap=tk.WORD,
            bg=BG_INPUT, fg=GRAY_1, insertbackground=NEON_PINK,
            relief="flat", bd=6, font=FONT_BODY,
            selectbackground=NEON_PINK,
        )
        self._journal.pack(fill=tk.BOTH)
        self._journal.insert("1.0",
            "I was looking at the sea in Izmir. It was raining softly, "
            "and an old song was playing through my headphones. "
            "I felt both peaceful and melancholic...")

        # Genre
        self._field_label(p, "GENRE", NEON_CYAN)
        self._genre_var = tk.StringVar(value="Indie")
        self._build_styled_combo(p, self._genre_var,
                                 list(GENRE_VISUAL_HINTS.keys()), NEON_CYAN)

        # Era
        self._field_label(p, "ERA", NEON_CYAN)
        self._era_var = tk.StringVar(value="2010s")
        self._build_styled_combo(p, self._era_var,
                                 ["1970s","1980s","1990s","2000s","2010s","2020s"],
                                 NEON_CYAN)

        # Track count
        self._field_label(p, "TRACK COUNT", NEON_CYAN)
        count_border = tk.Frame(p, bg=NEON_CYAN, padx=1, pady=1)
        count_border.pack(anchor="w", pady=(4, 20))

        self._count_var = tk.IntVar(value=10)
        tk.Spinbox(
            count_border, from_=6, to=14,
            textvariable=self._count_var,
            width=7, font=FONT_BODY,
            bg=BG_INPUT, fg=GRAY_1,
            buttonbackground=BG_INPUT,
            insertbackground=GRAY_1,
            relief="flat", bd=0,
        ).pack()

        # Generate button
        self._gen_btn = NeonButton(
            p, text="▶  GENERATE ALBUM",
            command=self._on_generate,
            color1=NEON_PINK, color2=NEON_CYAN,
            width=380, height=52,
            font=("Helvetica", 12, "bold"),
        )
        self._gen_btn.pack(fill=tk.X, pady=(0, 10))

        # Status
        self._status_var = tk.StringVar(value="")
        self._status_lbl = tk.Label(
            p, textvariable=self._status_var,
            fg=NEON_LIME, bg=BG_BASE,
            font=FONT_MONO, wraplength=370, justify="left",
        )
        self._status_lbl.pack(anchor="w")

        # Save button (hidden until generation is done)
        self._save_btn = NeonButton(
            p, text="⬇  SAVE ALBUM  (JSON + PNG)",
            command=self._on_save,
            color1=NEON_GOLD, color2=NEON_LIME,
            width=380, height=46,
            font=("Helvetica", 10, "bold"),
        )

    def _field_label(self, parent, text, color):
        tk.Label(parent, text=text, fg=color, bg=BG_BASE,
                 font=FONT_MONO).pack(anchor="w")

    def _build_styled_combo(self, parent, var, values, color):
        border = tk.Frame(parent, bg=color, padx=1, pady=1)
        border.pack(fill=tk.X, pady=(4, 12))
        # Use tk.OptionMenu
        menu_btn = tk.OptionMenu(border, var, *values)
        menu_btn.configure(
            bg=BG_INPUT, fg=GRAY_1,
            activebackground=color, activeforeground=BG_BASE,
            highlightthickness=0, relief="flat",
            font=FONT_BODY, anchor="w",
            indicatoron=True,
        )
        menu_btn["menu"].configure(
            bg=BG_INPUT, fg=GRAY_1,
            activebackground=color, activeforeground=BG_BASE,
            font=FONT_BODY,
        )
        menu_btn.pack(fill=tk.X)

    # Right panel: vinyl + metadata + tracklist

    def _build_right(self):
        p = self._col_right

        # Top: vinyl + metadata
        top = tk.Frame(p, bg=BG_BASE)
        top.pack(fill=tk.X, pady=(0, 12))

        # Vinyl record
        self._vinyl = VinylRecord(top, size=270)
        self._vinyl.pack(side=tk.LEFT, padx=(0, 28))

        # Metadata
        meta = tk.Frame(top, bg=BG_BASE)
        meta.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, anchor="n")

        tk.Label(meta, text="AI-CURATED PLAYLIST",
                 fg=GRAY_3, bg=BG_BASE, font=FONT_MONO).pack(anchor="w")

        self._lbl_album = tk.Label(meta, text="—",
                                   fg=WHITE, bg=BG_BASE,
                                   font=("Georgia", 28, "bold"),
                                   wraplength=500, justify="left")
        self._lbl_album.pack(anchor="w", pady=(4, 0))

        self._lbl_artist = tk.Label(meta, text="",
                                    fg=NEON_PINK, bg=BG_BASE,
                                    font=("Georgia", 13, "italic"))
        self._lbl_artist.pack(anchor="w", pady=(2, 6))

        self._lbl_mood = tk.Label(meta, text="",
                                  fg=GRAY_2, bg=BG_BASE,
                                  font=FONT_BODY, wraplength=500, justify="left")
        self._lbl_mood.pack(anchor="w", pady=(0, 8))

        self._lbl_meta_line = tk.Label(meta, text="",
                                       fg=GRAY_3, bg=BG_BASE, font=FONT_SMALL)
        self._lbl_meta_line.pack(anchor="w")

        self._tag_frame = tk.Frame(meta, bg=BG_BASE)
        self._tag_frame.pack(anchor="w", pady=(10, 0), fill=tk.X)

        # Accent divider
        tk.Frame(p, bg=NEON_CYAN, height=1).pack(fill=tk.X, pady=(0, 0))

        # Track list column headers
        hdr = tk.Frame(p, bg=BG_BASE, pady=5, padx=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="#",               fg=GRAY_3, bg=BG_BASE, font=FONT_MONO, width=4).pack(side=tk.LEFT)
        tk.Label(hdr, text="TITLE / ARTIST",  fg=GRAY_3, bg=BG_BASE, font=FONT_MONO).pack(side=tk.LEFT, padx=8)
        tk.Label(hdr, text="PLAY",            fg=GRAY_3, bg=BG_BASE, font=FONT_MONO).pack(side=tk.RIGHT, padx=6)
        tk.Frame(p, bg=GRAY_4, height=1).pack(fill=tk.X)

        # Scrollable track list
        outer = tk.Frame(p, bg=BG_BASE)
        outer.pack(fill=tk.BOTH, expand=True)

        self._track_canvas = tk.Canvas(outer, bg=BG_BASE, bd=0, highlightthickness=0)
        self._track_sb     = ttk.Scrollbar(outer, orient="vertical",
                                           command=self._track_canvas.yview)
        self._track_inner  = tk.Frame(self._track_canvas, bg=BG_BASE)

        self._track_inner.bind("<Configure>",
            lambda e: self._track_canvas.configure(
                scrollregion=self._track_canvas.bbox("all")))

        self._track_canvas.create_window((0, 0), window=self._track_inner, anchor="nw")
        self._track_canvas.configure(yscrollcommand=self._track_sb.set)

        self._track_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._track_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._track_canvas.bind(
            "<MouseWheel>",
            lambda e: self._track_canvas.yview_scroll(-1*(e.delta//120), "units"))

    # Event handlers

    def _on_generate(self):
        journal = self._journal.get("1.0", tk.END).strip()
        if not journal:
            messagebox.showwarning("Missing Input",
                                   "Please enter a mood or journal entry.")
            return

        genre       = self._genre_var.get()
        era         = self._era_var.get()
        track_count = self._count_var.get()

        # Update accent colors to match the chosen genre
        self._accent1, self._accent2 = GENRE_COLORS.get(genre, (NEON_PINK, NEON_CYAN))

        # Disable UI during generation
        self._gen_btn.set_enabled(False)
        self._save_btn.pack_forget()
        self._clear_tracks()
        self._reset_metadata()
        self._vinyl.start_spin()
        self._set_status("◈  Starting generation...")

        threading.Thread(
            target=self._gen_thread,
            args=(journal, genre, era, track_count),
            daemon=True,
        ).start()

    def _gen_thread(self, journal, genre, era, track_count):
        """Background worker: Gemini → Last.fm → Pollinations."""
        try:
            self._set_status("◈  Gemini is thinking...")
            album_data = call_gemini(journal, genre, era, track_count)

            self._set_status("◈  Fetching real tracks from Last.fm...")
            tracklist = build_tracklist(album_data.get("lastfm_tags", []), track_count)

            self._set_status("◈  Generating cover art via Pollinations.ai...")
            cover_img = generate_cover_image(
                album_data.get("cover_prompt", "abstract album cover"),
                genre,
            )

            self._album_data  = album_data
            self._tracklist   = tracklist
            self._cover_image = cover_img

            self.after(0, self._render, album_data, tracklist, cover_img, genre)

        except json.JSONDecodeError as e:
            self.after(0, self._on_error, f"Gemini returned invalid JSON.\n{e}")
        except requests.exceptions.RequestException as e:
            self.after(0, self._on_error, f"Network error.\n{e}")
        except Exception as e:
            self.after(0, self._on_error, str(e))

    # Result rendering

    def _render(self, album_data, tracklist, cover_img, genre):
        self._vinyl.set_cover(cover_img)
        self._vinyl.start_spin()

        # Metadata labels
        self._lbl_album.configure(text=album_data.get("album_name", "—"))
        self._lbl_artist.configure(text=album_data.get("artist_name", ""))
        self._lbl_mood.configure(text=album_data.get("mood_description", ""))
        self._lbl_meta_line.configure(
            text=(f"{album_data.get('year','?')}  ◈  "
                  f"{len(tracklist)} songs  ◈  "
                  f"{album_data.get('label','?')}"))

        # Genre-colored tag pills
        for w in self._tag_frame.winfo_children():
            w.destroy()
        pill_colors = [self._accent1, self._accent2, NEON_LIME, NEON_GOLD,
                       NEON_PINK, NEON_CYAN]
        for i, tag in enumerate(album_data.get("lastfm_tags", [])):
            c = pill_colors[i % len(pill_colors)]
            pill = tk.Frame(self._tag_frame, bg=c, padx=9, pady=2)
            pill.pack(side=tk.LEFT, padx=(0, 6), pady=2)
            tk.Label(pill, text=f"#{tag}", bg=c, fg=BG_BASE, font=FONT_TINY).pack()

        # Tracklist rows
        self._render_tracks(tracklist, genre)

        self._set_status(f"✓  {len(tracklist)} real songs loaded.")
        self._status_lbl.configure(fg=NEON_LIME)
        self._gen_btn.set_enabled(True)
        self._save_btn.pack(fill=tk.X, pady=(10, 0))

    def _render_tracks(self, tracks, genre):
        self._clear_tracks()
        a1, a2 = GENRE_COLORS.get(genre, (NEON_PINK, NEON_CYAN))

        for i, track in enumerate(tracks):
            bg    = BG_ROW_A if i % 2 == 0 else BG_ROW_B
            color = a1 if i % 2 == 0 else a2

            row = tk.Frame(self._track_inner, bg=bg, pady=7, padx=6)
            row.pack(fill=tk.X)

            # Left accent bar
            tk.Frame(row, bg=color, width=3).pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

            # Track number
            tk.Label(row, text=f"{i+1:02d}", bg=bg, fg=GRAY_3,
                     font=FONT_MONO, width=3).pack(side=tk.LEFT)

            # Song info
            info = tk.Frame(row, bg=bg)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
            tk.Label(info, text=track["title"], bg=bg, fg=WHITE,
                     font=FONT_HEAD, anchor="w").pack(anchor="w")
            tk.Label(info, text=track["artist"], bg=bg, fg=GRAY_2,
                     font=FONT_SMALL, anchor="w").pack(anchor="w")

            # Listen button with hover effect
            url = track.get("url", "")
            btn = tk.Label(
                row, text="▶ LISTEN",
                bg=GRAY_4, fg=color,
                font=FONT_TINY, padx=10, pady=4,
                cursor="hand2", relief="flat",
            )
            btn.pack(side=tk.RIGHT, padx=(8, 0))
            btn.bind("<Button-1>", lambda e, u=url: webbrowser.open(u) if u else None)
            btn.bind("<Enter>",    lambda e, b=btn, c=color: b.configure(bg=c, fg=BG_BASE))
            btn.bind("<Leave>",    lambda e, b=btn, c=color: b.configure(bg=GRAY_4, fg=c))

    def _clear_tracks(self):
        for w in self._track_inner.winfo_children():
            w.destroy()

    def _reset_metadata(self):
        self._lbl_album.configure(text="—")
        self._lbl_artist.configure(text="")
        self._lbl_mood.configure(text="")
        self._lbl_meta_line.configure(text="")
        for w in self._tag_frame.winfo_children():
            w.destroy()

    # Save

    def _on_save(self):
        if not self._album_data or not self._cover_image:
            messagebox.showwarning("Nothing to save", "Generate an album first.")
            return
        folder = filedialog.askdirectory(title="Choose save folder")
        if not folder:
            return

        raw_name  = self._album_data.get("album_name", "album")
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_"
                            for c in raw_name).strip().replace(" ", "_")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{safe_name}_{ts}"

        # JSON export
        json_path = os.path.join(folder, f"{base}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "album":        self._album_data,
                "tracklist":    self._tracklist,
            }, f, indent=2, ensure_ascii=False)

        # PNG export
        png_path = os.path.join(folder, f"{base}.png")
        self._cover_image.save(png_path)

        messagebox.showinfo("Saved!",
                            f"JSON → {json_path}\nPNG  → {png_path}")

    # Utilities

    def _set_status(self, msg):
        self.after(0, self._status_var.set, msg)

    def _on_error(self, msg):
        self._vinyl.stop_spin()
        self._set_status("⚠  Error occurred.")
        self._status_lbl.configure(fg=NEON_PINK)
        self._gen_btn.set_enabled(True)
        messagebox.showerror("Error", msg)

#  Entry point

if __name__ == "__main__":
    app = AlbumCoverStudio()
    app.mainloop()