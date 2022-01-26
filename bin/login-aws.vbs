Dim WinScriptHost

Set WinScriptHost = CreateObject("WScript.Shell")

WinScriptHost.Run "C:\Users\tbouska\scoop\apps\nodejs\current\bin\dexaws.cmd aws", 0

Set WinScriptHost = Nothing
