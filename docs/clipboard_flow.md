Clipboard and Hotkey Flow

Two hotkeys
V2.5 adds a second hotkey:

Ctrl+Alt+P       = fast path: proofread and paste immediately (original text left in clipboard).
Ctrl+Alt+Shift+P = review path: proofread, open popup, user decides.

No undo hotkey in either path.

Recovery behavior

Fast path (Ctrl+Alt+P):
After a successful correction, the original text is left in the clipboard.
If the user wants to restore the original text and Ctrl+Z does not work, they can manually
select the corrected text and press Ctrl+V (original text is in the clipboard).

Review path — Accept & apply (Ctrl+Alt+Shift+P + user clicks "Accept & apply"):
The corrected text is left in the clipboard after pasting. The user can re-paste manually
if needed. The original text is NOT left in the clipboard on this path.

Review path — Copy only:
The corrected text is placed in the clipboard. No paste is performed.
This is a safe fallback for apps where automatic paste after refocus is unreliable.

Review path — Reject / Cancel:
The previous clipboard is restored. Nothing is pasted.

Clipboard state summary

| Outcome                      | Clipboard after | Paste? | Refocus? |
|------------------------------|-----------------|--------|----------|
| Fast path success            | original text   | yes    | n/a      |
| Review: Accept & apply       | corrected text  | yes    | yes      |
| Review: Copy corrected text  | corrected text  | no     | no       |
| Review: Reject / Cancel      | previous        | no     | no       |
| Any failure                  | previous        | no     | n/a      |

Important detection rule

Do not detect selected text by comparing the old clipboard to the new clipboard.

That fails if the selected text is already identical to the clipboard.

Use this instead:

save clipboard -> clear clipboard -> Ctrl+C -> wait for clipboard content

Fast path full success flow (Ctrl+Alt+P)
1. Save current clipboard.
2. Clear clipboard.
3. Send Ctrl+C.
4. Wait for clipboard text.

5. If clipboard contains text:
   - mode = selected_text
   - use captured text

6. If clipboard is empty:
   - Send Ctrl+A.
   - Clear clipboard.
   - Send Ctrl+C.
   - Wait for clipboard text.
   - If clipboard contains text:
     - mode = whole_field
     - use captured text

7. If no text was captured:
   - restore previous clipboard
   - fail safely

8. Write captured text to a UTF-8 temp file. Run Python client via cmd /c; wait for it to exit.
9. Detect success by the presence of the output temp file (not the exit code — RunWait exit
   code capture via cmd /c is unreliable on some Windows versions and returns the cmd.exe PID
   instead of the child process exit code).
10. If the output file exists and is non-empty: put corrected_text in clipboard, Ctrl+V, then
    put original_text in clipboard as the recovery fallback.
11. Clean up temp files.

Review path full success flow (Ctrl+Alt+Shift+P)
1-7. Same clipboard capture as the fast path.
     Additionally: WinGet captures the source window handle before any clipboard ops.
8. Write captured text to a UTF-8 temp input file.
9. Run review_client.py via cmd /c (opens pywebview popup; blocks until popup closes).
10. On return, read the JSON decision file:
    {"decision": "accept"|"copy"|"reject"|"cancel", "corrected_text": "..."}
    - If file is absent: hard failure (backend/pywebview error) → restore previous clipboard.
    - accept → re-focus original window via stored hwnd; if focus confirmed → paste corrected text;
               if focus fails → fall back to copy-only; leave corrected text in clipboard.
    - copy   → leave corrected text in clipboard; no paste; no re-focus.
    - reject / cancel → restore previous clipboard; no paste.
11. Clean up temp files (input + decision JSON).

Refocus safety:
The review path stores the source window handle (hwnd) at capture time. On accept, it uses
WinActivate + IfWinActive to confirm focus before sending Ctrl+V. If the original window no
longer exists or cannot be activated, the hotkey falls back to copy-only mode and shows a
tray tip. It never pastes into an unknown window.

Failure flow (both paths)

On failure:

Do not paste anything.
Restore previous clipboard.
Show tray tip error message.
Leave source app untouched.

Failure cases include:

No text captured
Failed to write temp input file
Output file absent or empty after client exits (fast path)
Decision file absent after review client exits (review path)
Text shorter than MIN_CHARS
Text longer than MAX_CHARS
Backend unreachable
Ollama unreachable
Invalid JSON from model
Missing or empty corrected_text
pywebview / WebView2 runtime missing or failed to launch (review path)
Refocus failure → copy-only fallback, not a hard failure

Timing defaults
CLIPBOARD_TIMEOUT_SECONDS=0.5
PASTE_RESTORE_DELAY_MS=150

Small delays are acceptable because some apps consume clipboard updates asynchronously.

WebView2 Runtime (review path only)
The review popup requires the Microsoft Edge WebView2 Runtime:
https://developer.microsoft.com/en-us/microsoft-edge/webview2/
If it is not installed, the review client logs an error and exits; AHK restores the clipboard.
