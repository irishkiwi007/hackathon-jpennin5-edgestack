Set sh = CreateObject("WScript.Shell")
root = "C:\Users\Lenovo\alpaca-mcp-lab"
For Each m In Array("mcp","scheduler","dashboard","live","tunnel")
  sh.Run "python """ & root & "\host\run.py"" " & m, 0, False
Next
