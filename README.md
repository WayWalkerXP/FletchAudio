# I made a terrible mistake. 

Flet is a great UI framework, but it is not designed for the type of information dense layout that this project needs. After spending a few days getting familiar with PyQt6, I've come to realize that it's a much better framework that will allow me to implement a more usable UI that will allow the user to work through their books more quickly and efficiently.

I have started working on a new application that uses PyQt, which can be found here -> https://github.com/WayWalkerXP/alchemist

Fortunately, most of the bones of FletchAudio can be brought directly into the new project, so most of the work will simply be building the UI and wiring in the components from FA. Rather than months, it should only take a few weeks to get something usable.  Great things to come!
# FletchAudio

FletchAudio is a standalone Python/Flet audiobook metadata utility for collecting, reviewing, writing, auditing, and restoring ABS-focused audiobook metadata. Its core logic is split into reusable modules so it can later be integrated into ABS Librarian.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m metadata_collector.app
```

The app starts without command-line arguments, initializes a SQLite database under `~/.fletchaudio/`, loads saved settings, follows the system theme by default, and displays directory selection, rescan, theme controls, and a book grid.

## Selecting a working directory

Use **Select Working Directory** in the app. The scanner recursively detects `.m4b`, `.m4a`, `.mp3`, `.flac`, `.ogg`, `.opus`, and `.aac` files on local, mounted, or network-mounted paths. One audio file is shown as a single-file book; directories with multiple audio files are shown as folder books with expandable tracks.

## Audible title/author search

The title/author workflow builds a query from author plus cleaned album/title. It removes trailing `CD`/`Part` suffixes like `Book - CD 01`, calls Audible's catalog products endpoint, and presents results before any ASIN-specific metadata is fetched.

## Audible ASIN search

The ASIN workflow lets the user edit or confirm an ASIN, then calls Audible's product endpoint with detailed response groups and larger cover image sizes.

## Metadata comparison

Audible JSON is normalized into the `AbsMetadata` model. The UI is designed to show current metadata beside new Audible metadata, with one checkbox per proposed field. Empty Audible values default to unchecked, and metadata is never written without confirmation.

## Restore and audit history

Scans and successful writes store snapshots in SQLite. Every write or restore creates a change group and per-tag metadata change rows. Restore selection uses prior snapshots and selected tags only, so unrelated tags are not silently overwritten.

## Folder mass update

Folder books support preview-based mass update patterns for tags such as title, album, track, disc, narrator, series, and description. Placeholders include `%track%`, `%track:02%`, `%track:03%`, `%disc%`, `%filename%`, `%folder%`, `%album%`, `%author%`, `%narrator%`, `%series%`, `%series_part%`, and `%asin%`.

## Current limitations

This initial implementation provides the standalone architecture, persistence schema, scanner, Audible client/query construction, JSON normalization, Mutagen read/write helpers, history helpers, mass-update preview logic, tests, and a basic Flet grid. Advanced dialogs for comparison, search-result selection, restore inspection, cover download acceptance, and mass-update confirmation are intentionally conservative scaffolding and should be expanded before heavy production use.
