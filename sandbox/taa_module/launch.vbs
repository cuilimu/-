' TAA Sandbox Launcher (port 8502)
'
' Each L() call opens-append-closes the log so partial traces are preserved
' even if the script later hangs or aborts.

Option Explicit

Dim shell, fso
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

Dim hereDir, port, url, appPath, projectRoot
hereDir    = fso.GetParentFolderName(WScript.ScriptFullName)
port       = "8502"
appPath    = hereDir & "\app_standalone.py"
url        = "http://localhost:" & port

' projectRoot = 4 levels up
projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(projectRoot)
projectRoot = fso.GetParentFolderName(projectRoot)
projectRoot = fso.GetParentFolderName(projectRoot)
shell.Environment("Process")("PYTHONPATH") = projectRoot

Dim launchLog, slLog
launchLog = hereDir & "\launch.log"
slLog     = hereDir & "\streamlit.log"

' ── Logging (open / write / close per call → no buffer loss) ───────────────────
Sub L(msg)
    Dim f
    Set f = fso.OpenTextFile(launchLog, 8, True)   ' 8 = ForAppending, create
    f.WriteLine "[" & Now() & "] " & msg
    f.Close
End Sub

' Truncate previous log on first call
If fso.FileExists(launchLog) Then fso.DeleteFile launchLog, True

L "=== Launcher start ==="
L "ScriptFullName = " & WScript.ScriptFullName
L "hereDir        = " & hereDir
L "appPath        = " & appPath & "  (exists=" & fso.FileExists(appPath) & ")"
L "projectRoot    = " & projectRoot & "  (exists=" & fso.FolderExists(projectRoot) & ")"
L "port           = " & port

' ── (1) Read python_path.txt ───────────────────────────────────────────────────
Dim configPath, pythonExe, ts
configPath = hereDir & "\python_path.txt"
pythonExe  = ""
If fso.FileExists(configPath) Then
    Set ts = fso.OpenTextFile(configPath, 1)
    If Not ts.AtEndOfStream Then
        pythonExe = Trim(ts.ReadLine())
    End If
    ts.Close
End If
L "config python_path.txt = '" & pythonExe & "'"

If pythonExe <> "" Then
    If Not fso.FileExists(pythonExe) Then
        L "  → file missing on disk, falling back"
        pythonExe = ""
    Else
        L "  → exists, using this Python"
    End If
End If

' ── (2) streamlit.exe fallback ────────────────────────────────────────────────
Dim streamlitExe
streamlitExe = ""

If pythonExe = "" Then
    L "scanning streamlit.exe candidates"
    Dim userProfile
    userProfile = shell.ExpandEnvironmentStrings("%USERPROFILE%")

    Dim candidates(7), i
    candidates(0) = userProfile & "\anaconda3\Scripts\streamlit.exe"
    candidates(1) = userProfile & "\Anaconda3\Scripts\streamlit.exe"
    candidates(2) = userProfile & "\miniconda3\Scripts\streamlit.exe"
    candidates(3) = userProfile & "\AppData\Local\anaconda3\Scripts\streamlit.exe"
    candidates(4) = userProfile & "\AppData\Local\Continuum\anaconda3\Scripts\streamlit.exe"
    candidates(5) = "C:\ProgramData\anaconda3\Scripts\streamlit.exe"
    candidates(6) = "C:\ProgramData\Anaconda3\Scripts\streamlit.exe"
    candidates(7) = userProfile & "\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe"
    For i = 0 To 7
        If fso.FileExists(candidates(i)) Then
            streamlitExe = candidates(i)
            Exit For
        End If
    Next
    L "streamlit.exe fallback resolved = '" & streamlitExe & "'"
End If

If pythonExe = "" And streamlitExe = "" Then
    L "FATAL: no Python/streamlit found"
    MsgBox "找不到能运行 streamlit 的 Python。" & vbCrLf & vbCrLf & _
        "请在 Anaconda Prompt 里跑：" & vbCrLf & _
        "    python " & hereDir & "\create_shortcut.py", _
        16, "TAA Sandbox"
    WScript.Quit
