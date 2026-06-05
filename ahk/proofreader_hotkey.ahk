; proofreader_hotkey.ahk
; AutoHotkey v1.1 — Two global proofreading hotkeys
;
; Ctrl+Alt+P       — Fast path: proofread and apply immediately.
; Ctrl+Alt+Shift+P — Review path: proofread, show popup, user decides.
;
; Fast path (Ctrl+Alt+P) clipboard flow per docs/clipboard_flow.md:
;   1. Save current clipboard.
;   2. Clear clipboard.
;   3. Send Ctrl+C (copy selection).
;   4. Wait up to CLIPBOARD_TIMEOUT_SECONDS for clipboard text.
;   5. If empty → Ctrl+A fallback (capture whole field).
;   6. Write captured text to a UTF-8 temp file.
;   7. Run Python client; wait for exit code.
;   8. On exit 0: read output temp file, put corrected_text in clipboard,
;                  Ctrl+V (paste), then put original_text back in clipboard.
;   9. On failure: restore previous clipboard, show tray tip, do nothing else.
;  10. Clean up temp files.
;
; Review path (Ctrl+Alt+Shift+P) clipboard outcome:
;   accept  → paste corrected text; leave CORRECTED text in clipboard.
;   copy    → leave CORRECTED text in clipboard; no paste; no window refocus.
;   reject  → restore previous clipboard; no paste.
;   cancel  → restore previous clipboard; no paste.
;   failure → restore previous clipboard; tray tip.
;
; IMPORTANT: This script never sends {Enter} or {Return} — it will not submit
;            messages in Slack, Discord, or WhatsApp Desktop.

#NoEnv
#SingleInstance Force
#Persistent
SetWorkingDir %A_ScriptDir%\..
SendMode Input

; ---------------------------------------------------------------------------
; Configuration (mirrors .env defaults — edit these to match your .env)
; ---------------------------------------------------------------------------

; Full path to your Python interpreter. Examples:
;   "python"                                    (python on PATH)
;   "C:\Python311\python.exe"
;   "C:\your-repo\.venv\Scripts\python.exe"
PythonExe := "python"

; Path to the fast-path client script, relative to the repo root (SetWorkingDir above).
ClientScript := "client\proofread_client.py"

; Path to the review client script (V2.5), relative to the repo root.
ReviewClientScript := "client\review_client.py"

; Clipboard wait timeout in seconds (matches CLIPBOARD_TIMEOUT_SECONDS=0.5)
; ClipWait accepts fractional seconds.
ClipboardTimeoutSec := 0.5

; Delay (ms) after Ctrl+V before restoring original text to clipboard.
; Gives apps time to consume the clipboard before we overwrite it.
; (matches PASTE_RESTORE_DELAY_MS=150)
PasteRestoreDelayMs := 150

; ---------------------------------------------------------------------------
; Hotkey: Ctrl+Alt+P
; ---------------------------------------------------------------------------

