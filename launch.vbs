' Stock Engine Launcher
' Sets PYTHONPATH and uses Anaconda streamlit — no black window.

Dim shell, fso, appPath, port, url
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

port    = "8501"
appPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\ui\app.py"
url     = "http://localhost:" & port

' ── Set PYTHONPATH (required for stock_engine package imports) ────────────────
Dim projectRoot
projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.Environment("Process")("PYTHONPATH") = projectRoot

' ── Find streamlit: Anaconda locations first, then PATH ──────────────────────
Dim userProfile
userProfile = shell.ExpandEnvironmentStrings("%USERPROFILE%")

Dim candidates(7)
candidates(0) = userProfile & "\anaconda3\Scripts\streamlit.exe"
candidates(1) = userProfile & "\Anaconda3\Scripts\streamlit.exe"
candidates(2) = userProfile & "\miniconda3\Scripts\streamlit.exe"
candidates(3) = userProfile & "\AppData\Local\anaconda3\Scripts\streamlit.exe"
candidates(4) = userProfile & "\AppData\Local\Continuum\anaconda3\Scripts\streamlit.exe"
candidates(5) = "C:\ProgramData\anaconda3\Scripts\streamlit.exe"
candidates(6) = "C:\ProgramData\Anaconda3\Scripts\streamlit.exe"
candidates(7) = userProfile & "\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe"

Dim streamlitExe
streamlitExe = ""

Dim i
For i = 0 To 7
    If fso.FileExists(candidates(i)) Then
        streamlitExe = candidates(i)
        Exit For
    End If
Next

If streamlitExe = "" Then
    MsgBox "找不到 streamlit。请确认 Anaconda 已安装，或手动编辑 launch.vbs 填入路径。", 16, "Stock Engine"
    WScript.Quit
End If

' ── Clean up stale python.exe holding the target port ────────────────────────
' Prevents the "double-click does nothing / shows blank page" issue caused by
' a previous streamlit run that didn't exit cleanly.
Dim cleanupCmd
cleanupCmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command " & _
    """$c = Get-NetTCPConnection -LocalPort " & port & " -State Listen -EA 0 | Select-Object -First 1; " & _
    "if ($c) { try { $p = Get-Process -Id $c.OwningProcess -EA Stop; " & _
    "if ($p.ProcessName -eq 'python') { Stop-Process -Id $p.Id -Force; Start-Sleep -Milliseconds 600 } } catch {} }"""
shell.Run cleanupCmd, 0, True   ' synchronous, hidden

' ── Launch streamlit silently ─────────────────────────────────────────────────
Dim cmd
cmd = "cmd /c set PYTHONPATH=" & projectRoot & " && " & _
      Chr(34) & streamlitExe & Chr(34) & _
      " run " & Chr(34) & appPath & Chr(34) & _
      " --server.port " & port & _
      " --server.headless true" & _
      " --browser.gatherUsageStats false"

shell.Run cmd, 0, False   ' 0 = hidden window

' ── Poll until streamlit is ready, then open browser ─────────────────────────
' Replaces the unreliable fixed 4-second sleep — waits up to ~20s for the port
' to start accepting connections, so the browser never opens to a blank page.
Dim readyCmd
readyCmd = "powershell -NoProfile -Command " & _
    """for ($i=0; $i -lt 40; $i++) { " & _
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:" & port & "/_stcore/health' -UseBasicParsing -TimeoutSec 1 -EA Stop; " & _
    "if ($r.StatusCode -eq 200) { exit 0 } } catch {} ; Start-Sleep -Milliseconds 500 } ; exit 1"""
shell.Run readyCmd, 0, True   ' synchronous, hidden

shell.Run url, 1, False