End If

' ── Cleanup any stale python.exe holding the port ──────────────────────────────
L "running cleanup for port " & port
Dim cleanupCmd, cleanupExit
cleanupCmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command " & _
    """$c = Get-NetTCPConnection -LocalPort " & port & " -State Listen -EA 0 | Select-Object -First 1; " & _
    "if ($c) { try { $p = Get-Process -Id $c.OwningProcess -EA Stop; " & _
    "if ($p.ProcessName -eq 'python') { Stop-Process -Id $p.Id -Force; Start-Sleep -Milliseconds 600 } } catch {} }"""
cleanupExit = shell.Run(cleanupCmd, 0, True)
L "cleanup exit code = " & cleanupExit

' ── Build the streamlit cmd. PYTHONPATH already set via shell.Environment ─────
Dim cmdLine
If pythonExe <> "" Then
    cmdLine = "cmd /c """ & _
        Chr(34) & pythonExe & Chr(34) & _
        " -m streamlit run " & Chr(34) & appPath & Chr(34) & _
        " --server.port " & port & _
        " --server.headless true" & _
        " --browser.gatherUsageStats false" & _
        " > " & Chr(34) & slLog & Chr(34) & " 2>&1" & """"
Else
    cmdLine = "cmd /c """ & _
        Chr(34) & streamlitExe & Chr(34) & _
        " run " & Chr(34) & appPath & Chr(34) & _
        " --server.port " & port & _
        " --server.headless true" & _
        " --browser.gatherUsageStats false" & _
        " > " & Chr(34) & slLog & Chr(34) & " 2>&1" & """"
End If
L "streamlit cmdLine = " & cmdLine

' Truncate prior streamlit.log so we only see this run
If fso.FileExists(slLog) Then fso.DeleteFile slLog, True

' Async — return immediately, then poll
On Error Resume Next
shell.Run cmdLine, 0, False
If Err.Number <> 0 Then
    L "FATAL: shell.Run streamlit threw err " & Err.Number & " - " & Err.Description
    On Error Goto 0
    MsgBox "Failed to launch python: " & Err.Description, 16, "TAA Sandbox"
    WScript.Quit
End If
On Error Goto 0
L "streamlit spawned (async)"

' ── Poll the health endpoint up to 60 seconds (matplotlib first-import is slow) ─
Dim readyCmd, readyExit
readyCmd = "powershell -NoProfile -Command " & _
    """for ($i=0; $i -lt 120; $i++) { " & _
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:" & port & "/_stcore/health' -UseBasicParsing -TimeoutSec 1 -EA Stop; " & _
    "if ($r.StatusCode -eq 200) { exit 0 } } catch {} ; Start-Sleep -Milliseconds 500 } ; exit 1"""
L "polling /_stcore/health for up to 60s..."
readyExit = shell.Run(readyCmd, 0, True)
L "ready exit code = " & readyExit

If readyExit <> 0 Then
    Dim errBody, errFh
    errBody = "Streamlit 启动失败 (60s 内 /_stcore/health 没响应)。" & vbCrLf & vbCrLf & _
              "streamlit.log:" & vbCrLf
    If fso.FileExists(slLog) Then
        Set errFh = fso.OpenTextFile(slLog, 1)
        If Not errFh.AtEndOfStream Then
            errBody = errBody & errFh.ReadAll()
        Else
            errBody = errBody & "(空——cmd 可能根本没启动 python)"
        End If
        errFh.Close
    Else
        errBody = errBody & "(streamlit.log 不存在)"
    End If
    errBody = errBody & vbCrLf & vbCrLf & "完整 launcher 日志：" & vbCrLf & launchLog
    L "FATAL: streamlit not ready"
    MsgBox errBody, 16, "TAA Sandbox"
    WScript.Quit
End If

L "opening browser " & url
shell.Run url, 1, False
L "=== Launcher done ==="
