global DOO := "C:/Users/tbouska/.local/bin/doogat/doo/doo.exe "

!#d:: ; this triggers Doogat creation
{
    ih := InputHook("L1 T1")
    ih.Start()
    ErrorLevel := ih.Wait()

    If (ErrorLevel = "Timeout")
        return
    Else {

        If (ih.input="b") {
            Run DOO "create bookmark"
            Return
        }
        Else If (ih.input="c") {
            Run DOO "create contact"
            Return
        }
        Else If (ih.input="m") {
            Run DOO "create minutes"
            Return
        }
        Else If (ih.input="p") {
            Run DOO "create loop"
            Return
        }
        Else If (ih.input="q") {
            Run DOO "create quote"
            Return
        }
        Else If (ih.input="s") {
            Run DOO "create snippet"
            Return
        }
        Else If (ih.input="w") {
            Run DOO "create wiki-article"
            Return
        }
    }

    Return
}

!#p:: ; opens the project directory from any metadata
{
    A_Clipboard := "" ; Start off empty to allow ClipWait to detect when the text has arrived
    Send "^c"  ; Copy the highlighted text to clipboard
    ClipWait  ; Wait for the clipboard to contain text.

    search_string := A_Clipboard
    command := "edit loops --with `"id or rto-tmpl or rto-reg or rto or ticket or ticket-related or incident or user-story or us or psd or commit or roadmap = '" search_string "'`""

    Run DOO command

    Return
}
