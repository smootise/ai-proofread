Clipboard and Hotkey Flow
Hotkey

V1 has one hotkey:

Ctrl+Alt+P = proofread

No undo hotkey in V1.

Recovery behavior

After a successful correction, the original text must be left in the clipboard.

If the user wants to restore the original text and Ctrl+Z does not work, they can manually select the corrected text and press Ctrl+V.

Important detection rule

Do not detect selected text by comparing the old clipboard to the new clipboard.

That fails if the selected text is already identical to the clipboard.

Use this instead:

save clipboard -> clear clipboard -> Ctrl+C -> wait for clipboard content
Full success flow
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

8. Send captured text to Python client/backend.
9. Put corrected_text in clipboard.
10. Paste corrected_text.
11. Put original_text in clipboard.
Failure flow

On failure:

Do not paste anything.
Restore previous clipboard.
Show/log a simple error.
Leave source app untouched.

Failure cases include:

No text captured
Text shorter than MIN_CHARS
Text longer than MAX_CHARS
Backend unreachable
Ollama unreachable
Invalid JSON from model
Missing or empty corrected_text
Timing defaults
CLIPBOARD_TIMEOUT_SECONDS=0.5
PASTE_RESTORE_DELAY_MS=150

Small delays are acceptable because some apps consume clipboard updates asynchronously.