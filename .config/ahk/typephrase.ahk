^!e::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput Please understand that this is an estimate based on the assumption that there will be no specifications clarifications, no rework, no wait times, no hand-offs or escalations with higher priority. This can't be considered as a deadline commitment.
Return

^!r::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput Please let me know in case you require further assistance from me.{Enter}{Enter}Thank you.{Enter}{Enter}Cheers, Tomáš Bouška
Return

^!t::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput Thank you.{Enter}{Enter}Cheers, Tomáš Bouška
Return

^!z::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  FormatTime, CurrentDateTime,, yyyyMMddHHmmss
  Send %CurrentDateTime%
Return

^!d::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput Hi Martin,{Enter}{Enter}The solution was registered to GV Feature Pack FY21-M11 (version 6.11.2) with ID 667182. This goes to PROD in HRSP 86 cycle on 20.12.2020.{Enter}Transport to PD1 was requested via RTO 771624 and RevTrac states it was delivered.{Enter}{Enter}You may consult PDN here: http://teamsites.adpcorp.com/Sites/ProductTeamHomepage/developers/Applications/Product`%20changes`%20-`%20Product`%20Delivery`%20Notes`%20(all`%20applications)/GV_PDN_1-41898278025.docx?web=1{Enter}{Enter}Please let me know if you want to opt in the emergency deployment or find any side effects caused by the correction.{Enter}Bear in mind that the last modifications to this GVFP are allowed on 20.11.2020, so it will be much easier if you provided your feedback by then.{Enter}{Enter}Thank you.{Enter}{Enter}Cheers, Tomáš Bouška
Return