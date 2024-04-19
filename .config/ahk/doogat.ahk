global DOO := "C:\Users\tbouska\.local\bin\doogat\doo\doo.exe "

!#d:: ; this triggers Doogat creation
{
    ih := InputHook("L1 T1")
    ih.Start()
    ErrorLevel := ih.Wait()

    If (ErrorLevel = "Timeout")
        return
    Else {

        If (ih.input="b") {
            Run DOO "create bookmark --edit"
            Return
        }
        Else If (ih.input="c") {
            Run DOO "create contact --edit"
            Return
        }
        Else If (ih.input="m") {
            Run DOO "create minutes --edit"
            Return
        }
        Else If (ih.input="p") {
            Run DOO "create loop --edit"
            Return
        }
        Else If (ih.input="q") {
            Run DOO "create quote --edit"
            Return
        }
        Else If (ih.input="s") {
            Run DOO "create snippet --edit"
            Return
        }
        Else If (ih.input="w") {
            Run DOO "create wiki-article --edit"
            Return
        }
    }

    Return
}

!#p:: ; opens the project directory from any metadata
{
    A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
    Send "^c"  ; Copy the highlighted text to clipboard
    ClipWait ; Wait for the clipboard to contain text.

    search_string := Trim(A_Clipboard, " `n`r`t")

    command := "get loops `"id or rto-tmpl or rto-reg or rto or ticket or ticket-related or incident or user-story or us or psd or commit or roadmap = '" search_string "'`" --edit"

    Run DOO command

    Return
}

!#s:: ; schedules loop's next action in Outlook Calendar
{
    A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
    Send "^c"  ; Copy the highlighted text to clipboard
    ClipWait ; Wait for the clipboard to contain text.

    loop_id := Trim(A_Clipboard, " `n`r`t")

    Run "outlook-syncer.bat schedule_next_action " loop_id

    Return
}
