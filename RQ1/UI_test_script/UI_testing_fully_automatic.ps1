<#
  Anonymous / Shareable PowerShell script (Play Store + Health Connect flow)
  - Uses only relative paths by default
  - ADB resolved from PATH (configurable via $Adb)
  - UI taps by text (no personal coordinates)
  - No user/machine-specific paths or IDs
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── Configuration ─────────────────────────────────────────────────────────────
# Path to your JSON file containing an array of package-name strings:
$packageListFile = "package_name.json"

# Output directories (relative paths OK)
$dumpXmlDir      = "dump_xml"
$screenshotDir   = "path to save screenshots"

# Tunables
$postLaunchWait  = 1
$downloadWait    = 15
$screenshotWait  = 10

# ADB binary (use the one in PATH by default)
$Adb = "adb"
# ───────────────────────────────────────────────────────────────────────────────

# Ensure output folders exist
New-Item -ItemType Directory -Path $dumpXmlDir,$screenshotDir -Force | Out-Null

function Invoke-Adb {
    param([Parameter(Mandatory)][string[]]$Args)
    & $Adb @Args
}

function Dump-UiXml {
    param(
        [Parameter(Mandatory)][string]$DevicePath = "/sdcard/ui_dump.xml",
        [Parameter(Mandatory)][string]$LocalPath
    )
    Invoke-Adb @("shell","uiautomator","dump",$DevicePath) | Out-Null
    Invoke-Adb @("pull",$DevicePath,$LocalPath) | Out-Null
}

function Get-NodeCenter {
    param([Parameter(Mandatory)][string]$Bounds)
    if ($Bounds -notmatch '\[(\d+),(\d+)\]\[(\d+),(\d+)\]') { return $null }
    $x = ([int]$matches[1] + [int]$matches[3]) / 2
    $y = ([int]$matches[2] + [int]$matches[4]) / 2
    return @{ X = [int]$x; Y = [int]$y }
}

function Find-NodeByText {
    param(
        [Parameter(Mandatory)][xml]$Xml,
        [Parameter(Mandatory)][string]$TextFragment,
        [switch]$CaseSensitive
    )
    $query = if ($CaseSensitive) {
        "//node[contains(@text,'$TextFragment')]"
    } else {
        # Case-insensitive via translate trick
        $lower = $TextFragment.ToLowerInvariant()
        "//node[contains(translate(@text,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'$lower')]"
    }
    return $Xml.SelectSingleNode($query)
}

function Tap-ByText {
    param(
        [Parameter(Mandatory)][string]$TextFragment,
        [Parameter(Mandatory)][string]$DumpName
    )
    $dev = "/sdcard/$DumpName"
    $loc = Join-Path $dumpXmlDir $DumpName
    Dump-UiXml -DevicePath $dev -LocalPath $loc
    [xml]$doc = Get-Content $loc -Raw
    $node = Find-NodeByText -Xml $doc -TextFragment $TextFragment
    if (-not $node) { return $false }
    $center = Get-NodeCenter -Bounds $node.GetAttribute("bounds")
    if (-not $center) { return $false }
    Invoke-Adb @("shell","input","tap",$center.X,$center.Y)
    return $true
}

function Back-Many {
    param([int]$Times = 1, [int]$DelayMs = 200)
    1..$Times | ForEach-Object {
        Invoke-Adb @("shell","input","keyevent","4")
        Start-Sleep -Milliseconds $DelayMs
    }
}

function Open-PackageInPlayStore {
    param([Parameter(Mandatory)][string]$PackageName)
    Invoke-Adb @("shell","am","start","-a","android.intent.action.VIEW","-d","market://details?id=$PackageName") | Out-Null
    Start-Sleep -Seconds $postLaunchWait
}

function Stop-HealthConnect {
    # Opens HC settings page (public package) then force-stops the controller (public service)
    Invoke-Adb @("shell","am","start","-a","android.settings.APPLICATION_DETAILS_SETTINGS","-d","package:com.google.android.apps.healthdata") | Out-Null
    Start-Sleep -Seconds $postLaunchWait
    Invoke-Adb @("shell","am","force-stop","com.google.android.healthconnect.controller") | Out-Null
    Start-Sleep -Seconds 5
}

function Invoke-PlayStoreUninstall {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$PackageName)

    Open-PackageInPlayStore -PackageName $PackageName

    # Find and tap "Uninstall"
    if (Tap-ByText -TextFragment "Uninstall" -DumpName "uninstall_dump.xml") {
        Start-Sleep -Milliseconds 500

        # Confirm dialog: try "Uninstall", then "OK", then "Remove"
        $confirmed =
            (Tap-ByText -TextFragment "Uninstall" -DumpName "confirm_uninstall_dump.xml") -or
            (Tap-ByText -TextFragment "OK"         -DumpName "confirm_ok_dump.xml")       -or
            (Tap-ByText -TextFragment "Remove"     -DumpName "confirm_remove_dump.xml")

        if (-not $confirmed) {
            Write-Host "  → Could not find confirm button; attempting package manager uninstall"
            Invoke-Adb @("shell","pm","uninstall",$PackageName) | Out-Null
        }
    } else {
        Write-Host "  → No Uninstall button found; attempting package manager uninstall"
        Invoke-Adb @("shell","pm","uninstall",$PackageName) | Out-Null
    }

    Start-Sleep -Seconds $postLaunchWait
}

