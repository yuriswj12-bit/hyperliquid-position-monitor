param(
  [string] $StartAt = ""
)

$ErrorActionPreference = "Stop"

$repo = "yuriswj12-bit/hyperliquid-position-monitor"
$branch = "codex/mvp-hyperdress-monitor"
$message = "Add release check scripts"
$files = @(
  ".env.example",
  ".gitignore",
  "Dockerfile",
  "docker-compose.yml",
  "README.md",
  "PRODUCT_SPEC.md",
  "requirements.txt",
  "app/__init__.py",
  "app/config.py",
  "app/ai_analyst.py",
  "app/hyperliquid.py",
  "app/notifier.py",
  "app/reporting.py",
  "app/models.py",
  "app/risk.py",
  "app/storage.py",
  "app/main.py",
  "app/telegram_bot.py",
  "public/index.html",
  "public/app.js",
  "public/styles.css",
  "scripts/check.ps1",
  "scripts/smoke.ps1",
  "scripts/dev.ps1",
  "scripts/dev.sh",
  "scripts/push_phase2.ps1",
  "tests/test_risk.py",
  "tests/test_reporting.py",
  "tests/test_telegram_formatting.py"
)

function Invoke-GhJson {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Args,

    [Parameter(Mandatory = $false)]
    [string] $PayloadPath
  )

  $attempt = 1
  $maxAttempts = 5
  while ($attempt -le $maxAttempts) {
    if ($PayloadPath) {
      $output = gh @Args --input $PayloadPath
      if ($LASTEXITCODE -eq 0) {
        return $output | ConvertFrom-Json
      }
    }
    else {
      $output = gh @Args
      if ($LASTEXITCODE -eq 0) {
        return $output | ConvertFrom-Json
      }
    }

    if ($attempt -lt $maxAttempts) {
      $sleepSeconds = [Math]::Min(30, 3 * $attempt)
      Write-Host "  gh failed, retrying in $sleepSeconds seconds ($attempt/$maxAttempts)..."
      Start-Sleep -Seconds $sleepSeconds
    }
    $attempt += 1
  }

  if ($PayloadPath) {
    throw "gh failed: gh $($Args -join ' ') --input $PayloadPath"
  }
  throw "gh failed: gh $($Args -join ' ')"
}

function Write-JsonNoBom {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [object] $Value
  )

  $json = $Value | ConvertTo-Json -Depth 10
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

Write-Host "Updating PR branch $branch file by file..."
$encodedBranch = [System.Uri]::EscapeDataString($branch)

$started = [string]::IsNullOrWhiteSpace($StartAt)
foreach ($file in $files) {
  if (-not $started) {
    if ($file -eq $StartAt) {
      $started = $true
    }
    else {
      continue
    }
  }

  Write-Host "Updating $file..."
  $encodedPath = ($file -split "[\\/]" | ForEach-Object { [System.Uri]::EscapeDataString($_) }) -join "/"
  $current = $null
  $oldErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $currentOutput = & gh api "repos/$repo/contents/$encodedPath`?ref=$encodedBranch" 2>$null
    if ($LASTEXITCODE -eq 0 -and $currentOutput) {
      $current = $currentOutput | ConvertFrom-Json
    }
  }
  catch {
    $current = $null
  }
  finally {
    $ErrorActionPreference = $oldErrorActionPreference
  }
  $content = Get-Content -Raw -Encoding UTF8 $file
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
  $base64 = [Convert]::ToBase64String($bytes)
  $payloadPath = Join-Path (Get-Location) ".codex-update-$($file -replace '[\\/]', '_').json"

  try {
    $payload = @{
      message = "$message ($file)"
      content = $base64
      branch = $branch
    }
    if ($current) {
      $payload.sha = $current.sha
    }
    Write-JsonNoBom -Path $payloadPath -Value $payload

    $result = Invoke-GhJson -Args @("api", "repos/$repo/contents/$encodedPath", "--method", "PUT") -PayloadPath $payloadPath
    Write-Host "  -> $($result.commit.sha)"
  }
  finally {
    Remove-Item -Force $payloadPath -ErrorAction SilentlyContinue
  }
}

Write-Host "Done."
Write-Host "PR: https://github.com/yuriswj12-bit/hyperliquid-position-monitor/pull/1"
