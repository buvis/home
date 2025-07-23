::Andres ::Andrés
::Tomas ::Tomáš
::Bouska ::Bouška
::,.todo::⚒️
::,.done::✔️
::url-pexcg::
(
https://adponline.sharepoint.com/sites/GlobalView-Engine-Architecture/documentation/pex-payroll-exceptions-reporting/pex-consultant-guide.docx?web=1
)
::url-emergency::
(
https://confluence.es.ad.adp.com/spaces/EMEACSKB/pages/1524500795/Emergency+Product+Release#EmergencyProductRelease-GLOBALCHANGE
)
::ticket::
(
service request
)
::ity ::infotype

!#u:: ; rewrites Jira User story to MD link
{
    A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
    Send "^c"  ; Copy the highlighted text to clipboard
    ClipWait ; Wait for the clipboard to contain text.

    us_key := Trim(A_Clipboard, " `n`r`t")

    md_link := "[" us_key "](https://jira.service.tools-pi.com/browse/" us_key ")"

    SendInput(md_link)

    Return
}