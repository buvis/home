DOO := "C:/Users/tbouska/bin/doogat/doo/doo.exe"
!#b:: ; bookmark URL
  ClipSaved := ClipboardAll  ; Save current clipboard content to renew it at the end
  Clipboard =  ; Start off empty to allow ClipWait to detect when the text has arrived
  Send ^c  ; Copy the highlighted text to clipboard
  ClipWait  ; Wait for the clipboard to contain text.

  url := Clipboard
  url = %url%

  Run %DOO% create bookmark --with url=%url%

  ClipSaved = ; to free memory
Return

!#i::
  ClipSaved := ClipboardAll  ; Save current clipboard content to renew it at the end
  Clipboard =  ; Start off empty to allow ClipWait to detect when the text has arrived
  Send ^c  ; Copy the highlighted text to clipboard
  ClipWait  ; Wait for the clipboard to contain text.

  url := "https://launchpad.support.sap.com/#/incident/search/" Clipboard  ; Construct the link to SAP Support
  url = %url%  ; Trim the whitespace
  Run %url%  ; Open the browser

  Clipboard := ClipSaved  ; Restore the initial clipboard content
  ClipSaved = ; Free the memory
Return

!#o::
  ClipSaved := ClipboardAll  ; Save current clipboard content to renew it at the end
  Clipboard =  ; Start off empty to allow ClipWait to detect when the text has arrived
  Send ^c  ; Copy the highlighted text to clipboard
  ClipWait  ; Wait for the clipboard to contain text.

  url := "https://launchpad.support.sap.com/#/notes/" Clipboard  ; Construct the link to SAP Support
  url = %url%  ; Trim the whitespace
  Run %url%  ; Open the browser

  Clipboard := ClipSaved  ; Restore the initial clipboard content
  ClipSaved = ; Free the memory
Return

#space:: ; bring terminal
    IfWinExist ahk_exe alacritty.exe
        winactivate ahk_exe alacritty.exe
    else
        run, "C:\Users\tbouska\bin\scoop\alacritty\current\alacritty.exe", "-vv"
    WinWait ahk_exe alacritty.exe
    WinActivate ahk_exe alacritty.exe
    WinWaitActive ahk_exe alacritty.exe
Return

!#s:: ; run favorite apps
Input, key, L1 T1 ; now, wait 1s for keypress to determine what to run
If (ErrorLevel="Timeout")
    Return
Else
    bin := "C:\Users\tbouska\bin\"
    scoop := "C:\Users\tbouska\scoop\apps\"
    If (key="c")
        Run, %scoop%speedcrunch\current\speedcrunch.exe
    Else If (key="d")
        Run, %bin%td3.bat
    Else If (key="q")
        Run, %bin%tq3.bat
    Else If (key="f")
        Run, %bin%start-firefox.bat
    Else If (key="v")
        Run, %scoop%vivaldi\current\Application\vivaldi.exe
    Else If (key="k")
        Run, %scoop%keepass\current\KeePass.exe
    Else If (key="l")
        Run, "C:\Users\tbouska\reference\l\list\adp-lists.xlsx"
Return
