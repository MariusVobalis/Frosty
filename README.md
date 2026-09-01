**Select text on your screen. Hear it read out loud.**

Made for long game paragraphs, quest logs, and any window where you would rather listen than squint.

Drag a box. Wait a couple of seconds. A natural voice reads the text while game audio ducks down.

---

## What it does

| Step | Action |
| --- | --- |
| 1 | Press **Up Arrow** |
| 2 | Drag a box around the text |
| 3 | Frosty OCRs the selection |
| 4 | Microsoft neural voice reads it |
| 5 | Other app volume is lowered while it speaks |

**Down Arrow** stops speech and restores volume.  
**Right Arrow** quits.  
**Esc** cancels the selection box.

No cloud OCR. No account. Screenshot + local PaddleOCR + Edge neural TTS.

---

## Controls

```
UP      select area and read
DOWN    stop speaking
RIGHT   exit
ESC     cancel selection
```

---

## Requirements

- Windows
- Python 3.10+
- Internet the first time Edge TTS downloads a voice file
- NVIDIA GPU recommended for fast OCR  
  CPU works, just slower

---

## Install

1. Install [Python 3.10+](https://www.python.org/downloads/)  
   Tick **Add python.exe to PATH**
2. Put these files in one folder:
   - `Frosty_v24_5_NATURAL_VOICE.py`
   - `RUN_FROSTY.bat`
   - `Launch_Frosty.vbs`
   - `requirements.txt`
3. Double-click **`Launch_Frosty.vbs`** or `RUN_FROSTY.bat`

The launcher installs the Python packages and starts Frosty.

### Optional: build a Windows exe

On **your** Windows PC (not from this chat):

1. Open the folder
2. Double-click `build_exe.bat`
3. Wait. First build is slow
4. Run `dist\Frosty\Frosty.exe`

Keep the whole `dist\Frosty` folder. The exe is not a tiny single file. PaddleOCR makes it large.

If you prefer manual install:

```bat
pip install pycaw comtypes opencv-python psutil mss pillow pynput edge-tts pygame paddleocr numpy
python Frosty_v24_5_NATURAL_VOICE.py
```

---

## First run

The first start is slow. PaddleOCR loads detection + recognition models.

After that:

1. Open the game or window
2. Press **Up**
3. Drag around the paragraph
4. Let it speak

Use a tight box. Less empty UI = cleaner reading.

---

## Notes

- Built for dense game text (Frostpunk-style paragraphs), then opened to any screen region
- HDR-safe selector: it captures a still frame so the overlay does not go black
- During OCR it briefly raises its own process priority
- Some anti-cheat games dislike screen capture tools. Use at your own risk
- Voice: `en-US-ChristopherNeural`

---

## Donate

Frosty is free.

If it saves you from another wall of quest text, send a tip:

**(https://revolut.me/marektmhq)**

Passion project. If it gets used, I’ll keep building on it.

---

## License

Use it, share it, break it, improve it.  
Credit is nice. Not required.
