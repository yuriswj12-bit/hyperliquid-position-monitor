$ErrorActionPreference = "Stop"

$repo = "yuriswj12-bit/hyperliquid-position-monitor"
$branch = "codex/mvp-hyperdress-monitor"
$message = "Add wallet risk activity summary"
$files = @(
  ".env.example",
  "README.md",
  "PRODUCT_SPEC.md",
  "app/config.py",
  "app/ai_analyst.py",
  "app/models.py",
  "app/risk.py",
  "app/storage.py",
  "app/main.py",
  "app/telegram_bot.py",
  "public/index.html",
  "public/app.js",
  "public/styles.css",
  "scripts/push_phase2.ps1"
)

function Invoke-GhJson {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Args,

    [Parameter(Mandatory = $false)]
    [string] $PayloadPath
  )

  if ($PayloadPath) {
    $output = gh @Args --input $PayloadPath
    if ($LASTEXITCODE -ne 0) {
      throw "gh failed: gh $($Args -join ' ') --input $PayloadPath"
    }
    return $output | ConvertFrom-Json
  }

  $output = gh @Args
  if ($LASTEXITCODE -ne 0) {
    throw "gh failed: gh $($Args -join ' ')"
  }
  return $output | ConvertFrom-Json
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

foreach ($file in $files) {
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
