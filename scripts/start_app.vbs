' Hidden launcher for the Electron app (app/ built with `npm run build`).
' Waits for the backend health endpoint (up to ~60 s) so the board opens with data.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
appDir = root & "\app"
electron = appDir & "\node_modules\.bin\electron.cmd"

On Error Resume Next
For i = 1 To 30
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", "http://127.0.0.1:8020/api/health", False
    http.Send
    If Err.Number = 0 And http.Status = 200 Then Exit For
    Err.Clear
    WScript.Sleep 2000
Next
On Error GoTo 0

sh.CurrentDirectory = appDir
sh.Run """" & electron & """ .", 0, False
