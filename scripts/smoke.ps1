param(
  [string] $BaseUrl = "http://127.0.0.1:8000",
  [string] $Wallet = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Json {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Method,

    [Parameter(Mandatory = $true)]
    [string] $Url,

    [Parameter(Mandatory = $false)]
    [object] $Body
  )

  $params = @{
    Method = $Method
    Uri = $Url
    TimeoutSec = 30
  }
  if ($Body) {
    $params.ContentType = "application/json"
    $params.Body = ($Body | ConvertTo-Json -Depth 10)
  }
  Invoke-RestMethod @params
}

Write-Host "Checking $BaseUrl/api/health..."
$health = Invoke-Json -Method "GET" -Url "$BaseUrl/api/health"
if (-not $health.ok) {
  throw "Health check failed."
}
Write-Host "Health ok: $($health.app)"
if ($null -eq $health.monitor) {
  throw "Health response is missing monitor status."
}
Write-Host "Monitor running: $($health.monitor.monitor_running); last ok: $($health.monitor.last_monitor_ok_at)"

Write-Host "Checking watchlist..."
$wallets = Invoke-Json -Method "GET" -Url "$BaseUrl/api/watched-wallets"
Write-Host "Watchlist wallets: $($wallets.Count)"

if ($Wallet) {
  if ($Wallet -notmatch "^0x[a-fA-F0-9]{40}$") {
    throw "Wallet must be a valid 0x address."
  }

  Write-Host "Refreshing state for $Wallet..."
  $state = Invoke-Json -Method "POST" -Url "$BaseUrl/api/state" -Body @{ user = $Wallet }
  Write-Host "Positions: $($state.snapshot.positions.Count); changes: $($state.changes.Count); alerts: $($state.alerts.Count)"

  Write-Host "Checking summary..."
  $summary = Invoke-Json -Method "GET" -Url "$BaseUrl/api/wallets/$Wallet/summary?hours=24"
  Write-Host "Snapshots: $($summary.snapshot_count)/24h, total: $($summary.total_snapshot_count), enough trend data: $($summary.data_sufficient)"

  Write-Host "Refreshing fills..."
  $fillsResult = Invoke-Json -Method "POST" -Url "$BaseUrl/api/fills" -Body @{ user = $Wallet; aggregate_by_time = $true }
  Write-Host "Fetched fills: $($fillsResult.fetched_count); saved new fills: $($fillsResult.saved_count)"

  Write-Host "Checking stored fills..."
  $fills = Invoke-Json -Method "GET" -Url "$BaseUrl/api/fills?user=$Wallet&limit=10"
  Write-Host "Stored fills returned: $($fills.Count)"
}
else {
  Write-Host "No wallet supplied. Pass -Wallet 0x... to run state, summary, and fills smoke checks."
}

Write-Host "Smoke checks passed."
