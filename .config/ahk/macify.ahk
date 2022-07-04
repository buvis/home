; Copy & paste, but don't break Windows Terminal
#c::
{
	ActivePName := WinGetProcessName("A")
	if (ActivePName = "WindowsTerminal.exe")
	{
	  Send "^+c"
	} else {
	  Suspend(True)
	  Send "^c"
	  Suspend(False)
	}
	Return
}

#v::
{
	ActivePName := WinGetProcessName("A")
	if (ActivePName = "WindowsTerminal.exe")
	{
	  Send "^+v"
	} else {
	  Suspend(True)
	  Send "^v"
	  Suspend(False)
	}
	Return
}

#x::
{
	ActivePName := WinGetProcessName("A")
	if (ActivePName = "WindowsTerminal.exe")
	{
	  Send "^+x"
	} else {
	  Suspend(True)
	  Send "^x"
	  Suspend(False)
	}
	Return
}

; Select all
#a::
{
	Suspend(True)
	Send "^a"
	Suspend(False)
	Return
}

; Search function
#f::
{
	Suspend(True)
	Send "^f"
	Suspend(False)
	Return
}

; Reload
#r::
{
	Suspend(True)
	Send "^r"
	Suspend(False)
	Return
}

; Rather use save than Windows Search
#s::
{
	Suspend(True)
	Send "^s"
	Suspend(False)
	Return
}

; Open new tab in browsers
#t::
{
	Suspend(True)
	Send "^t"
	Suspend(False)
	Return
}

; Close tabs in browsers
#w::
{
	Suspend(True)
	Send "^w"
	Suspend(False)
	Return
}

; Close window
#q::
{
	Suspend(True)
	Send "!{f4}"
	Suspend(False)
	Return
}

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

; Use the better windows switching
; LWin & Tab::AltTab
