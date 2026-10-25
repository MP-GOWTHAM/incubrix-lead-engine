# Records ONLY the demo window (not the desktop) and stops the moment the demo finishes.
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$root = Split-Path $PSScriptRoot
$token = [guid]::NewGuid().ToString("N").Substring(0,8)
$flag = Join-Path $root "demo\.video_done_$token"
$out = "C:\Users\ADMIN\Videos\IncuBrix_Video_B_technical_demo.mp4"
$title = "IncuBrix Lead Engine - technical demo"
Remove-Item $flag -ErrorAction SilentlyContinue

Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$root\demo\video_b_demo.ps1`" -Token $token" -WindowStyle Maximized
# wait until the window exists with its title
for ($i = 0; $i -lt 40; $i++) {
    if (Get-Process powershell -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -eq $title) { break }
    Start-Sleep -Milliseconds 250
}

$psi = New-Object System.Diagnostics.ProcessStartInfo "ffmpeg"
$psi.Arguments = "-y -f gdigrab -framerate 15 -i desktop -c:v libx264 -preset ultrafast -crf 26 -pix_fmt yuv420p `"$out`""
$psi.RedirectStandardInput = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$ff = [System.Diagnostics.Process]::Start($psi)

while (-not (Test-Path $flag)) { Start-Sleep 1; if ((Get-Date) - $ff.StartTime -gt [TimeSpan]::FromMinutes(9)) { break } }
$ff.StandardInput.Write("q"); $ff.WaitForExit(20000) | Out-Null
"saved $out"

