# Product walkthrough (Video A): what IncuBrix gets, file by file. Runs on its own with readable pauses.
Set-Location $PSScriptRoot\..
$host.UI.RawUI.WindowTitle = "IncuBrix Lead Engine - technical demo"
function Step($title) { Write-Host ""; Write-Host ("=" * 90) -ForegroundColor Cyan; Write-Host "  $title" -ForegroundColor Cyan; Write-Host ("=" * 90) -ForegroundColor Cyan; Start-Sleep 3 }
function Show($path, $from, $count) { $t = Get-Content $path -Encoding utf8; $t[$from..([Math]::Min($t.Count-1, $from+$count-1))] }

Clear-Host
Step "IncuBrix Option 1 - multi-channel creator lead generation & outreach  |  Gowtham M P"
Write-Host "Goal: find creators who need IncuBrix, verify them, pick the best channel, write personalised outreach."
Write-Host "Deliverables: verified leads | outreach kit (7 channels) | engine | seed test | 30-day launch kit"
Start-Sleep 10

Step "1. The verified lead list - output/leads.csv"
$L = Import-Csv output\leads.csv
Write-Host ("Qualified creators : {0}" -f $L.Count)
Write-Host ("Duplicates         : {0}" -f ($L | Where-Object duplicate_check -ne 'UNIQUE').Count)
Write-Host ("Incomplete rows    : {0}" -f ($L | Where-Object completeness_check -ne 'COMPLETE').Count)
Write-Host "`nBy country:"; $L | Group-Object country_iso2 | Sort-Object Count -Descending | Format-Table Name, Count -AutoSize
Write-Host "By segment:"; $L | Group-Object creator_segment | Format-Table Name, Count -AutoSize
Write-Host "Best channel:"; $L | Group-Object best_channel | Sort-Object Count -Descending | Format-Table Name, Count -AutoSize
Start-Sleep 14

Step "2. Market insight from the data - output/lead_stats.json"
$s = Get-Content output\lead_stats.json -Raw | ConvertFrom-Json
Write-Host ("{0}% publish no transcripts  -> captions gap" -f $s.pct_no_transcripts)
Write-Host ("{0}% have long episodes with no clip channel linked  -> repurposing gap (median {1} min)" -f $s.pct_repurposing_gap, $s.median_episode_minutes)
Write-Host ("{0}% carry sponsor reads | {1}% memberships | {2}% sell coaching/consulting" -f $s.pct_sponsorship, $s.pct_membership, $s.pct_service)
Write-Host "`nOpportunity: lead every message with 3 free clips from the creator's own latest episode."
Start-Sleep 14

Step "3. One lead, every claim backed by a public link"
$l = $L | Where-Object priority -eq 'A' | Select-Object -Skip 3 -First 1
$l | Select-Object lead_id, creator_name, creator_segment, country_iso2, profile_url, last_content_date, content_count_30d, longform_count_60d, monetization_signal, monetization_evidence_url, incubrix_need, best_channel, channel_handle_or_url, channel_evidence_url, backup_channel, lead_score | Format-List
Start-Sleep 18

Step "4. Outreach kit - sequences per segment and channel (outreach/sequences/)"
Get-ChildItem outreach\sequences | Format-Table Name, Length -AutoSize
Show outreach\sequences\podcasters.md 0 32
Start-Sleep 16

Step "5. Priority A - 250 leads, each with first message + 2 follow-ups + backup touch"
Write-Host ("Files in outreach/priority_a: {0}" -f (Get-ChildItem outreach\priority_a\*.md).Count)
$f = Get-ChildItem outreach\priority_a\*.md | Select-Object -Skip 5 -First 1
Show $f.FullName 0 36
Start-Sleep 18

Step "6. Seed test on my own accounts - seed_test/"
$st = Get-Content seed_test\SEED_TEST.md -Encoding utf8
$i = ($st | Select-String -Pattern "^## 6\.").LineNumber
$st[($i-1)..($i+8)]
Write-Host "`nEvidence:"; Get-ChildItem seed_test\evidence | Format-Table Name -AutoSize
Start-Sleep 16

Step "7. Launch kit - what IncuBrix does next Monday (launch_kit/LAUNCH_KIT.md)"
$lk = Get-Content launch_kit\LAUNCH_KIT.md -Encoding utf8
$j = ($lk | Select-String -Pattern "^## 6\.").LineNumber
$lk[($j-1)..($j+14)]
Start-Sleep 18

Step "Engine: python -m engine run  |  repo: github.com/MP-GOWTHAM/incubrix-lead-engine  |  Demo complete."
Start-Sleep 4
Set-Content -Path demo\.video_done -Value (Get-Date -Format o)
