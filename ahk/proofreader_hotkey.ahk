; proofreader_hotkey.ahk
; AutoHotkey v1.1 — Ctrl+Alt+P global proofreading hotkey
;
; Full clipboard flow per docs/clipboard_flow.md:
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

; Path to the client script, relative to the repo root (SetWorkingDir above).
ClientScript := "client\proofread_client.py"

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
