# Setting up the dashboard on a Windows PC — from scratch

This is the **complete, no-experience-needed** walkthrough for getting the iHealth
dashboard running on a Windows computer that has never been used for coding. You'll
download two free programs, click through their installers, then copy-paste a short
list of commands. Take it one step at a time — there's a ✓ check after each step so
you always know it worked.

**Time:** about 20 minutes, most of it waiting on downloads.

**Have ready before you start:** your TLDCRM API credentials — `TLD_BASE_URL`,
`TLD_API_ID`, `TLD_API_KEY`. They live in the `.env` file on your work Mac (in the
`TLDDASHBOARD` folder), or you can get a fresh **read-only** key from your TLD admin
panel. You'll paste them in at Step 6.

---

## Step 1 — Install Python

1. Go to **<https://www.python.org/downloads/>** and click the big yellow
   **"Download Python 3.x.x"** button.
2. Open the file that downloads (it's in your Downloads folder, named like
   `python-3.x.x-amd64.exe`).
3. **VERY IMPORTANT:** on the first installer screen, check the box at the bottom that
   says **"Add python.exe to PATH"** before clicking anything else. This one checkbox
   prevents 90% of beginner headaches.
4. Click **"Install Now"** and let it finish. Click **Close**.

✓ **Check it worked:** Open the Start menu, type **PowerShell**, open it, and type:
```
python --version
```
You should see something like `Python 3.12.4`. (If it instead opens the Microsoft
Store or errors, see *Troubleshooting → "python" doesn't work* at the bottom.)

---

## Step 2 — Install Git

Git is the tool that downloads the code and syncs your changes with your work Mac.

1. Go to **<https://git-scm.com/download/win>** — the download starts automatically
   ("64-bit Git for Windows Setup").
2. Open the downloaded file and click **Next** through every screen — the **default
   options are all fine**. Click **Install**, then **Finish**.

✓ **Check it worked:** in PowerShell, type:
```
git --version
```
You should see something like `git version 2.45.0`.

---

## Step 3 — Open a terminal in the right place

This trick puts you "inside" the folder so you don't have to type long paths:

1. Open **File Explorer** and go to your **Documents** folder (or wherever you'd like
   to keep the project).
2. Click the **address bar** at the top (where it shows the folder path), type
   **`powershell`**, and press **Enter**.
3. A blue **PowerShell** window opens, already pointed at that folder. Use this window
   for the rest of the steps.

---

## Step 4 — Download the code

In that PowerShell window, type (or paste) this and press Enter:
```
git clone https://github.com/kendoric2/TLD-DASHBOARD-.git
```
Then step into the new folder:
```
cd TLD-DASHBOARD-
```

✓ **Check it worked:** type `dir` and press Enter — you should see `src`, `static`,
`templates`, `README.md`, and more. (Note the folder is named **`TLD-DASHBOARD-`** —
that's the GitHub repo name; it's the same project as `TLDDASHBOARD` on your Mac.)

---

## Step 5 — Install the project's dependencies

First create a clean "virtual environment" (keeps this project's pieces tidy):
```
python -m venv venv
venv\Scripts\activate
```
After the second command your prompt line will start with **`(venv)`** — that's how
you know it's on.

Now install the three things the dashboard needs:
```
pip install -r requirements.txt
```

✓ **Check it worked:** the last line says something like
`Successfully installed Flask-3.0.3 requests-2.32.3 python-dotenv-1.0.1`.

---

## Step 6 — Add your credentials

The code came down from GitHub, but your secret keys did **not** (on purpose — they're
never uploaded). You add them once on this PC.

1. Make your own copy of the template:
   ```
   copy .env.example .env
   ```
2. Open it in Notepad to edit:
   ```
   notepad .env
   ```
3. Fill in the three values (copy them from your work Mac's `.env`, or your TLD admin):
   ```
   TLD_BASE_URL=https://yourcompany.tldcrm.com
   TLD_API_ID=your-api-id
   TLD_API_KEY=your-api-key
   ```
4. Save (Ctrl+S) and close Notepad.

---

## Step 7 — Run it!

```
python src\app.py
```
Your browser should pop open at **http://localhost:5050** showing the dashboard. If it
doesn't open on its own, open a browser and go to that address yourself.

Leave the PowerShell window open while you use the dashboard. To stop it, click that
window and press **Ctrl+C**.

**Even easier next time:** open the `bin` folder in File Explorer and **double-click
`start.bat`** — it launches everything for you (it even finds your `venv`
automatically).

✓ **Check you're live, not demo:** go to **http://localhost:5050/health** — it should
say `"live": true`. If you see a yellow **"SAMPLE DATA"** badge on the dashboard, your
`.env` keys aren't being read — re-check Step 6.

---

## Everyday use (and staying in sync with your work Mac)

Everything syncs through GitHub. The rhythm is **pull before you start, push when you
finish** — the exact same git commands as on the Mac.

**When you sit down to work** (open PowerShell in the `TLD-DASHBOARD-` folder):
```
git pull
```

**When you're done making changes:**
```
git add -A
git commit -m "a short note about what you changed"
git push
```

That uploads your work so it's waiting on your Mac, and vice-versa. Your `.env` stays
on each computer and is never synced — set up once per machine and forget it.

> The first time you `git push` from this PC, GitHub will ask you to sign in (a browser
> window or a one-time code). That's normal — do it once and it remembers you.

---

## Troubleshooting

**"python" doesn't work / opens the Microsoft Store.**
Python isn't on your PATH. Easiest fix: re-run the Python installer from Step 1, choose
**Modify**, and make sure **"Add python.exe to PATH"** is checked — or just type **`py`**
instead of `python` everywhere (e.g. `py src\app.py`).

**`venv\Scripts\activate` gives a red "running scripts is disabled" error.**
That's PowerShell's safety setting. Either use **Command Prompt** instead of PowerShell,
or run this once and try again:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**"port 5050 is already in use."**
Something else is on that port. Run it on another one:
```
$env:PORT=5060; python src\app.py
```
then visit http://localhost:5060.

**`git` or `python` "not recognized."**
The install didn't add it to PATH. Close and reopen PowerShell first (PATH only updates
in new windows). If it still fails, reinstall and watch for the PATH checkbox/option.

**Stuck anywhere?** Copy the exact text from the PowerShell window and send it over —
we'll sort it out live.
