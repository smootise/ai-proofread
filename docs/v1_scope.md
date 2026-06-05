V1 Scope ✅ Complete
Goal

Build a Windows proof-of-concept proofreader that can be triggered from most apps with a global hotkey.

The first version focuses on reliable input manipulation, local correction, and correction logging. It does not need a polished UI.

Target apps

Manual testing should cover:

Notepad
Firefox text inputs
Slack
Discord
WhatsApp Desktop
User workflow
User selects text or places cursor in an input field.
User presses Ctrl+Alt+P.
App tries to copy selected text.
If no selected text is detected, app falls back to Ctrl+A and copies the whole field.
Text is sent to the backend.
Backend returns structured JSON.
Client pastes only corrected_text.
Original text is placed in the clipboard as a manual recovery fallback.
Correction behavior

The correction engine should:

Preserve original language.
Preserve tone.
Preserve line breaks.
Fix spelling and grammar only.
Avoid style rewrites.
Avoid making casual text overly formal.
Never translate text unless absolutely necessary, which should almost never happen.
V1 non-goals

Do not implement:

Review popup
Web UI (delivered in V2)
Correction history UI (delivered in V2)
Per-correction accept/reject
ML or clustering
Preference learning
Rich-text preservation
macOS support
Cloud APIs
Browser extension
TrueNAS deployment files unless explicitly requested
Success criteria

V1 is successful if:

It works reliably in Notepad and most target apps.
It handles selected text.
It handles whole-field fallback.
It does not send/submit messages.
It restores the previous clipboard on failure.
It leaves the original text in the clipboard after success.
It logs correction events to SQLite.
It fails safely when backend/Ollama/JSON parsing fails.
V1 bugfixes (shipped after initial implementation)

AHK exit code unreliability: RunWait exit code capture via cmd /c returns the cmd.exe PID
instead of the child process exit code on some Windows versions. Fixed by detecting success
via the presence of the output temp file instead.

Client .env loading: proofread_client.py now resolves .env relative to the repo root
(via the script's own path) rather than relying on the working directory, so it works
correctly regardless of where it is invoked from.

UTF-8 BOM in stored text: AutoHotkey's FileOpen writes files with a UTF-8 BOM on some
Windows configurations. The BOM was stored verbatim in original_text and caused the V2
diff view to show the first word as a spurious correction. Fixed by stripping the BOM
in the diff renderer (existing stored data handled automatically, no migration needed).