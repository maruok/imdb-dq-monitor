<#
.SYNOPSIS
    Orchestrates DQM investigations and reviews end-to-end using Claude Code agents.
    Runs entirely on your Claude Pro subscription -- no API billing.

.DESCRIPTION
    Phase 1: Agent 1 (Analyst) investigates each flagged check via /dqm-investigate
    Phase 2: Agent 2 (Reviewer) independently reviews each output via /dqm-review
    Phase 3: Combined markdown summary of all verdicts

    All agents run non-interactively with --dangerously-skip-permissions so no
    manual approval is needed. Agent isolation is maintained: each claude invocation
    starts a fresh context.

.PARAMETER Checks
    One or more check names to investigate. Partial names work (case-insensitive).
    Example: "titleType: tvMiniSeries", "genre: Drama"

.PARAMETER All
    Investigate all currently flagged checks (uses MCP server to fetch the list).

.PARAMETER Max
    Cap on how many checks to run when using -All. Default: 5.
    Increase carefully -- each pair (investigate + review) costs ~20-30K tokens.

.PARAMETER PauseSecs
    Seconds to wait between agent invocations. Default: 8.
    Increase to 30+ if you are hitting Claude Pro rate limits.

.PARAMETER SkipReview
    Run Phase 1 only (investigations, no reviews). Useful for quick checks.

.EXAMPLE
    .\agents\run_dqm.ps1 -Checks "titleType: tvMiniSeries"
    .\agents\run_dqm.ps1 -Checks "titleType: tvMiniSeries","genre: Drama"
    .\agents\run_dqm.ps1 -All -Max 3
    .\agents\run_dqm.ps1 -All -Max 5 -PauseSecs 30
    .\agents\run_dqm.ps1 -Checks "titleType: tvMiniSeries" -SkipReview