^!p::
    ; --- Save the previous clipboard so we can always restore it on failure ---
    PrevClipboard := ClipboardAll   ; binary snapshot (images, rich text, etc.)

    ; --- Step 1-4: Try to capture selected text ---
    Clipboard := ""
    Send ^c
    ClipWait, %ClipboardTimeoutSec%, 1  ; ,1 = wait for any data (not just text)
    CapturedText := Clipboard
    CaptureMode  := "selected_text"

    ; --- Step 5: Ctrl+A fallback if no selection was captured ---
    if (CapturedText = "")
    {
        Send ^a
        Clipboard := ""
        Send ^c
        ClipWait, %ClipboardTimeoutSec%, 1
        CapturedText := Clipboard
        CaptureMode  := "whole_field"
    }

    ; --- Fail if still empty after fallback ---
    if (CapturedText = "")
    {
        Clipboard := PrevClipboard
        TrayTip, Proofreader, No text captured., 3, 2
        goto Cleanup
    }

    ; --- Step 6: Write captured text to a UTF-8 temp file ---
    ; Use the AHK script PID so concurrent activations don't collide.
    TempIn  := A_Temp . "\proofread_in_"  . A_ScriptPID . ".txt"
    TempOut := A_Temp . "\proofread_out_" . A_ScriptPID . ".txt"

    ; Delete any leftover output file from a previous run.
    if FileExist(TempOut)
        FileDelete, %TempOut%

    ; Write the input file as UTF-8.
    ; FileOpen handle must be stored in a variable; otherwise AHK may
    ; garbage-collect the object before the write is flushed.
    hFile := FileOpen(TempIn, "w", "UTF-8")
    if !hFile
    {
        Clipboard := PrevClipboard
        TrayTip, Proofreader, Failed to write temp input file., 3, 2
        goto Cleanup
    }
    hFile.Write(CapturedText)
    hFile.Close()
    hFile := ""

    ; --- Step 7: Detect active window info ---
    WinGetActiveTitle, ActiveTitle
    WinGetClass, ActiveClass, A
    SourceApp := ActiveClass  ; window class is more stable than title

    ; Strip double-quotes from strings that go on the command line.
    ; (Captured text is passed via file — only these short metadata strings
    ;  are passed as arguments, so sanitising quotes is sufficient.)
    StringReplace, SourceApp,   SourceApp,   `",, All
    StringReplace, ActiveTitle, ActiveTitle, `",, All

    ; --- Step 7b: Run Python client ---
    ; The captured text is never on the command line — it travels via TempIn.
    ; Success is detected by the presence of the output file, not the exit code.
    ; RunWait exit code capture via cmd /c is unreliable in AHK v1.1 (returns
    ; the cmd.exe PID instead of the child process exit code on some Windows versions).
    CmdLine = %PythonExe% "%ClientScript%" --input-file "%TempIn%" --output-file "%TempOut%" --source-app "%SourceApp%" --window-title "%ActiveTitle%" --mode %CaptureMode%

    RunWait, %ComSpec% /c %CmdLine%, , Hide

    ; --- Step 8: On success, paste the corrected text ---
    if (FileExist(TempOut))
    {
        ; Read the output file as UTF-8 (*P65001 = code page 65001 = UTF-8)
        FileRead, CorrectedText, *P65001 %TempOut%

        if (CorrectedText != "")
        {
            ; Put corrected text in clipboard and paste it
            Clipboard := CorrectedText
            ClipWait, 2
            Send ^v
            Sleep, %PasteRestoreDelayMs%

            ; Leave the original text in the clipboard as the recovery fallback.
            ; (per docs/clipboard_flow.md: "original text left in clipboard after success")
            Clipboard := CapturedText
        }
        else
        {
            ; Output file was empty — treat as failure, restore clipboard
            Clipboard := PrevClipboard
            TrayTip, Proofreader, Correction returned empty text., 3, 2
        }
    }
    else
    {
        ; --- Step 9: Failure — restore previous clipboard, no paste ---
        Clipboard := PrevClipboard
        TrayTip, Proofreader, Proofreading failed. Clipboard restored., 3, 2
    }

    ; --- Step 10: Clean up temp files ---
Cleanup:
    if FileExist(TempIn)
        FileDelete, %TempIn%
    if FileExist(TempOut)
        FileDelete, %TempOut%
return

; ---------------------------------------------------------------------------
; Hotkey: Ctrl+Alt+Shift+P — Review path (V2.5)
; ---------------------------------------------------------------------------
;
; Captures text using the same safe clipboard flow as the fast path, then
; opens a pywebview popup for the user to review the proposed correction before
; deciding to accept, copy, or reject.
;
; Decision outcomes (read from the JSON decision temp file):
;   accept  → re-focus original window, paste corrected text, leave CORRECTED in clipboard.
;   copy    → leave CORRECTED text in clipboard only; no paste; no re-focus.
;   reject  → restore previous clipboard; no paste.
;   cancel  → restore previous clipboard; no paste (window closed without action).
;   missing → failure; restore previous clipboard; tray tip.
; ---------------------------------------------------------------------------

