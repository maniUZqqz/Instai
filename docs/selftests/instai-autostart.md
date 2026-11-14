# Acceptance run for 0.12.0: InstAI starts by itself and updates itself (on the owner's GPU PC)

Everything is automatic after ONE double-click of the fresh `START.bat` (the folder from an old ZIP cannot update itself: replace it once with the ZIP of `main`, copying `data`, `.env`, `models`, `tools` over). These are the checks.

| Check | How | Pass |
|---|---|---|
| Shortcut registered | double-click `START.bat`; then `Win+R` -> `shell:startup` | a minimized shortcut named `InstAI` is there; the console said "InstAI will start by itself when you log in to Windows" |
| Starts at logon | sign out and in (or restart) | within a minute `http://127.0.0.1:8765` answers; no browser window and no console window stay open; `data\logs\update.log` has a fresh line |
| Updates at logon | after a new commit on `main`: sign out and in | `update.log` says "updated InstAI vX -> vY" or "is up to date"; never a traceback; the server runs the new version (badge) |
| Off switch | double-click `Autostart-Off.bat`, restart Windows | the shortcut is gone and InstAI does not start; `Autostart-On.bat` brings it back |
| No second copy | double-click `START.bat` while it already runs | it says it is already running and opens the browser; the port 8765 is held by one server |
| Next to the agent | start the NMarketing node too (its own shortcut) | Models page -> "Living next to NMarketing": agent running; ports 8188 / 11434 "open (in use)"; no second ComfyUI; after 90 s without GPU work InstAI's voice servers (if it started any) are gone from Task Manager and the card is free |
