# Jackson Williams - Smart Image Resizer

Crops and resizes product photos to a chosen size (default 1087 × 1087 px),
auto-centering on the product, with arrow-key fine-tuning.

## For users (Mac)

1. Unzip the download and drag **Photo Resizer** into **Applications**.
2. First launch only — macOS will say it can't verify the app:
   - Click **Done** (not "Move to Trash").
   - Open **System Settings → Privacy & Security**, scroll to the bottom,
     and click **Open Anyway** next to "Photo Resizer", then confirm.
   - This is a one-time step. After that it opens like any other app.
3. If macOS asks to let the app access your Documents / Desktop / Downloads
   folder, click **Allow** (it needs this to read your photos).

Which download? Apple menu → **About This Mac**. If it says "Chip: Apple M…",
use the **AppleSilicon** build. If it says "Processor: Intel…", use **Intel**.

## For users (Windows)

Unzip and double-click **Photo Resizer.exe**. If Windows shows "Windows
protected your PC", click **More info → Run anyway** (one time).

## Using it

1. **Input** → choose the folder of photos. **Output** defaults to a `resized`
   folder inside it (originals are never touched).
2. Check the size (default 1087 × 1087) and format.
3. Each photo opens already centered. Nudge with the arrow keys
   (Shift = faster, + / − = zoom), then press **Enter** to save and move on.
   "Save all remaining" skips the review step.

## For Jackson/other devs: building the apps

Mac apps can only be built on a Mac, so this repo builds everything in the
cloud with GitHub Actions (free for public repos; private repos get a monthly
allowance, and Mac minutes count extra).

1. Create a GitHub repo and upload everything in this folder. The
   `.github/workflows/build.yml` file must keep that exact path. Tip: in the
   GitHub web UI use **Add file → Create new file**, type
   `.github/workflows/build.yml` as the name, and paste the contents.
2. Open the **Actions** tab → **Build apps** → **Run workflow**.
3. After ~5–10 minutes, open the finished run and download the three artifacts
   (Mac Apple Silicon, Mac Intel, Windows). Each is a zip containing the zip
   you share.
4. Share via your company drive or a link — not email (see below).

### Run from source instead
```
python -m pip install -r requirements.txt
python photo_resizer.py
```

### Changing things
- Colors, brand name, default size, threshold, center mode: constants at the
  top of `photo_resizer.py`.
- After editing, re-run the workflow to get fresh builds.
