^!e::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput Please understand that this is an estimate based on the assumption that there will be no specifications clarifications, no rework, no wait times, no hand-offs or escalations with higher priority. This can't be considered as a deadline commitment.
Return

^!u::
  KeyWait Ctrl
  KeyWait Shift
  Send, {Ctrl}{Shift}
  SendInput This is very interesting, and I will need some time to dive into it.{Enter}{Enter}Unfortunately, I can’t do that immediately due to other priorities.{Enter}{Enter}To understand the urgency better, could you please let me know the bad thing that will happen if this isn’t resolved as soon as possible? What would be the preferred date for you to get this resolved?
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
  SendInput <pre>{Enter}Hello,{Enter}{Enter}The solution was implemented and tested in Template.{Enter}{Enter}You may find the rule description and customizing option in <a href='https://adponline.sharepoint.com/:w:/r/sites/GlobalView-Engine-Architecture/documentation/pex-payroll-exceptions-reporting/pex-consultant-guide.docx?web=1'>PEX consultant guide</a>.{Enter}{Enter}The solution was registered to GV Feature Pack FY21-M05 (version 6.13.2) with ID 667531. It will deploy to Production in 05_May'21-Jun'21 (HRSP 93) cycle on 20.06.2021.{Enter}In parallel, the transport to PD1 was requested via RTO 799312 and RevTrac states it was delivered.{Enter}{Enter}Please let me know if you want to opt in the emergency deployment or find any side effects caused by the correction.{Enter}Bear in mind that the last modifications to GVFP FY21-M03 are allowed on 21.05.2021, so it will be much easier if you provided your feedback by then.{Enter}{Enter}Thank you.{Enter}{Enter}Cheers, Tomáš Bouška</pre>
Return