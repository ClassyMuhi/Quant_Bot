Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File ""D:\Projects\Quant_Bot\scripts\run_sync.ps1"" -WaitSeconds 120", 0, False
