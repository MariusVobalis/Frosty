
import asyncio, os, re, tempfile, threading, time, tkinter as tk
import mss, cv2, numpy as np
import psutil
from PIL import Image
from pynput import keyboard
import edge_tts, pygame
from paddleocr import PaddleOCR
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

VOICE="en-US-ChristopherNeural"; RATE="-8%"; PITCH="-8Hz"; DUCK=.25

with mss.MSS() as s:
    mon=s.monitors[1]
L,T,W,H=mon["left"],mon["top"],mon["width"],mon["height"]

pygame.mixer.init()
audio_backup={}
audio_file=None
speech_lock=threading.Lock()

def sessions():
    out=[]
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process:
                out.append((s,s._ctl.QueryInterface(ISimpleAudioVolume)))
    except: pass
    return out

def duck():
    global audio_backup
    audio_backup={}
    for s,v in sessions():
        try:
            audio_backup[s.Process.pid]=(v,v.GetMasterVolume())
            if not v.GetMute(): v.SetMasterVolume(DUCK,None)
        except: pass

def unduck():
    global audio_backup
    for v,old in audio_backup.values():
        try: v.SetMasterVolume(old,None)
        except: pass
    audio_backup={}

def stop():
    global audio_file
    try: pygame.mixer.music.stop()
    except: pass
    unduck()
    if audio_file:
        try: os.remove(audio_file)
        except: pass
        audio_file=None

async def tts(text,fn):
    await edge_tts.Communicate(text=text,voice=VOICE,rate=RATE,pitch=PITCH).save(fn)


def _prepare_narration(text):
    """
    Make Edge Neural speech sound more natural without changing OCR.
    This is intentionally lightweight: no extra OCR, no external AI.
    """
    text = text.strip()

    # Normalize whitespace and punctuation spacing.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)

    # Give sentence boundaries a little breathing room.
    text = re.sub(r"([.!?])\s+", r"\1  ", text)

    # Avoid speaking accidental OCR separators as strange words.
    text = text.replace("  —  ", " — ")
    text = text.replace("  -  ", " — ")

    return text.strip()


def speak(text):
    text = _prepare_narration(text)
    global audio_file
    with speech_lock:
        stop()
        fd,fn=tempfile.mkstemp(suffix=".mp3"); os.close(fd); audio_file=fn
        try:
            asyncio.run(tts(text,fn))
            duck(); pygame.mixer.music.load(fn); pygame.mixer.music.set_volume(1); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): time.sleep(.05)
        except Exception as e: print("[VOICE]",repr(e))
        finally:
            try: pygame.mixer.music.stop()
            except: pass
            unduck()
            try: os.remove(fn)
            except: pass
            audio_file=None

print("[START] Loading PaddleOCR...")
ocr=PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="gpu",
    text_det_limit_side_len=1600
)

