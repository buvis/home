DOO := "C:/Users/tbouska/.local/bin/doogat/doo/doo.exe"
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

!#t::
  Send ^c  ; Copy service request number
  Run "https://esicrm.esi.adp.com/siebel/app/callcenter_sso/enu/?SWECmd=GotoView&SWEView=Service+Request+Screen+Homepage+View&SWERF=1&SWEHo=esicrm.esi.adp.com&SWEBU=1&_tid=1622114720"  ; Open the browser
Return


!#s:: ; run favorite apps
Input, key, L1 T1 ; now, wait 1s for keypress to determine what to run
If (ErrorLevel="Timeout")
    Return
Else
    bin_locl := "C:\Users\tbouska\.local\bin\"
    If (key="d")
        Run, %bin_locl%\td3.bat
    Else If (key="e")
        Run, "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    Else If (key="q")
        Run, %bin_locl%\tq3.bat
    Else If (key="k")
        Run, "C:\Program Files (x86)\KeePass Password Safe 2\KeePass.exe"
    Else If (key="l")
        Run, "C:\Users\tbouska\OneDrive - Automatic Data Processing Inc\z\reference\list\adp-lists.xlsx"
Return

#Space::
    WinActivate, ahk_exe C:/Users/tbouska/scoop/apps/alacritty/current/alacritty.exe
Return
