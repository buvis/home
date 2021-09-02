DOO := "C:/Users/tbouska/.local/bin/doogat/doo/doo.exe"

!#d:: ; this triggers Doogat creation
Input, key, L1 T1 ; now, wait 1s for keypress to determine what to create
If (ErrorLevel="Timeout")
    Return
Else
{
    If (key="b") {
    Run %DOO% create bookmark
    Return
    }
    Else If (key="c") {
    Run %DOO% create contact
    Return
    }
    Else If (key="m") {
    Run %DOO% create minutes
    Return
    }
    Else If (key="p") {
    Run %DOO% create loop
    Return
    }
    Else If (key="q") {
    Run %DOO% create quote
    Return
    }
    Else If (key="s") {
    Run %DOO% create snippet
    Return
    }
    Else If (key="w") {
    Run %DOO% create wiki-article
    Return
    }
}
Return

!#p:: ; opens the project directory from any metadata
  ClipSaved := ClipboardAll  ; Save current clipboard content to renew it at the end
  Clipboard =  ; Start off empty to allow ClipWait to detect when the text has arrived
  Send ^c  ; Copy the highlighted text to clipboard
  ClipWait  ; Wait for the clipboard to contain text.

  text := Clipboard
  text = %text%

  Run %DOO% edit loops --with "id or rto-tmpl or rto-reg or rto or ticket or ticket-related or incident or user-story or us or psd or commit or roadmap = '%text%'"

  ClipSaved = ; to free memory
Return
