Set sh = CreateObject("WScript.Shell")
' Starts the five supervisors from the PROMOTED checkout (the edgestack-live
' junction), never from a working tree, with the pinned interpreter. Each
' supervisor is ensure-running (a per-mode lock in host/run.py), so running
' this twice cannot double-start the scheduler or the Live Manager.
root = "C:\Users\Lenovo\edgestack-live"
py = "C:\Python314\python.exe"
For Each m In Array("mcp","scheduler","dashboard","live","tunnel")
  sh.Run """" & py & """ """ & root & "\host\run.py"" " & m, 0, False
Next
