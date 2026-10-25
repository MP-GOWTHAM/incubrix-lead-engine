param([string]$Token = 'manual')
# Technical demo run sheet (Video B). Runs every step live, with pauses so each output is readable.
Set-Location $PSScriptRoot\..
$host.UI.RawUI.WindowTitle = "IncuBrix Lead Engine - technical demo"
function Step($title) { Write-Host ""; Write-Host ("=" * 90) -ForegroundColor Cyan; Write-Host "  $title" -ForegroundColor Cyan; Write-Host ("=" * 90) -ForegroundColor Cyan; Start-Sleep 3 }

Clear-Host
Step "IncuBrix creator lead engine  |  one command: python -m engine run  |  stdlib only, no keys, `$0"
Get-Content README.md -TotalCount 22 | Out-Host
Start-Sleep 12

Step "1. Offline test suite (28 tests, incl. every audit regression)"
python -m unittest discover -s tests 2>&1 | Select-Object -Last 4 | Out-Host
Start-Sleep 6

Step "2. NORMAL RUN on new input: 17 real shows the engine has never seen (demo/video_input.txt)"
python -m engine run --seed demo/video_input.txt --only-seed | Out-Host
Start-Sleep 12

Step "Full-scale run history (output/runs.csv): 20,000+ shows, 1,048 qualified, 0 duplicates, `$0"
Import-Csv output\runs.csv | Select-Object run_at, mode, input_size, qualified, duplicates_removed, runtime_min, direct_cost_usd | Format-Table -AutoSize | Out-Host
Start-Sleep 12

Step "A qualified lead and its evidence (every claim has a public URL)"
$l = Import-Csv output\leads.csv | Where-Object priority -eq "A" | Select-Object -First 1
$l | Select-Object lead_id, creator_name, country_iso2, best_channel, channel_handle_or_url, channel_evidence_url, monetization_signal, monetization_evidence_url, incubrix_need, lead_score | Format-List | Out-Host
Start-Sleep 15

Step "3. REFRESH on another new input (demo/video_input_2.txt): new creators get new IDs, old IDs unchanged"
python -m engine run --seed demo/video_input_2.txt --only-seed | Out-Host
Start-Sleep 10

Step "4. FAILURE: simulated crash after 5 feeds (demo/video_input_3.txt)"
python -m engine run --seed demo/video_input_3.txt --only-seed --simulate-failure 5 | Out-Host
Start-Sleep 4
Write-Host "`nerrors.csv (last lines):" -ForegroundColor Yellow
Get-Content output\errors.csv -Tail 2 | Out-Host
Start-Sleep 8

Step "   RECOVERY: same command again -> reuses the 5 saved feeds, fetches only the rest"
python -m engine run --seed demo/video_input_3.txt --only-seed --verbose 2>&1 | Select-String -Pattern "fetching|qualified:|duplicates|runtime|Qualified |Rejected " | Select-Object -First 20 | Out-Host
Start-Sleep 12

Step "Priority A outreach: first message + 2 follow-ups + backup touch, sender + opt-out + tracked link"
$f = Get-ChildItem outreach\priority_a\*.md | Select-Object -First 1
Get-Content $f.FullName -Encoding utf8 -TotalCount 45 | Out-Host
Start-Sleep 18

Step "Launch kit: what IncuBrix does next Monday (launch_kit/LAUNCH_KIT.md section 3)"
$lk = Get-Content launch_kit\LAUNCH_KIT.md -Encoding utf8
$i = ($lk | Select-String -Pattern "^## 3\." ).LineNumber
$lk[($i-1)..($i+12)] | Out-Host
Start-Sleep 15

Step "Demo complete."
Start-Sleep 4
Set-Content -Path "demo\.video_done_$Token" -Value (Get-Date -Format o)
