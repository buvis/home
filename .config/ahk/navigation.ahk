!#i::
{
	ClipSaved := ClipboardAll()  ; Save current clipboard content to renew it at the end
	A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
	Send "^c"  ; Copy the highlighted text to clipboard
	ClipWait  ; Wait for the clipboard to contain text.

	url := "https://launchpad.support.sap.com/#/incident/search/" A_Clipboard  ; Construct the link to SAP Support
	url := url  ; Trim the whitespace
	Run url ; Open the browser

	A_Clipboard := ClipSaved  ; Restore the initial clipboard content
	ClipSaved := "" ; Free the memory
	Return
}

!#j::
{
	ClipSaved := ClipboardAll()  ; Save current clipboard content to renew it at the end
	A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
	Send "^c"  ; Copy the highlighted text to clipboard
	ClipWait  ; Wait for the clipboard to contain text.

	url := "https://jira.service.tools-pi.com/browse/" A_Clipboard  ; Construct the link to Jira issue
	url := url  ; Trim the whitespace
	Run url  ; Open the browser

	A_Clipboard := ClipSaved  ; Restore the initial clipboard content
	ClipSaved := "" ; Free the memory
	Return
}

!#o::
{
	ClipSaved := ClipboardAll()  ; Save current clipboard content to renew it at the end
	A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
	Send "^c"  ; Copy the highlighted text to clipboard
	ClipWait  ; Wait for the clipboard to contain text.

	url := "https://me.sap.com/support/article/" A_Clipboard  ; Construct the link to SAP Support
	url := url  ; Trim the whitespace
	Run url  ; Open the browser

	A_Clipboard := ClipSaved  ; Restore the initial clipboard content
	ClipSaved := "" ; Free the memory
	Return
}

!#t::
{
	Send "^c"  ; Copy service request number
	Run "https://esicrm.esi.adp.com/siebel/app/callcenter_sso/enu/?SWECmd=GotoView&SWEView=Service+Request+Screen+Homepage+View&SWERF=1&SWEHo=esicrm.esi.adp.com&SWEBU=1&_tid=1622114720"  ; Open the browser
	Return
}


!#s:: ; run favorite apps
{
	ih := InputHook("L1 T1")
	ih.Start()
	ErrorLevel := ih.Wait()
	
	If (ErrorLevel = "Timeout")
		return
	Else
		bin_locl := "C:\Users\tbouska\.local\bin\"
		If (ih.input="d")
			Run bin_locl "td3.bat"
		Else If (ih.input="e")
			Run "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
		Else If (ih.input="q")
			Run bin_locl "tq3.bat"
		Else If (ih.input="k")
			Run "C:\Users\tbouska\scoop\apps\keepass\current\KeePass.exe"
		Else If (ih.input="l")
			Run "C:\Users\tbouska\OneDrive - Automatic Data Processing Inc\z\reference\list\adp-lists.xlsx"
	Return
}

#Space::
{
	Send "{Blind}{vkE8}"
	If WinExist("ahk_exe wezterm-gui.exe")
		WinActivate "ahk_exe wezterm-gui.exe"
	Else
		Run "C:/Users/tbouska/scoop/apps/wezterm/current/wezterm-gui.exe"
	Return
}