^!+p::
    ; --- Save the previous clipboard (binary snapshot) so we can restore on failure ---
    RPrevClipboard := ClipboardAll

    ; --- Store the original window handle for re-focus after the popup closes ---
    WinGet, ROrigHwnd, ID, A

    ; --- Capture selected text ---
    Clipboard := ""
    Send ^c
    ClipWait, %ClipboardTimeoutSec%, 1
    RCapturedText := Clipboard
    RCaptureMode  := "selected_text"

    ; --- Ctrl+A fallback if no selection was detected ---
    if (RCapturedText = "")
    {
        Send ^a
        Clipboard := ""
        Send ^c
        ClipWait, %ClipboardTimeoutSec%, 1
        RCapturedText := Clipboard
        RCaptureMode  := "whole_field"
    }

    ; --- Fail if still empty ---
    if (RCapturedText = "")
    {
        Clipboard := RPrevClipboard
        TrayTip, Proofreader (Review), No text captured., 3, 2
        goto ReviewCleanup
    }

    ; --- Write captured text to a UTF-8 temp input file ---
    RTempIn       := A_Temp . "\proofread_in_"       . A_ScriptPID . ".txt"
    RTempDecision := A_Temp . "\proofread_decision_" . A_ScriptPID . ".json"

    if FileExist(RTempDecision)
        FileDelete, %RTempDecision%

    RhFile := FileOpen(RTempIn, "w", "UTF-8")
    if !RhFile
    {
        Clipboard := RPrevClipboard
        TrayTip, Proofreader (Review), Failed to write temp input file., 3, 2
        goto ReviewCleanup
    }
    RhFile.Write(RCapturedText)
    RhFile.Close()
    RhFile := ""

    ; --- Detect active window metadata ---
    WinGetActiveTitle, RActiveTitle
    WinGetClass, RActiveClass, A
    RSourceApp := RActiveClass

    StringReplace, RSourceApp,   RSourceApp,   `",, All
    StringReplace, RActiveTitle, RActiveTitle, `",, All

    ; --- Run the review client (opens pywebview popup; blocks until popup closes) ---
    RCmdLine = %PythonExe% "%ReviewClientScript%" --input-file "%RTempIn%" --output-file "%RTempDecision%" --source-app "%RSourceApp%" --window-title "%RActiveTitle%" --mode %RCaptureMode%

    RunWait, %ComSpec% /c %RCmdLine%, , Hide

    ; --- Read the decision file ---
    if (!FileExist(RTempDecision))
    {
        ; No decision file = hard failure (backend down, pywebview missing, etc.)
        Clipboard := RPrevClipboard
        TrayTip, Proofreader (Review), Review failed. Clipboard restored., 3, 2
        goto ReviewCleanup
    }

    FileRead, RDecisionJson, *P65001 %RTempDecision%

    ; Parse "decision" field from the JSON using a simple regex approach.
    ; The JSON is always {"decision": "...", "corrected_text": "..."} from our client.
    ; We use a separate temp file for each field to avoid AHK string-handling quirks.
    RDecision := ""
    RCorrectedText := ""

    ; Extract decision value (one of: accept, copy, reject, cancel)
    if RegExMatch(RDecisionJson, """decision""\s*:\s*""([^""]+)""", RMatch)
        RDecision := RMatch1

    ; Extract corrected_text value (may contain escaped chars — we re-read from JSON safely)
    ; For the text content, use a second temp file written by the client instead of parsing.
    ; The client writes the full corrected text; we trust what it wrote to the JSON.
    ; Use a relaxed multi-line regex: match from "corrected_text": " to the next unescaped "
    ; This covers the common case. For robustness, the accept/copy branches also handle
    ; an empty parse by falling back to copy-only mode.
    if RegExMatch(RDecisionJson, """corrected_text""\s*:\s*""((?:[^""\\]|\\.)*)""", RMatch2)
    {
        RCorrectedText := RMatch21
        ; Unescape basic JSON escape sequences: \n \r \t \\  \"
        StringReplace, RCorrectedText, RCorrectedText, \n,  `n,  All
        StringReplace, RCorrectedText, RCorrectedText, \r,  `r,  All
        StringReplace, RCorrectedText, RCorrectedText, \t,  `t,  All
        StringReplace, RCorrectedText, RCorrectedText, \\,  \,   All
        StringReplace, RCorrectedText, RCorrectedText, \",  ",   All
    }

    ; --- Branch on the decision ---

    if (RDecision = "accept")
    {
        if (RCorrectedText = "")
        {
            ; Corrected text parse failed — fall back to copy-only for safety.
            Clipboard := RPrevClipboard
            TrayTip, Proofreader (Review), Could not read corrected text. Clipboard restored., 3, 2
            goto ReviewCleanup
        }

        ; Re-focus the original source window.
        ; If the window no longer exists or cannot be activated, fall back to copy-only.
        WinActivate, ahk_id %ROrigHwnd%
        Sleep, 150
        IfWinActive, ahk_id %ROrigHwnd%
        {
            ; Window is active — safe to paste.
            Clipboard := RCorrectedText
            ClipWait, 2
            Send ^v
            Sleep, %PasteRestoreDelayMs%
            ; Leave the CORRECTED text in the clipboard (user can re-paste manually).
            ; (Different from the fast path, which leaves the original.)
            Clipboard := RCorrectedText
            TrayTip, Proofreader (Review), Correction applied., 2, 1
        }
        else
        {
            ; Could not re-focus — fall back to copy-only so text is not pasted blindly.
            Clipboard := RCorrectedText
            TrayTip, Proofreader (Review), Could not refocus source window. Corrected text copied to clipboard., 4, 2
        }
    }
    else if (RDecision = "copy")
    {
        if (RCorrectedText = "")
        {
            Clipboard := RPrevClipboard
            TrayTip, Proofreader (Review), Could not read corrected text. Clipboard restored., 3, 2
            goto ReviewCleanup
        }
        ; Leave CORRECTED text in clipboard; no paste; no re-focus.
        Clipboard := RCorrectedText
        TrayTip, Proofreader (Review), Corrected text copied to clipboard., 2, 1
    }
    else
    {
        ; reject, cancel, or unrecognised decision → restore previous clipboard.
        Clipboard := RPrevClipboard
        if (RDecision = "reject" or RDecision = "cancel")
            TrayTip, Proofreader (Review), Correction rejected. Clipboard restored., 2, 1
        else
            TrayTip, Proofreader (Review), Unexpected decision. Clipboard restored., 3, 2
    }

ReviewCleanup:
    if FileExist(RTempIn)
        FileDelete, %RTempIn%
    if FileExist(RTempDecision)
        FileDelete, %RTempDecision%
return
