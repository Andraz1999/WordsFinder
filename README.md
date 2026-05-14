(The project is still in beta)

# Words Finder

**Words Finder** is a desktop application for Japanese learners that connects to your Anki decks, scans subtitle files (`.srt` / `.ass`), and produces a filtered list of words that appear in the subtitles but that you don't know yet — along with the sentences they appear in. It is designed to be used alongside [Anki](https://apps.ankiweb.net/) and the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation (Windows)](#installation-windows)
- [Installation (macOS)](#installation-macos)
- [Installation (Linux)](#installation-linux)
- [First Launch — Initial Setup](#first-launch--initial-setup)
- [Main Screen](#main-screen)
- [Subtitle Results (Subs Page)](#subtitle-results-subs-page)
- [Kanji Stats](#kanji-stats)
- [Words Stats](#words-stats)
- [Settings](#settings)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Parsing Modes: Orth-base vs Lemma](#parsing-modes-orth-base-vs-lemma)
- [Background Images](#background-images)
- [Data Storage](#data-storage)
- [Advanced: CLI Usage](#advanced-cli-usage)
- [Tech Stack](#tech-stack)

---

## Features

- **Anki sync** — reads all cards from your configured decks and extracts the words/kanji you already know.
- **Subtitle scanning** — scans all `.srt` and `.ass` files in a folder (including subfolders) and finds every word you don't know yet.
- **Sentence context** — for each unknown word, the app stores every sentence it appears in along with the subtitle file title and timestamp.
- **Kanji tracker** — shows which kanji from your subtitles you already know and which you don't, sortable by school grade or RTK order.
- **Word list** — a paginated view of all words pulled from your Anki decks, sortable by frequency.
- **New subtitles export** — save selected sentences to an output `.srt` file to feed into tools like [subs2srs](https://subs2srs.sourceforge.net/) for card creation.
- **LLM prompt generator** — copies a ready-made prompt (with 200 unknown words) to clipboard for pasting into an AI assistant to get readings and meanings quickly.
- **Two parsing modes** — orthographic-base and lemma, so you can control how word variants are matched.
- **English / Japanese UI.**
- **Dark and light themes**, with optional custom background images per subtitle collection.

---

## Prerequisites

Before installing Words Finder you need:

1. **[Anki](https://apps.ankiweb.net/)** — the flashcard application. Must be running whenever you sync.
2. **[AnkiConnect](https://ankiweb.net/shared/info/2055492159)** — an Anki add-on (code `2055492159`) that exposes a local API the app uses to read your cards.
   - Install it from inside Anki: *Tools → Add-ons → Get Add-ons…* and enter the code above.
   - The default AnkiConnect URL is `http://localhost:8765`. Leave this as-is unless you have changed it manually.

---

## Installation (Windows)

> **Requires Windows 10 or later** (64-bit)

1. Download **`WordsFinderSetup.exe`** from the [Releases](../../releases) page.
2. Run the installer and follow the prompts. The installation is roughly **1 GB** — the majority of the space is the [UniDic](https://clrd.ninjal.ac.jp/unidic/) dictionary used for Japanese tokenisation.
3. Launch **Words Finder** from the Start Menu or the desktop shortcut.

All user data (configuration, word databases, scan results) is stored in `%AppData%\Roaming\WordsFinder` and is never affected by updating or reinstalling the app.

---

## Installation (macOS)

> **Requires macOS 13 (Ventura) or later** — supports both Apple Silicon (M1/M2/M3/M4) and Intel Macs

1. Download **`WordsFinder-macOS.zip`** from the [Releases](../../releases).
2. Unzip the file — you will get **`WordsFinder.app`**.
3. Drag **`WordsFinder.app`** into your **Applications** folder.
4. Double-click it to launch.

> **First launch — security warning**
>
> Because the app is not signed with an Apple Developer certificate, macOS will block it the very first time with a message like *"WordsFinder cannot be opened because the developer cannot be verified."*
>
> To get past this **one time only**:
> 1. Right-click (or Control-click) **`WordsFinder.app`**
> 2. Select **Open** from the context menu
> 3. Click **Open** in the dialog that appears
>
> After that, you can open the app normally by double-clicking it.

All user data (configuration, word databases, scan results) is stored in `~/Library/Application Support/WordsFinder` and is never affected by updating or reinstalling the app.

---

## Installation (Linux)

> **Requires a GTK3 desktop environment with WebKit2GTK** — Ubuntu 22.04+ / Debian 11+ or equivalent

### Option A — AppImage (recommended, double-click)

1. Download `WordsFinder.AppImage` from the [Releases](../../releases) page.
2. Make it executable (one time only):
```bash
   chmod +x WordsFinder.AppImage
```
3. Double-click it in your file manager, or run it from the terminal:
```bash
   ./WordsFinder.AppImage
```

First launch registers the app icon in your system so it appears correctly in file managers and the app launcher going forward.

> **Required system packages** (Ubuntu/Debian — install once):
> ```bash
> sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
> ```
> On Ubuntu 22.04 replace `gir1.2-webkit2-4.1` with `gir1.2-webkit2-4.0`.

---

### Option B — Tarball (manual extract)

1. Download `WordsFinderSetup.tar.gz` from the [Releases](../../releases) page.
2. Extract and launch:
```bash
   tar -xzf WordsFinderSetup.tar.gz
   cd WordsFinder
   ./WordsFinder.sh
```
   `WordsFinder.sh` checks for the required GTK packages and installs any that are missing before launching.

---

### Option C — From source

```bash
# 1. Create a virtual environment using the SYSTEM Python (required for GTK)
/usr/bin/python3 -m venv --system-site-packages venv
source venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Download the UniDic dictionary (~600 MB, one time)
python -m unidic download

# 4. Run
python main.py
```

---

## First Launch — Initial Setup

### Step 1 — Language selection

On first launch you will be asked to choose between **English** and **日本語** for the UI language. This can be changed later in Settings.

### Step 2 — Deck & field configuration

You must tell Words Finder which Anki deck(s) to read from and which field within each note type contains the Japanese word.

| Field | What to enter |
|---|---|
| **Deck** | The exact name of your Anki deck (e.g. `Japanese`) |
| **Field** | The note field that holds the word (e.g. `Expression`) |

**Tips:**

- If one deck contains multiple note types with different field names (e.g. `Expression` on some cards and `Sentence` on others), add a separate row for each combination.
- It is strongly recommended to maintain **two decks**: a large archive deck (cards you no longer add to) and a smaller active deck where new cards go. After the first sync, configure Words Finder to watch only the active deck — the app only fetches cards newer than the last sync timestamp, so pointing it at a huge static deck wastes time on every subsequent sync.
- Scanning 9,000 cards takes approximately 3 minutes on a typical machine.

You can add up to 9 deck/field pairs. Click **OK** to save and continue to the main screen.

---

## Main Screen

The main screen has three functional areas:

### Toolbar (top right)

| Button | Description |
|---|---|
| **Sync Anki** | Connects to AnkiConnect and fetches all cards from the configured decks. Extracts words and kanji from the configured fields. Only cards newer than the last sync are fetched on subsequent runs. Anki must be open. |
| **Scan Subs** | Tokenises all subtitle files in the configured input folder and finds every word that appears in the subtitles but is not in your Anki word list. |
| **Path field** | The folder path to your subtitle files. All `.srt` and `.ass` files in the folder and its subfolders are processed. The name of the top-level folder is used as the title of the resulting collection card. |
| **Browse** | Opens a folder picker dialog to set the subtitle input path. |
| **Settings (⚙)** | Opens the Settings page. |

### Subtitle collections grid

Each scanned subtitle folder appears as a card showing the collection name and your current comprehension percentage (words you know ÷ total words). Click a card to open the full word and sentence view. Right-click a card to delete it.

### Stats section

Two navigation panels at the bottom of the screen:

- **漢 Kanji** — opens the Kanji Stats page.
- **語 Words** — opens the Words Stats page.

---

## Subtitle Results (Subs Page)

Clicking a collection card opens the detailed results page for that subtitle folder.

### Toolbar

| Button | Description |
|---|---|
| **Rescan** | Re-runs the subtitle scan for this specific collection (useful after syncing new Anki cards). |
| **Prompt** | Copies a prompt to your clipboard containing up to 200 of the unknown words with an instruction for an LLM (e.g. ChatGPT or Claude) to return readings and meanings. |
| **Search / Ctrl+F** | Filters the word list by the text you type. |

### Word list (left panel)

Each word entry shows:

- The **word** itself.
- A **count** of how many times it appears across all subtitle files in the collection.
- An **Already Know** button — marks the word as known, removes it from this collection, and adds it to your known-words database in the currently active parsing mode.
- **Right-click → Delete** — removes the word from this collection without marking it as known.

### Sentence list (right panel)

Clicking a word in the left panel populates the sentence panel with every sentence that word appears in. Each row shows:

| Column | Description |
|---|---|
| **Title** | The subtitle filename / show title |
| **Timestamp** | The start time of the subtitle line |
| **Sentence** | The full subtitle line containing the word |
| **Add to output** | Writes this subtitle line to the configured output `.srt` file (requires an output folder to be set in Settings) |
| **Copy** | Copies the sentence to clipboard. Right-clicking a sentence row also copies it. |

### Workflow tip — creating new Anki cards from subtitles

1. Set an **output folder** in Settings.
2. In the sentence panel, click **Add to output** for any sentence you want to study.
3. The sentence is appended to an `.srt` file in the output folder, named after the collection.
4. Import that `.srt` into **subs2srs** to generate Anki cards with audio and screenshots automatically.

---

## Kanji Stats

The Kanji page shows all kanji encountered in your subtitle files, divided into:

- **Known** — kanji found in your Anki cards.
- **Unknown** — kanji not yet in Anki.

### Sorting

| Option | Description |
|---|---|
| **Grade** | Japanese school grade order (Grade 1 → Grade 6 → Secondary → Other) |
| **RTK** | Remembering the Kanji (Heisig) order |

The sort preference is saved to your config automatically.

### Search

Press `Ctrl+F` (or click the search bar) to filter kanji by character. Matching tiles are shown across all sections with their original numbers preserved. Press `Escape` to clear the search and return to the normal view.

---

## Words Stats

The Words page shows all words extracted from your Anki cards.

- Words are displayed in a paginated grid (up to 500 per page). Use the navigation buttons at the top and bottom to move between pages.
- Words marked as **Already Know** via the Subs page appear in a separate "Known" section.
- Use the **Descending / Ascending** sort buttons to reorder by frequency.
- Press `Ctrl+F` (or click the search bar) to filter words by text. Matching tiles are shown across all pages with their original numbers preserved. Press `Escape` to clear the search and return to the normal view.

---

## Settings

Access Settings via the ⚙ icon on the main screen.

### Decks & Fields

Same interface as the initial setup screen. After your first Anki sync, it is best practice to configure only your active (new-card) deck here so that subsequent syncs stay fast.

> ⚠ The app only fetches cards **newer than the last sync**. If you remove a deck from the list and later want to include older cards from it, you will need to **Reset Database** first and re-sync everything.

### Subtitle Paths

| Setting | Description |
|---|---|
| **Input folder** | Default folder to scan for subtitle files (same as the path field on the main screen). |
| **Output folder** | Where exported subtitle lines are saved. Required for the **Add to output** button in the Subs page. If not set, that button is disabled. |

### Brackets setting

When **Ignore in brackets** is enabled, any text inside the following bracket types is excluded from word and kanji extraction:

- Half-width and full-width parentheses `()` `（）`
- Half-width and full-width square brackets `[]` `［］`
- Curly braces `{}` `｛｝`
- Angle brackets `<>` `＜＞`
- Lenticular brackets `【】`
- Tortoise-shell brackets `〔〕`
- Angle brackets `〈〉` `《》`

Text inside Japanese corner brackets `「」` and white corner brackets `『』` is **always** included regardless of this setting.

### Parsing Mode

See [Parsing Modes](#parsing-modes-orth-base-vs-lemma) below.

### Language

Switch between English and Japanese UI at any time.

### Visuals

Toggle between **dark** and **light** mode.

### Background folder

Choose a folder of images to use as thumbnails/backgrounds for your subtitle collection cards. The image filename (without extension) must exactly match the collection title (the subtitle folder name). If no matching image is found, the default icon is shown.

### Reset Database

Deletes all stored word and kanji data. Subtitle collection results (the scan output files) are **not** deleted — remove those manually by right-clicking a collection card on the main screen and choosing Delete.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl +` | Zoom in |
| `Ctrl -` | Zoom out |
| `Ctrl 0` | Reset zoom |
| `Ctrl R` | Reload the current page |
| `Ctrl F` | Search / filter words on the Subs, Words, and Kanji pages |

---

## Parsing Modes: Orth-base vs Lemma

Words Finder tokenises Japanese text using [fugashi](https://github.com/polm/fugashi) with the UniDic dictionary. Each word can be stored in one of two modes, and you can switch between them at any time in Settings. **Both modes are updated simultaneously** on every Anki sync and subtitle scan.

| Mode | Behaviour |
|---|---|
| **Orth-base** | Treats different written forms of a word as separate word, e.g. 嵌る and ハマる are counted as two distinct entries. |
| **Lemma** | Groups all written forms of the same word together, e.g. 嵌る and ハマる are counted as one entry. |

The **Already Know** button on the Subs page adds the word only to the **currently active** parsing mode's database. If you switch modes, you may need to re-mark some words.

---

## Background Images

To add custom artwork to your collection cards:

1. Prepare a folder of image files (`.jpg`, `.png`, etc.).
2. In Settings → **Background folder**, select that folder.
3. Name each image file to exactly match the subtitle collection title.
   - Example: if your subtitle folder was called `Spirited Away`, the image should be named `Spirited Away.jpg`.
4. If no matching image is found, the default icon is displayed instead.

---

## Data Storage

User data is stored at a platform-specific location and is never affected by updating or reinstalling the app:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\WordsFinder\` |
| Linux | `~/.local/share/WordsFinder/` |
| macOS | `~/Library/Application Support/WordsFinder/` |

The folder structure is the same across all platforms:

```
WordsFinder/
├── config.json              # App configuration (decks, paths, settings)
├── ui_config.json           # UI preferences (language, theme, background folder)
└── data/
    ├── anki_words_lemma.jsonl       # Words database — lemma mode
    ├── anki_words_orth_base.jsonl   # Words database — orth-base mode
    ├── kanji/
    │   ├── kanji_static.json        # Read-only kanji reference data (bundled)
    │   └── kanji_dynamic.json       # Your known-kanji database (written at runtime)
    └── new_words/
        └── <CollectionName>/        # Subtitle scan results per collection
```

To fully reset to a clean state, delete the `WordsFinder` folder from the path above.

---

## Advanced: CLI Usage

Words Finder also exposes a command-line interface. Run it from a terminal in the installation directory or, if running from source, from the project root.

**Windows:**
```
python main.py [--config PATH] <command>
```

**Linux (AppImage):**
```
./WordsFinder.AppImage [--config PATH] <command>
```

| Command | Description |
|---|---|
| `sync-anki` | Fetch new cards from Anki |
| `scan-subs` | Scan subtitle files for new words |
| `mark-known <word>` | Mark a specific word as known |
| `remove-word <folder> <word>` | Remove a word from a subtitle collection |
| `delete-results <folder>` | Delete a subtitle collection result folder |
| `subtitle-stats <folder>` | Print comprehension statistics for a collection |
| `kanji-stats [--sort RTK]` | Print kanji statistics (optional RTK sort) |
| `reset` | Delete all word and kanji databases (prompts for confirmation) |

---

## Tech Stack

| Component | Library |
|---|---|
| Japanese tokenisation | [fugashi](https://github.com/polm/fugashi) + [UniDic](https://clrd.ninjal.ac.jp/unidic/) |
| Web UI framework | [Flask](https://flask.palletsprojects.com/) |
| Desktop window | [pywebview](https://pywebview.flowrl.com/) |
| Anki integration | [AnkiConnect](https://ankiweb.net/shared/info/2055492159) |
| Frontend styling | [Tailwind CSS](https://tailwindcss.com/) |