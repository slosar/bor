You have to write a terminal based e-mail reader.

The application has to use mu to access emails. I have put mu4e in agents/mu4e to see how mu4e uses mu to search for emails, etc.

The application has to use textual library for user interface. See help/terminal_editor.py for a minimal textual editor. In particular see how
alt-1-9 are detected. alt-0/-/= give U+00BA U+2013 U+2260 respectivelly.

The application can use any solution to send emails via SMTP.

See coding guidelines in agents/guidelines.md.

The applications has to use configuration file in ~/.config/bor.conf. Values for all major parameters including inbox folder and archived folder should be configurable. You should create your own schema and create an example configuration file.  

The applications uses screen tabs as per terminal_editor.py example. Tab 0, accessible by Alt-0, is always on and displays "Message index" tab
Additional Tabs appear as needed and are accessible from Alt-1 onwards. Tab titles should be informative. 

Here is description of individual tabs that you should implement and the keyboard shortcuts.

# "Message index" tab

Message index displays messages, one email entry per line. Each line should show Date, From, Subject and Flags fields.
Flags field should contain unicode symbols to show: unread, replied, forward, important and attachments flags.
Unread message should additionally be colored (blue by default).
Important messages should additional be colored (orange by default).
Marked messages should have inverted video.

Messages can be ordered either by date (with newest on top) or threaded.  When messages are threaded, the subject is indented with the appropriate ↳ symbol. 

Follow keys should be implemented:
    - up, down arrows, PgUp, PgDn
    - N/P for next previous should be equivalent to down/up arrows
    - space is page down
    - Enter: opens message in a new "Message" tab
    - R: Replies to message in a new "Compose" tab
    - F: Forward the message in a new "Compose" tab
    - C: create new mail in a new Compose tab
    - Ctrl-F : Search message index incrementally
    - S: Search for messages using mu
    - Ctrl+Q: quit application
    - I: display inbox folder (shortcut for the relevant search command)
    - O: display archived folder (shortcut for the relevant search command)
    - U: display draft folder (shortcut for the relevant search command)
    - E: ONLY if message is in the draft folder: edit message in a new "Compose" tab 
    - J: jump to folder (shortcut for the relevant search command)
    - L: Execute a synchronization command in a new tab (user selectable, meant to fetch new messages)
    - M: mark the message (for future action)
    - X: archive marked messages (move into archived folder) otherwise archive current message. Ask for y/n confirmation first.I
    - D: delete marked messages otherwise delete current message. In either case ask for confirmation.
    - A: Applies a flag to marked messages or current message. Flag can be (U)nread, (N)ew, (F)lagged (=important). Shift +U/N/F removes the flag
    - Z: undo the last move message operation
    - T: enable/disable threading.
    - Ctrl-T: make the appropriate search with mu to show all messages in a threads associated with current message. This new threaded view replaces the current message list. 
    - Ctrl-R update mu index, same as mu4e-update.el 

By default the inbox should be displayed. The contents should be obtained using appropriate mu search command. It should only show first 400 (user selectable) messages to avoid performance issues

# "Message" tab

Message tab displays a the actual message. It should display the actual header (From: , To:, CC:, etc.) followed by the text message in as old email readers like pine.
It should also prominently display the number of attachments and their type. When email is html only, one should you a renderer that can render in terminal. Please use a rendered of your choice that works well with textual library.
Clicking on links in the viewer should open them in a browser. Mouse wheel should scroll the message up and down. 

The following keys should be implemented:
    - up, down arrows, PgUp, PgDn 
    - space is page down
    - "<" returns to message index (as Alt-0) without closing tab
    - Q returns to message index with closing tab.
    - M, X, D, A work exactly as in Message index. If I mark some messages and return to index they remain marked. 
    - N next message (if the current message is focused in message index)
    - P previous message (if the current message is focused in message index)
    - R: Replies to message in a "Compose" tab that replace Message tab
    - F: Forward the message in a "Compose" tab that replace Message tab 
    - C: create new mail in a "Compose" tab that replace Message tab
    - Ctrl-S: Search message index incrementally
    - A: Archive current message 
    - Z: Replace current tab with "Attachments" tab for the current message
    - Ctrl-R: display rich headers that show things like BCC, etc.


    
# "Attachments" tab

Displays the list of all attachments. They can be selected by a number (if <=9) or my selecting an item from a menu widget. When attachment is selected, it is displayed in box if it is a parsable type, like text.
Images should be displayed assuming kitty terminal using icat command. Other formats like pdf and html should be opened using system handler.
 The following keys should be additionally implemented:
    - Q returns to the parent message
    - < should return to the message index without closing tab. 


# "Compose" Tab
This tab is for composing messages. It should have a To:, CC:, BCC: and Subject fields on top. They should be editable. 

In To:, CC: and BCC: fields the email tab autocompletion should work using email database provided by mu.
Aliases defined in .mailrc should also complete when I press Tab.

The Compose tab message contents should be initialized appropriately when a mail is replied to (quoting it) or Forwarded.

The editor should support:
    - movement with arrows/ Pg Up/Dn / Home / End
    - Ctrl-S: Search incrementally
    - Ctrl-I: add contents of a text file
    - Ctrl-A: attach a file (with filename autocompletion on Tab)
    - Copy/Cut/Paste via Crtl-C/X/V 
    - Undo / Redo via Ctrl-Z, Ctrl-Y
    - text autocompletions. A small letter follows by tab should autocomplete into a configurable string. E.g. A+Tab can autocmplete into "     Joe". These combinations should be configurable.
 
In the To/CC/BCC fields, ctrl-F should open a search box that allows me to search email addresses and pick the email from them list.

 The following commands should work in all fields, including To:  and the editor. 
    - Ctrl-L L (Ctrl-L followed by L) sends the email and closes tab.
    - Ctrl-L D saves the email in the draft folder and closes tab.
    - Ctrl-L X cancels send. It should prompt for y/n confirmation.
    - Ctrl-L S goes to Subject field
    - Ctrl-L T goes to To fieled
    - Ctrl-L C goes to CC field
    - Ctrl-L B goes to BCC field
    - Ctrl-L E goes to Editor
    - Ctrl-L A should add attachments to the email. Filenames should be specified via input box that starts with user home (or last folder used) and supports tab completion. 
    - Tab should also move between To/CC/BCC/Subject fields (once in editor it becomes editor tab.)


# "Synchronization" Tab  
    
Synchronization tab calls an external system command (configurable) and displays its tty in a separate tab.  After Synchronization, mu index should be updated.