# ─── Read package names from JSON ──────────────────────────────────────────────
$packages = Get-Content -Path $packageListFile -Raw | ConvertFrom-Json

foreach ($package in $packages) {
    $already = Join-Path $screenshotDir "screen_$package.png"
    if (Test-Path $already) {
        Write-Host "=== Skipping $package (screenshot exists) ==="
        continue
    }

    Write-Host "=== Processing package: $package ==="

    # Step 1: Open Play Store page & try “Install”
    Open-PackageInPlayStore -PackageName $package

    # Tap "Install" by text
    $installed = $false
    if (Tap-ByText -TextFragment "Install" -DumpName "install_dump.xml") {
        Start-Sleep -Seconds $downloadWait
        $installed = $true
    } else {
        Write-Host "  → No Install button; screenshot & skip"
        Start-Sleep -Seconds $screenshotWait
        Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
        Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
        Stop-HealthConnect
        continue
    }

    # Step 2: Launch Health Connect via Settings → “Open”
    Invoke-Adb @("shell","am","start","-a","android.settings.APPLICATION_DETAILS_SETTINGS","-d","package:com.google.android.apps.healthdata") | Out-Null
    Start-Sleep -Seconds $postLaunchWait

    if (-not (Tap-ByText -TextFragment "Open" -DumpName "hc_open_dump.xml")) {
        Write-Host "  → Could not find 'Open' button; screenshot & cleanup"
        Start-Sleep -Seconds $screenshotWait
        Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
        Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
        Stop-HealthConnect
        if ($installed) { Invoke-PlayStoreUninstall -PackageName $package }
        continue
    }
    Start-Sleep -Seconds $postLaunchWait

    # Step 3: Dump “App permissions” list & open it
    if (-not (Tap-ByText -TextFragment "App permissions" -DumpName "ap_dump.xml")) {
        Write-Host "  → 'App permissions' missing; screenshot & skip"
        Start-Sleep -Seconds $screenshotWait
        Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
        Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
        Back-Many -Times 3
        Stop-HealthConnect
        if ($installed) { Invoke-PlayStoreUninstall -PackageName $package }
        continue
    }
    Start-Sleep -Seconds $postLaunchWait

    # Step 5: Tap “Not allowed access” and check “No apps denied”
    $dev = "/sdcard/ca_dump.xml"
    $loc = Join-Path $dumpXmlDir "ca_dump.xml"
    Dump-UiXml -DevicePath $dev -LocalPath $loc
    [xml]$doc = Get-Content $loc -Raw

    $na = Find-NodeByText -Xml $doc -TextFragment "Not allowed access"
    if ($na) {
        $center = Get-NodeCenter -Bounds $na.GetAttribute("bounds")
        if ($center) {
            # Slight nudge downward (same as original script intent)
            Invoke-Adb @("shell","input","tap",$center.X, ($center.Y + 100))
            Start-Sleep -Seconds $postLaunchWait
        }

        Dump-UiXml -DevicePath "/sdcard/deny_dump.xml" -LocalPath (Join-Path $dumpXmlDir "deny_dump.xml")
        [xml]$denyDoc = Get-Content (Join-Path $dumpXmlDir "deny_dump.xml") -Raw
        if (Find-NodeByText -Xml $denyDoc -TextFragment "No apps denied") {
            Write-Host "  → No apps denied; screenshot & skip"
            Start-Sleep -Seconds $screenshotWait
            Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
            Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
            Back-Many -Times 3
            Stop-HealthConnect
            if ($installed) {
                # Prefer Play Store path; fallback to pm uninstall inside helper
                Invoke-PlayStoreUninstall -PackageName $package
            }
            continue
        }
    } else {
        Write-Host "  → 'Not allowed access' missing; screenshot & skip"
        Start-Sleep -Seconds $screenshotWait
        Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
        Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
        Back-Many -Times 3
        Stop-HealthConnect
        if ($installed) { Invoke-PlayStoreUninstall -PackageName $package }
        continue
    }

    # Step 6: Scroll (generic swipe)
    1..4 | ForEach-Object {
        Invoke-Adb @("shell","input","swipe","500","1800","500","600","500") | Out-Null
        Start-Sleep -Seconds 1
    }
    Start-Sleep -Seconds $postLaunchWait

    # Step 7: Tap “Read privacy policy” (text-driven) or skip+ss
    if (-not (Tap-ByText -TextFragment "Read privacy policy" -DumpName "rpp_dump.xml")) {
        Write-Host "  → ‘Read privacy policy’ missing; screenshot & skip"
        Start-Sleep -Seconds $screenshotWait
        Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
        Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null
        Stop-HealthConnect
        continue
    }

    # Step 8: Screenshot the policy page
    Start-Sleep -Seconds $screenshotWait
    Invoke-Adb @("shell","screencap","-p","/sdcard/screen_$package.png") | Out-Null
    Invoke-Adb @("pull","/sdcard/screen_$package.png",(Join-Path $screenshotDir "screen_$package.png")) | Out-Null

    # Step 9: Back out & terminate
    Back-Many -Times 3
    Stop-HealthConnect

    # Step 10: Uninstall the app
    if ($installed) {
        Invoke-PlayStoreUninstall -PackageName $package
    }

    Write-Host "=== Done with $package ===`n"
}
