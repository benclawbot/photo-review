# Photo Review

A local Windows gallery for reviewing files in `~/Downloads/Photos`. It supports browser previews where available, keyboard selection, date groups from EXIF capture metadata, and moving confirmed selections to the Windows Recycle Bin.

## Run

```powershell
python -m pip install -r requirements.txt
python photo-review.py
```

The app listens only on `127.0.0.1:8765` and opens the gallery in your browser. Press `Ctrl+C` in the terminal to stop it. Files without EXIF capture dates appear in the undated group.

## Keyboard

- Arrow keys: move through the gallery
- Space: select or deselect the current file
- Delete: open the confirmation for selected files

Deletion sends files to the Windows Recycle Bin after confirmation.