def select():
    # Opaque screenshot-backed selector: avoids HDR transparency black screen.
    with mss.MSS() as s:
        shot=s.grab({"left":L,"top":T,"width":W,"height":H})
    fd,path=tempfile.mkstemp(suffix=".png"); os.close(fd)
    Image.frombytes("RGB",shot.size,shot.rgb).save(path,"PNG")
    ans={"r":None}; root=tk.Tk(); root.overrideredirect(True); root.geometry(f"{W}x{H}+{L}+{T}"); root.attributes("-topmost",True)
    c=tk.Canvas(root,width=W,height=H,highlightthickness=0,cursor="crosshair"); c.pack(fill="both",expand=True)
    photo=tk.PhotoImage(file=path); c.create_image(0,0,image=photo,anchor="nw")
    st={"x":None,"y":None}; box={"id":None}; label={"id":None}
    def down(e):
        st["x"],st["y"]=e.x,e.y
        if box["id"]: c.delete(box["id"])
        box["id"]=c.create_rectangle(e.x,e.y,e.x,e.y,outline="white",width=3)
    def move(e):
        if st["x"] is None:return
        c.coords(box["id"],st["x"],st["y"],e.x,e.y)
        if label["id"]: c.delete(label["id"])
        label["id"]=c.create_text(e.x+10,e.y+10,text=f"{abs(e.x-st['x'])} x {abs(e.y-st['y'])}",fill="white",font=("Segoe UI",12,"bold"),anchor="nw")
    def up(e):
        if st["x"] is None:return
        w,h=abs(e.x-st["x"]),abs(e.y-st["y"])
        if w<20 or h<10:return
        ans["r"]=(L+min(st["x"],e.x),T+min(st["y"],e.y),w,h); root.destroy()
    def cancel(e=None):
        ans["r"]=None
        try: root.destroy()
        except: pass
    c.bind("<ButtonPress-1>",down); c.bind("<B1-Motion>",move); c.bind("<ButtonRelease-1>",up)
    root.bind("<Escape>",cancel); root.bind("<Button-3>",cancel)
    c.create_text(W//2,25,text="FROSTY — drag around the text | ESC = cancel",fill="white",font=("Segoe UI",14,"bold"))
    root.focus_force(); root.mainloop()
    try: os.remove(path)
    except: pass
    return ans["r"]


# ---------------------------------------------------------------------------
# GPU TURBO
# ---------------------------------------------------------------------------
_turbo_state = {
    "active": False,
    "game": None,
    "game_priority": None,
    "frosty_priority": None,
}

_SYSTEM_FOREGROUND = {
    "explorer.exe", "dwm.exe", "taskmgr.exe", "applicationframehost.exe",
    "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "lockapp.exe", "textinputhost.exe", "ctfmon.exe"
}

def _foreground_pid_and_name():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid = int(pid.value)
        if not pid:
            return None, None
        try:
            name = psutil.Process(pid).name()
        except Exception:
            name = None
        return pid, name
    except Exception:
        return None, None

def _turbo_begin(game_pid=None, game_name=None):
    global _turbo_state
    if _turbo_state["active"]:
        return

    me = psutil.Process(os.getpid())
    try:
        old_me = me.nice()
    except Exception:
        old_me = None

    target = None
    old_target = None

    if game_pid and game_pid != os.getpid():
        try:
            p = psutil.Process(game_pid)
            pname = p.name().lower()
            if p.is_running() and pname not in _SYSTEM_FOREGROUND:
                old_target = p.nice()
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                target = p
                print(
                    f"[TURBO] Game: {p.name()} (PID {p.pid}) "
                    f"priority -> BELOW_NORMAL"
                )
        except Exception as e:
            print(f"[TURBO] Could not lower foreground app: {e!r}")

    try:
        me.nice(psutil.HIGH_PRIORITY_CLASS)
        print("[TURBO] Frosty priority -> HIGH")
    except Exception as e:
        print(f"[TURBO] Could not raise Frosty priority: {e!r}")

    _turbo_state.update({
        "active": True,
        "game": target,
        "game_priority": old_target,
        "frosty_priority": old_me,
    })

def _turbo_end():
    global _turbo_state
    if not _turbo_state["active"]:
        return

    try:
        me = psutil.Process(os.getpid())
        old_me = _turbo_state.get("frosty_priority")
        if old_me is not None:
            me.nice(old_me)
    except Exception as e:
        print(f"[TURBO] Could not restore Frosty priority: {e!r}")

    try:
        game = _turbo_state.get("game")
        old_game = _turbo_state.get("game_priority")
        if game is not None and old_game is not None and game.is_running():
            game.nice(old_game)
            print(f"[TURBO] Game: {game.name()} priority restored")
    except Exception as e:
        print(f"[TURBO] Could not restore game priority: {e!r}")

    _turbo_state = {
        "active": False,
        "game": None,
        "game_priority": None,
        "frosty_priority": None,
    }

def capture(r):
    l,t,w,h=r
    with mss.MSS() as s:
        q=s.grab({"left":l,"top":t,"width":w,"height":h})
    return Image.frombytes("RGB",q.size,q.rgb)


def parse(res):
    """
    Extract PaddleOCR boxes and reconstruct reading order.

    PaddleOCR gives us individual text boxes. Frostpunk's centered
    paragraphs are multi-line, so simply sorting every box by Y/X can
    scramble the sentence. We first cluster boxes into horizontal lines,
    then sort each line left-to-right, and finally sort lines top-to-bottom.
    """
    try:
        d = res.json
        if callable(d):
            d = d()
    except Exception:
        return []

    if isinstance(d, str):
        import json
        try:
            d = json.loads(d)
        except Exception:
            return []

    if not isinstance(d, dict):
        return []

    d = d.get("res", d)

    texts = d.get("rec_texts", [])
    scores = d.get("rec_scores", [])
    boxes = d.get("rec_boxes", [])

    raw = []

    for i, text in enumerate(texts):
        text = str(text).strip()
        if not text:
            continue

        try:
            box = np.asarray(boxes[i], dtype=float)
            if box.shape == (4, 2):
                xs = box[:, 0]
                ys = box[:, 1]
                left = float(xs.min())
                right = float(xs.max())
                top = float(ys.min())
                bottom = float(ys.max())
            else:
                left, top, right, bottom = map(float, box[:4])

            height = max(1.0, bottom - top)
            center_y = (top + bottom) / 2.0
        except Exception:
            continue

        try:
            score = float(scores[i])
        except Exception:
            score = 0.0

        raw.append({
            "text": text,
            "score": score,
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
            "cy": center_y,
            "h": height,
        })

    if not raw:
        return []

    # Estimate the typical character/box height. OCR may return slightly
    # different heights for words on the same visual line.
    heights = sorted(x["h"] for x in raw)
    median_h = heights[len(heights) // 2]

    # A generous tolerance handles anti-aliased text and slightly slanted
    # detection boxes, but still keeps genuinely separate lines apart.
    tolerance = max(8.0, median_h * 0.60)

    lines = []

    # Process boxes top-to-bottom and assign each to the closest existing
    # line whose vertical center is close enough.
    for item in sorted(raw, key=lambda x: (x["cy"], x["left"])):
        best = None
        best_distance = None

        for line in lines:
            distance = abs(item["cy"] - line["cy"])
            line_tol = max(
                tolerance,
                max(item["h"], line["height"]) * 0.60,
            )

            if distance <= line_tol:
                if best_distance is None or distance < best_distance:
                    best = line
                    best_distance = distance

        if best is None:
            lines.append({
                "items": [item],
                "cy": item["cy"],
                "height": item["h"],
            })
        else:
            best["items"].append(item)

            # Update line center using all members.
            best["cy"] = sum(
                x["cy"] for x in best["items"]
            ) / len(best["items"])

            best["height"] = sum(
                x["h"] for x in best["items"]
            ) / len(best["items"])

    # Sort lines by their actual vertical position.
    lines.sort(key=lambda line: line["cy"])

    ordered = []

    for line in lines:
        # Within a line, normal reading order is left-to-right.
        line["items"].sort(key=lambda x: x["left"])

        for item in line["items"]:
            ordered.append((
                item["cy"],
                item["left"],
                item["score"],
                item["text"],
            ))

    return ordered


def clean(x):
    x=re.sub(r"\s+"," ",x)
    return re.sub(r"\s+([,.!?;:])",r"\1",x).strip()



def _fast_resize_for_ocr(img):
    """
    Keep OCR input large enough for small game fonts, but avoid the
    enormous 8k-9k images Paddle was receiving from small selections.
    Target ~2200 px on the long side and never upscale an already-large
    selection beyond what is useful for OCR.
    """
    w, h = img.size
    long_side = max(w, h)

    if long_side < 1100:
        scale = min(3.0, 2200.0 / long_side)
    elif long_side < 1600:
        scale = min(1.8, 2200.0 / long_side)
    else:
        scale = min(1.35, 2200.0 / long_side)

    if abs(scale - 1.0) < 0.05:
        return img

    new_size = (
        max(1, int(w * scale)),
        max(1, int(h * scale)),
    )
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _normalize_ocr_word(word):
    word = re.sub(r"^[^A-Za-z0-9']+|[^A-Za-z0-9']+$", "", word)
    return word


def _word_similarity(a, b):
    from difflib import SequenceMatcher
    aa = _normalize_ocr_word(a).lower()
    bb = _normalize_ocr_word(b).lower()

    if not aa or not bb:
        return 0.0

    return SequenceMatcher(None, aa, bb).ratio()



def _cleanup_ocr_artifacts(text, alternatives):
    """
    Conservative post-OCR cleanup.

    This runs only on already-produced text, so it adds essentially no
    latency compared with PaddleOCR.

    It uses the other OCR candidates as evidence. It does NOT use a game
    dictionary and does not blindly spellcheck proper nouns.
    """
    if not text or not alternatives:
        return text

    from difflib import SequenceMatcher

    words = text.split()
    alt_words = [a.split() for a in alternatives if a.strip()]

    def bare(w):
        return re.sub(r"[^A-Za-z0-9']", "", w).lower()

    def best_alt(word, idx):
        bw = bare(word)
        if not bw:
            return None

        hits = []

        for awords in alt_words:
            # Search a small neighborhood, not the entire paragraph.
            lo = max(0, idx - 3)
            hi = min(len(awords), idx + 4)

            for j in range(lo, hi):
                other = awords[j]
                bo = bare(other)
                if not bo:
                    continue

                ratio = SequenceMatcher(
                    None, bw, bo, autojunk=False
                ).ratio()

                if ratio >= 0.82:
                    hits.append((ratio, other))

        if not hits:
            return None

        hits.sort(reverse=True, key=lambda x: x[0])
        return hits[0]

    repaired = []
    changes = 0

    for i, word in enumerate(words):
        replacement = best_alt(word, i)

        if replacement:
            ratio, other = replacement

            # Repair obvious glued punctuation/spacing artifacts.
            if (
                ratio >= 0.88
                and len(bare(other)) >= 3
                and len(bare(word)) <= len(bare(other)) + 2
                and bare(word) != bare(other)
            ):
                # Never replace a capitalized/proper-looking token with a
                # lower-case one merely because they are similar.
                if not (
                    word[:1].isupper()
                    and other[:1].islower()
                ):
                    word = other
                    changes += 1

        repaired.append(word)

    result = " ".join(repaired)

    # Generic merged-word repair. Only accept a split if the exact
    # concatenation is strongly supported by an alternative OCR result.
    for awords in alt_words:
        for i in range(len(words) - 1):
            merged = bare(repaired[i] + repaired[i + 1])

            if len(merged) < 6:
                continue

            for j in range(len(awords) - 1):
                pair = bare(awords[j] + awords[j + 1])

                if merged == pair:
                    # Prefer the alternative spacing exactly.
                    candidate = (
                        awords[j] + " " + awords[j + 1]
                    )

                    current = (
                        repaired[i] + " " + repaired[i + 1]
                    )

                    if current != candidate:
                        repaired[i] = awords[j]
                        repaired[i + 1] = awords[j + 1]
                        changes += 1
                    break

    result = " ".join(repaired)

    # Small generic punctuation/spacing cleanup.
    result = re.sub(r"\s+([,.!?;:])", r"\1", result)
    result = re.sub(r"([,.!?;:])([A-Za-z])", r"\1 \2", result)
    result = re.sub(r"\s{2,}", " ", result).strip()

    if changes:
        print(
            f"[OCR] Conservative artifact cleanup: "
            f"{changes} supported correction(s)."
        )

    return result


def _repair_words(primary, alternatives):
    """
    Cheap word-level consensus.

    Only repairs a token when another OCR result has a very close token
    in the same neighborhood. This is deliberately conservative: it does
    not use a game dictionary and does not invent text.
    """
    if not alternatives:
        return primary

    p_words = primary.split()
    alt_words = [a.split() for a in alternatives if a.strip()]

    repaired = []
    for i, word in enumerate(p_words):
        candidates = []

        for words in alt_words:
            lo = max(0, i - 2)
            hi = min(len(words), i + 3)

            for j in range(lo, hi):
                other = words[j]
                sim = _word_similarity(word, other)

                if sim >= 0.78:
                    candidates.append((sim, other))

        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            best_sim, best_word = candidates[0]

            # Prefer a clean alternative only when it has substantially
            # better structure and is not merely a punctuation difference.
            if (
                best_sim >= 0.86
                and len(best_word) >= 2
                and (
                    len(best_word) > len(word)
                    or word.lower() != best_word.lower()
                )
            ):
                word = best_word

        repaired.append(word)

    return " ".join(repaired)


def _prepare_for_tts(text):
    """
    Preserve sentence/paragraph rhythm without doing extra OCR work.
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def variants(img):
    """
    Performance-aware OCR preprocessing.

    Small UI text benefits from enlargement, but blindly multiplying every
    selection by 2.5x can make PaddleOCR spend time resizing an already
    huge image. Keep the longest side around 1800-2400 px.
    """
    bgr = cv2.cvtColor(
        np.asarray(img),
        cv2.COLOR_RGB2BGR,
    )

    h, w = bgr.shape[:2]
    longest = max(h, w)

    # read() already prepares the image. Do not enlarge it a second time.
    # Only genuinely small prepared images receive a controlled enlargement.
    if longest < 1400:
        scale = min(1.6, 1800.0 / max(1, longest))
    else:
        scale = 1.0

    if abs(scale - 1.0) < 0.01:
        up = bgr
    else:
        up = cv2.resize(
            bgr,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    gray = cv2.cvtColor(
        up,
        cv2.COLOR_BGR2GRAY,
    )

    clahe = cv2.createCLAHE(
        2.0,
        (8, 8),
    )
    con = clahe.apply(gray)

    blur = cv2.GaussianBlur(
        con,
        (0, 0),
        1.1,
    )

    sharp = cv2.addWeighted(
        con,
        1.35,
        blur,
        -0.35,
        0,
    )

    _, otsu = cv2.threshold(
        sharp,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    morph = cv2.morphologyEx(
        otsu,
        cv2.MORPH_CLOSE,
        np.ones((2, 2), np.uint8),
    )

    return [
        (
            "upscaled",
            up,
        ),
        (
            "contrast",
            cv2.cvtColor(
                con,
                cv2.COLOR_GRAY2BGR,
            ),
        ),
        (
            "sharp",
            cv2.cvtColor(
                sharp,
                cv2.COLOR_GRAY2BGR,
            ),
        ),
        (
            "otsu",
            cv2.cvtColor(
                otsu,
                cv2.COLOR_GRAY2BGR,
            ),
        ),
        (
            "morph",
            cv2.cvtColor(
                morph,
                cv2.COLOR_GRAY2BGR,
            ),
        ),
    ]


COMMON=set("the and to of a in we our on was by from this that is are were for with it as be have has had not no one you they their there any others out what why did do should now world know survive people home frozen generator blizzard crossed reach find solid abandoned worst site way sea north convoy handful managed only".split())

def quality(text,conf):
    words=re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text)
    if not words:return -9999
    common=sum(w.lower() in COMMON for w in words)
    weird=len(re.findall(r"[^A-Za-z0-9\s.,!?;:'\"-]",text))
    bad=len(re.findall(r"[A-Za-z]\d[A-Za-z]|\d[A-Za-z]\d",text))*3
    bad+=sum(len(w)>22 for w in words)*2
    ratio=sum(c.isalpha() for c in text)/max(1,len(text))
    return common*3+min(len(words),100)*.12+conf*10+ratio*5-weird*1.5-bad



def _sentence_quality(text, conf):
    """
    v23 compatibility wrapper around the proven v22 English-quality scorer.
    """
    return quality(text, conf)


def _reconstruct(rows):
    """
    Convert parse()'s already line-ordered OCR rows into one paragraph.
    """
    if not rows:
        return ""

    text = " ".join(
        str(row[3]).strip()
        for row in rows
        if len(row) >= 4 and str(row[3]).strip()
    )

    return clean(text)




def _token_similarity(a, b):
    """
    Small edit-distance-like similarity for OCR tokens.
    No dictionary and no game-specific hard-coding.
    """
    from difflib import SequenceMatcher

    a = re.sub(r"[^A-Za-z0-9']", "", a).lower()
    b = re.sub(r"[^A-Za-z0-9']", "", b).lower()

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b,
        autojunk=False,
    ).ratio()


def _token_consensus(best_text, candidates):
    """
    Lightweight word-level cleanup.

    The sentence chosen by the global consensus remains the backbone.
    When another OCR pass produces a very similar token and that spelling
    has independent support, prefer the supported spelling.

    This is intentionally conservative: it never invents words.
    """
    if len(candidates) < 2:
        return best_text

    best_tokens = _tokenize(best_text)

    if not best_tokens:
        return best_text

    # Build token lists for alternatives.
    alternatives = [
        _tokenize(c["text"])
        for c in candidates
        if c["text"] != best_text
    ]

    if not alternatives:
        return best_text

    from difflib import SequenceMatcher

    corrected = list(best_tokens)

    for alt in alternatives:
        if not alt:
            continue

        matcher = SequenceMatcher(
            None,
            best_tokens,
            alt,
            autojunk=False,
        )

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue

            left = best_tokens[i1:i2]
            right = alt[j1:j2]

            # Only attempt one-to-one word corrections. We do not want
            # this lightweight pass to invent or delete whole phrases.
            if len(left) != len(right):
                continue

            for offset, (old, new) in enumerate(
                zip(left, right)
            ):
                sim = _token_similarity(
                    old,
                    new,
                )

                if sim < 0.78 or old.lower() == new.lower():
                    continue

                # Count independent support for the alternative spelling.
                support = 0

                for other in alternatives:
                    if other is alt:
                        continue

                    if i1 + offset >= len(other):
                        continue

                    other_token = other[i1 + offset]

                    if _token_similarity(
                        new,
                        other_token,
                    ) >= 0.90:
                        support += 1

                if support >= 1:
                    corrected[
                        i1 + offset
                    ] = new

    # Rebuild conservatively. Punctuation from the selected OCR candidate
    # is preserved separately by _restore_punctuation().
    return " ".join(corrected)


def _restore_punctuation(source, tokens_text):
    """
    Reapply punctuation from the selected OCR sentence after token
    consensus. This keeps normal commas/full stops without trying to
    perform linguistic rewriting.
    """
    source_tokens = _tokenize(source)
    new_tokens = tokens_text.split()

    if not source_tokens or not new_tokens:
        return source

    # If token counts changed, don't risk damaging punctuation.
    if len(source_tokens) != len(new_tokens):
        return source

    positions = []
    for match in re.finditer(
        r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?",
        source,
    ):
        positions.append(match.end())

    out = []
    last = 0

    for i, token in enumerate(new_tokens):
        end = positions[i]

        punctuation = source[
            positions[i - 1] if i else 0:end
        ]

        # Extract only punctuation immediately following the source token.
        m = re.search(
            r"[^A-Za-z0-9']+$",
            source[
                match.start() if False else
                max(0, end - len(source_tokens[i]) - 8):
                end
            ],
        )

        out.append(token)

    # Safer approach: replace source tokens one by one while preserving all
    # non-token text.
    result = []
    cursor = 0

    matches = list(re.finditer(
        r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?",
        source,
    ))

    for i, match in enumerate(matches):
        result.append(
            source[cursor:match.start()]
        )
        result.append(
            new_tokens[i]
        )
        cursor = match.end()

    result.append(source[cursor:])
    return "".join(result)


def _normalize_for_consensus(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text):
    return re.findall(
        r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+",
        text
    )


def _similarity(a, b):
    from difflib import SequenceMatcher

    aa = _tokenize(a.lower())
    bb = _tokenize(b.lower())

    if not aa or not bb:
        return 0.0

    return SequenceMatcher(
        None,
        " ".join(aa),
        " ".join(bb),
    ).ratio()


def _coverage(a, b):
    """
    How much of the shorter OCR text is represented in the longer one.

    This catches a failure that defeated v23:
    two OCR results can be globally similar while one has silently
    dropped an entire chunk of the sentence.
    """
    from difflib import SequenceMatcher

    aa = _tokenize(a.lower())
    bb = _tokenize(b.lower())

    if not aa or not bb:
        return 0.0

    shorter, longer = (
        (aa, bb)
        if len(aa) <= len(bb)
        else (bb, aa)
    )

    sm = SequenceMatcher(
        None,
        shorter,
        longer,
        autojunk=False,
    )

    matched = sum(
        block.size
        for block in sm.get_matching_blocks()
    )

    return matched / max(1, len(shorter))


def _length_ratio(a, b):
    aa = _tokenize(a)
    bb = _tokenize(b)

    if not aa or not bb:
        return 0.0

    return min(len(aa), len(bb)) / max(
        len(aa), len(bb)
    )


def _pair_metrics(a, b):
    return {
        "similarity": _similarity(a, b),
        "coverage": _coverage(a, b),
        "length_ratio": _length_ratio(a, b),
    }


def _consensus_strength(candidates):
    if not candidates:
        return None, 0.0, 0.0

    best = None
    best_score = -1.0

    for candidate in candidates:
        metrics = []

        for other in candidates:
            if other is candidate:
                continue

            metrics.append(
                _pair_metrics(
                    candidate["text"],
                    other["text"],
                )
            )

        if not metrics:
            score = 0.0
            agreement = 0.0
            mean_similarity = 0.0
            mean_coverage = 0.0
        else:
            mean_similarity = sum(
                m["similarity"]
                for m in metrics
            ) / len(metrics)

            mean_coverage = sum(
                m["coverage"]
                for m in metrics
            ) / len(metrics)

            strong = sum(
                (
                    m["similarity"] >= 0.90
                    and m["coverage"] >= 0.90
                    and m["length_ratio"] >= 0.90
                )
                for m in metrics
            )

            agreement = strong / len(metrics)

            # Coverage is intentionally important. It prevents a shorter
            # candidate with good confidence from winning simply because
            # its remaining words look clean.
            score = (
                mean_similarity * 0.35
                + mean_coverage * 0.40
                + agreement * 0.25
            )

        candidate["_mean_similarity"] = mean_similarity
        candidate["_mean_coverage"] = mean_coverage
        candidate["_agreement"] = agreement

        if score > best_score:
            best_score = score
            best = candidate

    return (
        best,
        best["_agreement"] if best else 0.0,
        best["_mean_similarity"] if best else 0.0,
    )


def _consensus_score(candidate, candidates):
    metrics = []

    for other in candidates:
        if other is candidate:
            continue

        metrics.append(
            _pair_metrics(
                candidate["text"],
                other["text"],
            )
        )

    if metrics:
        similarity = sum(
            x["similarity"] for x in metrics
        ) / len(metrics)

        coverage = sum(
            x["coverage"] for x in metrics
        ) / len(metrics)

        length = sum(
            x["length_ratio"] for x in metrics
        ) / len(metrics)

        strong_votes = sum(
            (
                x["similarity"] >= 0.90
                and x["coverage"] >= 0.90
                and x["length_ratio"] >= 0.90
            )
            for x in metrics
        )
    else:
        similarity = coverage = length = 0.0
        strong_votes = 0

    language = _sentence_quality(
        candidate["text"],
        candidate["confidence"],
    )

    # The old v23 scorer over-rewarded a shorter "clean" OCR result.
    # v23.2 makes completeness/consensus dominant.
    return (
        coverage * 70.0
        + similarity * 35.0
        + length * 25.0
        + strong_votes * 12.0
        + language * 0.15
        + candidate["confidence"] * 2.0
    )


def _strong_enough_to_stop(candidates):
    """
    Early-stop only when the actual text agrees strongly.

    Three candidates that merely look similar are NOT enough. We require:
      - 3+ usable candidates
      - >= 90% sequence similarity
      - >= 90% token coverage
      - >= 90% relative token count
      - at least two strong supporting candidates

    This prevents the v23 failure where a 51-token result won against a
    much more complete 64-token result.
    """
    if len(candidates) < 3:
        return False, 0.0

    best, _, _ = _consensus_strength(
        candidates
    )

    if not best:
        return False, 0.0

    supporters = []

    for other in candidates:
        if other is best:
            continue

        m = _pair_metrics(
            best["text"],
            other["text"],
        )

        if (
            m["similarity"] >= 0.90
            and m["coverage"] >= 0.90
            and m["length_ratio"] >= 0.90
        ):
            supporters.append(m)

    # Require two independent strong supporters. This is deliberately
    # conservative because each PaddleOCR pass is relatively cheap compared
    # with giving the user a sentence with missing words.
    if len(supporters) >= 2:
        avg = sum(
            x["similarity"]
            for x in supporters
        ) / len(supporters)

        return True, avg

    return False, 0.0




def _run_ocr_variant(name, variant):
    t0 = time.perf_counter()
    all_rows = []

    for result in ocr.predict(variant):
        all_rows.extend(
            parse(result)
        )

    text = _reconstruct(all_rows)

    confidence = (
        sum(row[2] for row in all_rows)
        / len(all_rows)
        if all_rows
        else 0.0
    )

    language_score = _sentence_quality(
        text,
        confidence,
    )

    elapsed = (
        time.perf_counter() - t0
    )

    return {
        "name": name,
        "text": text,
        "confidence": confidence,
        "language": language_score,
        "segments": len(all_rows),
        "time": elapsed,
    }



def _trusted_first_pass(candidate):
    """
    Ultra-fast path.

    If the first, high-quality image variant is already extremely
    confident and produces strong English-like text, there is no reason
    to spend another 2-3 seconds proving what Paddle has already read.

    This is generic quality gating, not game-specific correction.
    """
    if not candidate:
        return False

    text = candidate.get("text", "").strip()
    confidence = float(candidate.get("confidence", 0.0))
    language = float(candidate.get("language", -9999.0))
    segments = int(candidate.get("segments", 0))

    if len(text) < 45 or segments < 8:
        return False

    weird = len(
        re.findall(
            r"[^A-Za-z0-9\s.,!?;:'\"()\-]",
            text,
        )
    )

    return (
        confidence >= 0.997
        and language >= 82.0
        and weird <= max(2, len(text) // 250)
    )


def _fast_consensus_ready(candidates):
    """
    Fast path after TWO passes.

    Two very similar, complete OCR results are enough for ordinary game
    text. Difficult text continues to additional variants.
    """
    if len(candidates) < 2:
        return False, 0.0

    a = candidates[0]
    b = candidates[1]

    m = _pair_metrics(
        a["text"],
        b["text"],
    )

    # Slightly stricter than necessary, because a third pass is cheap but
    # missing text is costly.
    ready = (
        m["similarity"] >= 0.96
        and m["coverage"] >= 0.96
        and m["length_ratio"] >= 0.95
        and a["confidence"] >= 0.90
        and b["confidence"] >= 0.90
    )

    return ready, m["similarity"]



def read(r, fg_pid=None, fg_name=None):
    try:
        img = capture(r)
        img = _fast_resize_for_ocr(img)

        _turbo_begin(fg_pid, fg_name)

        print(
            f"[F8] Selected area: "
            f"{img.size[0]}x{img.size[1]} (OCR-prepared)"
        )
        print(
            "[F8] FAST SMART OCR: "
            "high-confidence first-pass early acceptance."
        )

        all_variants = variants(img)
        variant_map = {name: variant for name, variant in all_variants}

        candidates = []

        def run_variant(name):
            variant = variant_map[name]
            t0 = time.perf_counter()
            rows = []

            for result in ocr.predict(variant):
                rows.extend(parse(result))

            text = _reconstruct(rows)
            confidence = (
                sum(row[2] for row in rows) / len(rows)
                if rows else 0.0
            )
            language_score = _sentence_quality(
                text,
                confidence,
            )
            elapsed = time.perf_counter() - t0

            if text:
                candidate = {
                    "name": name,
                    "text": text,
                    "confidence": confidence,
                    "language": language_score,
                    "segments": len(rows),
                    "time": elapsed,
                }
                candidates.append(candidate)

                print(
                    f"[OCR] {name}: "
                    f"segments={len(rows)} "
                    f"confidence={confidence:.3f} "
                    f"language={language_score:.2f} "
                    f"time={elapsed:.2f}s"
                )
                print("      " + text)
                return candidate

            print(
                f"[OCR] {name}: no usable text "
                f"(time={elapsed:.2f}s)"
            )
            return None

        # ------------------------------------------------------------
        # PASS 1: best quality / original image
        # ------------------------------------------------------------
        first = run_variant("upscaled")

        if first and _trusted_first_pass(first):
            print()
            print(
                "[OCR] HIGH-CONFIDENCE FIRST PASS — "
                "skipping all additional OCR."
            )
            print(
                "[OCR] This saves the contrast + fallback passes."
            )
        else:
            # --------------------------------------------------------
            # PASS 2: contrast
            # --------------------------------------------------------
            second = run_variant("contrast")

            if _fast_consensus_ready(candidates):
                _, agreement = _fast_consensus_ready(candidates)
                print()
                print(
                    f"[OCR] FAST CONSENSUS ({agreement:.2f})"
                )
                print(
                    "[OCR] Two-pass consensus — "
                    "skipping difficult-text preprocessing."
                )
            else:
                print()
                print(
                    "[OCR] First two passes disagree — "
                    "trying difficult-text fallbacks."
                )

                for name in ("sharp", "otsu", "morph"):
                    if name not in variant_map:
                        continue

                    run_variant(name)

                    # Once we have three strong mutually supporting
                    # candidates, stop immediately.
                    stop, agreement = _strong_enough_to_stop(
                        candidates
                    )

                    if stop:
                        print()
                        print(
                            f"[OCR] STRONG CONSENSUS ({agreement:.2f})"
                        )
                        print(
                            "[OCR] Remaining passes skipped."
                        )
                        break

        if not candidates:
            print("[F8] No usable text detected.")
            return

        for candidate in candidates:
            candidate["final"] = _consensus_score(
                candidate,
                candidates,
            )

        candidates.sort(
            key=lambda x: x["final"],
            reverse=True,
        )

        best = candidates[0]

        # Cheap word-level repair only when we actually have alternatives.
        if len(candidates) >= 2:
            alternatives = [
                c["text"]
                for c in candidates[1:]
            ]

            repaired = _repair_words(
                best["text"],
                alternatives,
            )

            if repaired != best["text"]:
                print(
                    "[OCR] Word-level consensus repaired "
                    "minor OCR differences."
                )
                best["text"] = repaired

        final_text = _cleanup_ocr_artifacts(
            best["text"],
            [
                c["text"]
                for c in candidates
                if c is not best
            ],
        )
        final_text = _prepare_for_tts(
            final_text
        )

        print()
        print("[F8] CONSENSUS RESULTS:")

        for i, candidate in enumerate(
            candidates[:5],
            1,
        ):
            print(
                f"  #{i} {candidate['name']} "
                f"final={candidate['final']:.2f} "
                f"confidence={candidate['confidence']:.3f}"
            )

        print()
        print(f"[F8] SELECTED: {best['name']}")
        print("[F8] FINAL CONSENSUS TEXT:")
        print(final_text)
        print()
        print("[F8] READING...")

        speak(final_text)

        print("[F8] Finished.")

    except Exception as e:
        print("[F8] ERROR:", repr(e))
    finally:
        _turbo_end()



def start():
    # Capture the game/application before the selector takes foreground.
    fg_pid, fg_name = _foreground_pid_and_name()
    if fg_pid and fg_pid != os.getpid():
        print(f"[F8] Foreground app: {fg_name or 'unknown'} (PID {fg_pid})")

    print("\n[F8] SELECT TEXT AREA — drag around the paragraph; ESC cancels.")
    r=select()
    if r:
        threading.Thread(
            target=read,
            args=(r, fg_pid, fg_name),
            daemon=True
        ).start()
    else:
        print("[F8] Selection cancelled.")

last=0
def key(k):
    global last
    now=time.monotonic()
    if k==keyboard.Key.up and now-last>.8:
        last=now; stop(); threading.Thread(target=start,daemon=True).start()
    elif k==keyboard.Key.down:
        stop(); print("[DOWN] Speech stopped; audio restored.")
    elif k==keyboard.Key.right:
        stop(); print("[RIGHT] Exiting."); return False

print("="*72)
print(" FROSTY v24.5 - ULTRA FAST + NATURALER VOICE")
print("="*72)
print(f"Primary monitor: {W} x {H}")
print(f"Voice: {VOICE} | Rate: {RATE} | Pitch: {PITCH}")
print("UP = select/read | DOWN = stop | RIGHT = quit")
print("HDR-safe opaque selector. No fixed Frostpunk coordinates.")
print("OCR: HIGH-CONFIDENCE first-pass acceptance + adaptive consensus.\nGPU TURBO: temporary HIGH Frosty priority + foreground app BELOW_NORMAL during OCR.")
listener=keyboard.Listener(on_press=key); listener.start()
try:
    while True: time.sleep(.2)
except KeyboardInterrupt: pass
finally:
    listener.stop(); stop()