#>
param(
    [string[]] $Checks,
    [switch]   $All,
    [int]      $Max        = 5,
    [int]      $PauseSecs  = 8,
    [switch]   $SkipReview
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# --- Paths -------------------------------------------------------------------

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$InvDir      = Join-Path $PSScriptRoot "investigations"

# Run from project root so claude reads .claude/settings.json and MCP config
Push-Location $ProjectRoot
try {

New-Item -ItemType Directory -Force -Path $InvDir | Out-Null

# --- Helpers -----------------------------------------------------------------

function Write-Banner {
    param([string]$msg, [string]$color = "Cyan")
    $line = "-" * 64
    Write-Host ""
    Write-Host $line -ForegroundColor $color
    Write-Host "  $msg" -ForegroundColor $color
    Write-Host $line -ForegroundColor $color
}

function Get-FilesWrittenAfter {
    param([string]$pattern, [datetime]$since, [string]$exclude = '')
    $files = @(Get-ChildItem $pattern -ErrorAction SilentlyContinue |
               Where-Object { $_.LastWriteTime -gt $since })
    if ($exclude) { $files = @($files | Where-Object { $_.Name -notmatch $exclude }) }
    return @($files | Select-Object -ExpandProperty Name)
}

function Get-Verdict {
    param([string]$reviewFile)
    if (-not (Test-Path $reviewFile)) { return "NOT FOUND" }
    $content = Get-Content $reviewFile -Raw -ErrorAction SilentlyContinue
    if ($content -match '\*\*OVERALL:\s*([A-Z][A-Z-]+)\*\*') { return $Matches[1] }
    return "UNKNOWN"
}

function Get-FlaggedCheckNames {
    $py = @'
import sys
sys.path.insert(0, 'agents')
sys.path.insert(0, '.')
from dqm_mcp_server import list_flagged_checks
print(list_flagged_checks())
'@
    $tmp = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), '.py')
    [System.IO.File]::WriteAllText($tmp, $py, [System.Text.Encoding]::UTF8)
    try {
        $json = python $tmp 2>$null
        $parsed = $json | ConvertFrom-Json
        return @($parsed | ForEach-Object { $_.name })
    } catch {
        return @()
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

# --- Resolve check list ------------------------------------------------------

if ($All) {
    Write-Host "Fetching flagged checks from MCP server..." -ForegroundColor Gray
    $Checks = Get-FlaggedCheckNames
    if (-not $Checks -or $Checks.Count -eq 0) {
        Write-Host "No flagged checks found. Nothing to do." -ForegroundColor Yellow
        return
    }
    if ($Checks.Count -gt $Max) {
        Write-Host "Found $($Checks.Count) flagged checks -- capping at $Max (use -Max N to change)." -ForegroundColor Yellow
        $Checks = @($Checks | Select-Object -First $Max)
    }
}

if (-not $Checks -or $Checks.Count -eq 0) {
    Write-Host ""
    Write-Host "Usage:"
    Write-Host '  .\agents\run_dqm.ps1 -Checks "titleType: tvMiniSeries"'
    Write-Host '  .\agents\run_dqm.ps1 -Checks "titleType: tvMiniSeries","genre: Drama"'
    Write-Host '  .\agents\run_dqm.ps1 -All'
    Write-Host '  .\agents\run_dqm.ps1 -All -Max 3 -PauseSecs 30'
    Write-Host ""
    return
}

# --- Header ------------------------------------------------------------------

$RunStart = Get-Date
Write-Host ""
Write-Host "DQM Agent Orchestrator  $($RunStart.ToString('yyyy-MM-dd HH:mm'))" -ForegroundColor White
Write-Host "Checks  : $($Checks -join ' | ')" -ForegroundColor Gray
if ($SkipReview) {
    Write-Host "Flow    : Investigate only (review skipped)" -ForegroundColor Gray
} else {
    Write-Host "Flow    : Investigate -> Review -> Combined report" -ForegroundColor Gray
}
Write-Host "Tokens  : Claude Pro subscription (no API billing)" -ForegroundColor Gray

# --- Phase 1: Investigations -------------------------------------------------

$investigationFiles = [System.Collections.Generic.List[string]]::new()

for ($i = 0; $i -lt $Checks.Count; $i++) {
    $check = $Checks[$i]
    Write-Banner "[$($i+1)/$($Checks.Count)] AGENT 1 -- Investigating: $check"

    $phaseStart = Get-Date

    claude -p "/dqm-investigate $check" --dangerously-skip-permissions

    $newFiles = Get-FilesWrittenAfter -pattern "$InvDir\*.md" -since $phaseStart -exclude '_review'
    $newFile  = $newFiles | Select-Object -First 1

    Write-Host ""
    if ($newFile) {
        $investigationFiles.Add((Join-Path $InvDir $newFile))
        Write-Host "  Saved: $newFile" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: No investigation file produced for '$check'." -ForegroundColor Yellow
    }

    if ($i -lt ($Checks.Count - 1)) {
        Write-Host "  Pausing $PauseSecs s before next agent..." -ForegroundColor DarkGray
        Start-Sleep -Seconds $PauseSecs
    }
}

if ($investigationFiles.Count -eq 0) {
    Write-Host ""
    Write-Host "No investigation files were produced. Exiting." -ForegroundColor Red
    return
}

# --- Phase 2: Reviews --------------------------------------------------------

$reviewFiles = [System.Collections.Generic.List[string]]::new()

if (-not $SkipReview) {
    for ($i = 0; $i -lt $investigationFiles.Count; $i++) {
        $invFile = $investigationFiles[$i]
        $leaf    = Split-Path $invFile -Leaf
        Write-Banner "[$($i+1)/$($investigationFiles.Count)] AGENT 2 -- Reviewing: $leaf" "Magenta"

        $phaseStart = Get-Date

        $relPath = "agents\investigations\$leaf"
        claude -p "/dqm-review $relPath" --dangerously-skip-permissions

        $newReviews = Get-FilesWrittenAfter -pattern "$InvDir\*_review.md" -since $phaseStart
        $newReview  = @($newReviews) | Select-Object -First 1

        Write-Host ""
        if ($newReview) {
            $reviewFiles.Add((Join-Path $InvDir $newReview))
            Write-Host "  Saved: $newReview" -ForegroundColor Green
        } else {
            Write-Host "  WARNING: No review file produced for '$leaf'." -ForegroundColor Yellow
        }

        if ($i -lt ($investigationFiles.Count - 1)) {
            Write-Host "  Pausing $PauseSecs s before next agent..." -ForegroundColor DarkGray
            Start-Sleep -Seconds $PauseSecs
        }
    }
}

# --- Phase 3: Combined report ------------------------------------------------

Write-Banner "Generating combined report..." "White"

$RunEnd   = Get-Date
$Duration = [int]($RunEnd - $RunStart).TotalMinutes
$slug     = $RunStart.ToString('yyyy-MM-dd_HHmm')

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("# DQM Run Report")
$lines.Add("")
$lines.Add("**Date**: $($RunStart.ToString('yyyy-MM-dd HH:mm'))  |  **Duration**: ~${Duration} min  |  **Checks**: $($Checks.Count)")
$lines.Add("")
$lines.Add("---")
$lines.Add("")
$lines.Add("## Verdict Summary")
$lines.Add("")
$lines.Add("| Check | Verdict | Files |")
$lines.Add("|---|---|---|")

foreach ($invFile in $investigationFiles) {
    $leaf       = Split-Path $invFile -Leaf
    $checkLabel = $leaf -replace '^\d{4}-\d{2}-\d{2}_','' -replace '\.md$','' -replace '_',' '
    $reviewName = $leaf -replace '\.md$','_review.md'
    $reviewPath = Join-Path $InvDir $reviewName

    if ($SkipReview) {
        $verdict = "(review skipped)"
    } else {
        $verdict = Get-Verdict $reviewPath
    }

    if (Test-Path $reviewPath) {
        $reviewLink = "[$reviewName]($reviewPath)"
    } else {
        $reviewLink = "not produced"
    }

    $lines.Add("| $checkLabel | $verdict | [$leaf]($invFile) / $reviewLink |")
}

$lines.Add("")
$lines.Add("---")
$lines.Add("")
$lines.Add("## Output Files")
$lines.Add("")
foreach ($f in $investigationFiles) { $lines.Add("- $( Split-Path $f -Leaf )  -- investigation") }
foreach ($f in $reviewFiles)        { $lines.Add("- $( Split-Path $f -Leaf )  -- review") }
$lines.Add("")
$lines.Add("---")
$lines.Add("*Generated by run_dqm.ps1 -- all token usage via Claude Pro subscription.*")

$reportPath = Join-Path $InvDir "run_${slug}_summary.md"
[System.IO.File]::WriteAllLines($reportPath, $lines, [System.Text.Encoding]::UTF8)
Write-Host "  Saved: $(Split-Path $reportPath -Leaf)" -ForegroundColor Green

# --- Final summary -----------------------------------------------------------

Write-Banner "ALL DONE -- $($investigationFiles.Count) investigated, $($reviewFiles.Count) reviewed" "Green"
Write-Host ""

foreach ($invFile in $investigationFiles) {
    $leaf       = Split-Path $invFile -Leaf
    $label      = $leaf -replace '^\d{4}-\d{2}-\d{2}_','' -replace '\.md$',''
    $reviewName = $leaf -replace '\.md$','_review.md'
    $reviewPath = Join-Path $InvDir $reviewName

    if ($SkipReview) {
        $verdict = "(review skipped)"
        $color   = "Gray"
    } else {
        $verdict = Get-Verdict $reviewPath
        if ($verdict -eq "ENDORSE")              { $color = "Green"  }
        elseif ($verdict -eq "ENDORSE-WITH-CAVEATS") { $color = "Yellow" }
        elseif ($verdict -eq "RETURN-FOR-REWORK")    { $color = "Red"    }
        else                                         { $color = "Gray"   }
    }

    Write-Host "  $label" -NoNewline
    Write-Host "  ->  $verdict" -ForegroundColor $color
}

Write-Host ""
Write-Host "Combined report: $reportPath" -ForegroundColor Cyan
Write-Host ""

} finally {
    Pop-Location
}
