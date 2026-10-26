$ErrorActionPreference = "Stop"

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
  Write-Error "Flutter is not installed or is not in PATH. Install Flutter stable first."
  exit 1
}

$tempRoot = Join-Path $env:TEMP ("psc_mentor_shell_" + [guid]::NewGuid().ToString())
try {
  flutter create $tempRoot --project-name psc_mentor --org in.pscmentor --platforms=android,ios,macos,windows

  foreach ($platform in @("android", "ios", "macos", "windows")) {
    $destination = Join-Path (Get-Location) $platform
    if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
    Copy-Item (Join-Path $tempRoot $platform) $destination -Recurse
  }

  flutter pub get
  flutter doctor
  Write-Host "Platform shells generated without replacing lib/ or docs/. Run: flutter run"
}
finally {
  if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force }
}
