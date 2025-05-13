; Selecting
#a::Send "^a"

; Copying
#c::
{
  A_Clipboard := ""
  Send "^c"  ; Copy the highlighted text to clipboard
  ClipWait  ; Wait for the clipboard to contain text.

  cleanText := Trim(A_Clipboard, "`r`n")
  A_Clipboard := cleanText

  Return
}

; Finding
#f::Send "^f"

; Opening
#o::Send "^o"

; Command palette
#p::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "explorer.exe")
  {
    Suspend(True)
          Send "#p"
    Suspend(False)
  }
  else if (ActivePName = "Code.exe")
  {
    Send "^P"
  }
  else {
    Send "!p"
  }
  Return
}

; Close windows (cmd + q to Alt + F4)
#q::Send "!{F4}"

; Save
#s::Send "^s"

; New tab
#t::Send "^t"

; Pasting
#v::Send "^v"

; Close tab
#w::Send "^w"

; Cutting
#x::Send "^x"

; Redo
#y::Send "^y"

; Undo
#z::Send "^z"

; Remap Windows + Tab to Alt + Tab.
; Lwin & Tab::AltTab

; Map fn keys to right option

RAlt & F7::Send "{Media_Prev}"
RAlt & F8::Send "{Media_Play_Pause}"
RAlt & F9::Send "{Media_Next}"
RAlt & F10::SendInput "{Volume_Mute}"
RAlt & F11::SendInput "{Volume_Down}"
RAlt & F12::SendInput "{Volume_Up}"

; Move on line
#Left::Send "{Home}"
#Right::Send "{End}"

; Language switching
^Space::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "eclipse.exe")
  {
    Suspend(True)
      Send "{Ctrl down}{Space}{Ctrl up}"
    Suspend(False)
  } else {
    Send "{Ctrl down}{Shift}{Ctrl up}"
  }
  Return
}

; Disable alone press of windows key
; https://stackoverflow.com/questions/69143107/how-to-disable-the-win-key-if-its-the-only-key-being-pressed-using-autohotkey
~LWin::Send "{Blind}{vkE8}"

; Special characters
!6::§

; Align Obsidian hotkeys
;
; add to daily note
!#l::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "Obsidian.exe")
  {
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
    Suspend(True)
          Send "^!l"
    Suspend(False)
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
  }
  Return
}
;
; Switch editing/reading
#e::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "Obsidian.exe")
  {
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
    Suspend(True)
          Send "^e"
    Suspend(False)
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
  }
  Return
}

;
; Omnisearch
+#f::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "Obsidian.exe")
  {
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
    Suspend(True)
          Send "+^f"
    Suspend(False)
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
  }
  Return
}
;
; Use template
!#t::
{
  ActivePName := WinGetProcessName("A")
  if (ActivePName = "Obsidian.exe")
  {
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
    Suspend(True)
          Send "^!t"
    Suspend(False)
    DetectHiddenWindows True
    WM_COMMAND := 0x0111
    ID_FILE_SUSPEND := 65404
    PostMessage WM_COMMAND, ID_FILE_SUSPEND,,, "C:\Users\tbouska\.local\ahk\typephrase.ahk ahk_class AutoHotkey"
  }
  Return
}
