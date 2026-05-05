[CmdletBinding()]
param(
	[string]$BaseUrl = "http://127.0.0.1:8000",
	[switch]$AutoStartServer
)

$ErrorActionPreference = "Stop"

$script:Passed = 0
$script:Failed = 0
$serverProcess = $null

function Write-Section {
	param([string]$Text)
	Write-Host ""
	Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Assert-True {
	param(
		[bool]$Condition,
		[string]$Name,
		[string]$FailMessage
	)

	if ($Condition) {
		$script:Passed += 1
		Write-Host "[PASS] $Name" -ForegroundColor Green
	}
	else {
		$script:Failed += 1
		Write-Host "[FAIL] $Name : $FailMessage" -ForegroundColor Red
	}
}

function Assert-Equal {
	param(
		[string]$Name,
		[object]$Expected,
		[object]$Actual
	)

	$ok = "$Expected" -eq "$Actual"
	Assert-True -Condition $ok -Name $Name -FailMessage "expected '$Expected' but got '$Actual'"
}

function Invoke-Json {
	param(
		[string]$Method,
		[string]$Url,
		[object]$Body = $null
	)

	if ($null -ne $Body) {
		$json = $Body | ConvertTo-Json -Depth 10
		return Invoke-RestMethod -Uri $Url -Method $Method -ContentType "application/json" -Body $json
	}

	return Invoke-RestMethod -Uri $Url -Method $Method
}

function Assert-HttpStatus {
	param(
		[string]$Method,
		[string]$Url,
		[object]$Body,
		[int]$ExpectedStatus,
		[string]$Name
	)

	try {
		if ($null -ne $Body) {
			$json = $Body | ConvertTo-Json -Depth 10
			Invoke-RestMethod -Uri $Url -Method $Method -ContentType "application/json" -Body $json | Out-Null
		}
		else {
			Invoke-RestMethod -Uri $Url -Method $Method | Out-Null
		}

		Assert-True -Condition ($ExpectedStatus -ge 200 -and $ExpectedStatus -lt 300) -Name $Name -FailMessage "expected status $ExpectedStatus but request succeeded"
	}
	catch {
		$statusCode = -1
		if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
			$statusCode = [int]$_.Exception.Response.StatusCode
		}

		Assert-Equal -Name $Name -Expected $ExpectedStatus -Actual $statusCode
	}
}

function Wait-Health {
	param([string]$Url)

	for ($i = 0; $i -lt 20; $i++) {
		try {
			$health = Invoke-RestMethod -Uri "$Url/api/health" -Method Get
			if ($health.status -eq "ok") {
				return $true
			}
		}
		catch {
			Start-Sleep -Milliseconds 500
		}
	}

	return $false
}

function Start-LocalServerIfNeeded {
	param([string]$Url)

	if (-not $AutoStartServer) {
		return $null
	}

	$repoRoot = Split-Path -Parent $PSScriptRoot
	$backendPath = Join-Path $repoRoot "backend"

	Write-Section "Starting local backend"
	$proc = Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $backendPath -PassThru

	$ready = Wait-Health -Url $Url
	Assert-True -Condition $ready -Name "Server startup" -FailMessage "server did not become healthy"

	if (-not $ready) {
		try { Stop-Process -Id $proc.Id -Force } catch {}
		throw "Cannot continue tests because server did not start."
	}

	return $proc
}

try {
	$serverProcess = Start-LocalServerIfNeeded -Url $BaseUrl

	Write-Section "Basic availability"
	$health = Invoke-Json -Method "GET" -Url "$BaseUrl/api/health"
	Assert-Equal -Name "Health endpoint status" -Expected "ok" -Actual $health.status

	$home = Invoke-WebRequest -Uri "$BaseUrl/" -Method Get
	Assert-Equal -Name "Root page HTTP status" -Expected 200 -Actual $home.StatusCode

	Write-Section "Reset to known state"
	$resetState = Invoke-Json -Method "POST" -Url "$BaseUrl/api/reset"
	Assert-Equal -Name "Reset mode value" -Expected 1 -Actual $resetState.mode.value
	Assert-Equal -Name "Reset rgb status" -Expected "green" -Actual $resetState.devices.rgb_status

	Write-Section "Mode and RGB logic"
	$mode2 = Invoke-Json -Method "POST" -Url "$BaseUrl/api/mode" -Body @{ mode = 2 }
	Assert-Equal -Name "Mode 2 label" -Expected "Scheduled mode" -Actual $mode2.mode.label
	Assert-Equal -Name "Mode 2 rgb" -Expected "yellow" -Actual $mode2.devices.rgb_status

	$mode1 = Invoke-Json -Method "POST" -Url "$BaseUrl/api/mode" -Body @{ mode = 1 }
	Assert-Equal -Name "Mode 1 rgb" -Expected "green" -Actual $mode1.devices.rgb_status

	Write-Section "Auto rule in mode 1"
	$autoOn = Invoke-Json -Method "POST" -Url "$BaseUrl/api/sensor-data" -Body @{
		temperature   = 30
		humidity      = 55
		soil_moisture = 20
		light         = 500
	}
	Assert-Equal -Name "Auto turns P10 on" -Expected "on" -Actual $autoOn.devices.pump_p10

	$autoOff = Invoke-Json -Method "POST" -Url "$BaseUrl/api/sensor-data" -Body @{
		temperature   = 30
		humidity      = 55
		soil_moisture = 90
		light         = 1000
	}
	Assert-Equal -Name "Auto turns P10 off" -Expected "off" -Actual $autoOff.devices.pump_p10

	Write-Section "Manual control behavior"
	$manual = Invoke-Json -Method "POST" -Url "$BaseUrl/api/control" -Body @{
		device = "pump_p13"
		state  = "on"
	}
	Assert-Equal -Name "Manual sets mode 0" -Expected 0 -Actual $manual.mode.value
	Assert-Equal -Name "Manual sets rgb red" -Expected "red" -Actual $manual.devices.rgb_status
	Assert-Equal -Name "Manual turns P13 on" -Expected "on" -Actual $manual.devices.pump_p13

	Write-Section "Simulation and history"
	$sim = Invoke-Json -Method "POST" -Url "$BaseUrl/api/simulate"
	$hasHistory = ($sim.history.temperature.Count -gt 0) -and ($sim.history.light.Count -gt 0)
	Assert-True -Condition $hasHistory -Name "History updated after simulate" -FailMessage "history arrays are empty"

	Write-Section "Validation errors"
	Assert-HttpStatus -Method "POST" -Url "$BaseUrl/api/thresholds" -Body @{
		soil_low            = 70
		soil_high           = 50
		light_low           = 600
		gdd_light_threshold = 2000
	} -ExpectedStatus 422 -Name "Reject invalid thresholds"

	Assert-HttpStatus -Method "POST" -Url "$BaseUrl/api/sensor-data" -Body @{
		temperature = 30
		humidity    = 50
	} -ExpectedStatus 422 -Name "Reject missing sensor fields"
}
catch {
	$script:Failed += 1
	Write-Host "[FATAL] $($_.Exception.Message)" -ForegroundColor Red
}
finally {
	if ($null -ne $serverProcess) {
		try {
			Stop-Process -Id $serverProcess.Id -Force
			Write-Host "\nStopped local backend process $($serverProcess.Id)."
		}
		catch {
			Write-Host "\nCould not stop backend process automatically."
		}
	}
}

Write-Host ""
Write-Host "=== Test summary ===" -ForegroundColor Cyan
Write-Host "Passed: $script:Passed"
Write-Host "Failed: $script:Failed"

if ($script:Failed -gt 0) {
	exit 1
}

exit 0
