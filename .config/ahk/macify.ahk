; Copy & paste, but don't break Windows Terminal
#c::
WinGet, ActiveID, ID, A
WinGet, ActivePName, ProcessName, ahk_id %ActiveID%
if (ActivePName = "WindowsTerminal.exe")
{
  Send ^+c
} else {
  Suspend On
  Send ^c
  Suspend Off
}
Return

#v::
WinGet, ActiveID, ID, A
WinGet, ActivePName, ProcessName, ahk_id %ActiveID%
if (ActivePName = "WindowsTerminal.exe")
{
  Send ^+v
} else {
  Suspend On
  Send ^v
  Suspend Off
}
Return

#x::
WinGet, ActiveID, ID, A
WinGet, ActivePName, ProcessName, ahk_id %ActiveID%
if (ActivePName = "WindowsTerminal.exe")
{
  Send ^+x
} else {
  Suspend On
  Send ^x
  Suspend Off
}
Return

; Select all
#a::
  Suspend On
  Send ^a
  Suspend Off
Return

; Search function
#f::
  Suspend On
  Send ^f
  Suspend Off
Return

; Reload
#r::
  Suspend On
  Send ^r
  Suspend Off
Return

; Rather use save than Windows Search
#s::
  Suspend On
  Send ^s
  Suspend Off
Return

; Close tabs in browsers
#w::
  Suspend On
  Send ^w
  Suspend Off
Return

; Close window
#q::
  Suspend On
  Send !{f4}
  Suspend Off
Return

; Move on line
#Left::Send, {Home}
#Right::Send, {End}

; Language switching
^Space::
  Send, {Ctrl down}{Shift}{Ctrl up}
Return

; Disable alone press of windows key
;LWin Up:: Return

; Use the better windows switching
;LWin & Tab::AltTab
