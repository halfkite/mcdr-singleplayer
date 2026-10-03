param(
    [string]$PythonPath = '',
    [string]$ArchiveScript = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) { $PythonPath = Join-Path $taskRoot '.venv/Scripts/python.exe' }
if (-not $ArchiveScript) { $ArchiveScript = Join-Path $env:USERPROFILE '.codex/skills/build-game-mods/scripts/archive_mod_build.py' }
if (-not (Test-Path -LiteralPath $ArchiveScript)) { throw "Archive script missing: $ArchiveScript" }
Push-Location $taskRoot
try {
    $taskVersion = (Get-Content -LiteralPath 'python/mcdreforged.plugin.json' -Raw | ConvertFrom-Json).version
    & $PythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed' }
    & (Join-Path $taskRoot 'fabric-bridge/gradlew.bat') -p fabric-bridge build --console=plain
    if ($LASTEXITCODE -ne 0) { throw 'Fabric 26.3 build failed' }
    # Archive the installable jar immediately after every successful actual mod build.
    & $PythonPath $ArchiveScript --artifact "fabric-bridge/build/libs/mcdr-singleplayer-$taskVersion.jar" --output-root 'mod-builds' --mod-name 'mcdr-singleplayer' --game-version '26.3 Fabric' --build-command 'fabric-bridge/gradlew.bat -p fabric-bridge build --console=plain'
    if ($LASTEXITCODE -ne 0) { throw 'Mod build archive failed' }
    & $PythonPath 'scripts/package_release.py'
    if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed' }
    & $PythonPath $ArchiveScript --artifact "dist/singleplayer_bridge-$taskVersion.mcdr" --artifact "dist/singleplayer_prime_backup-$taskVersion.mcdr" --artifact "dist/singleplayer_chunk_backup-$taskVersion.mcdr" --artifact "dist/mcdr-singleplayer-$taskVersion-mc26.3-fabric.zip" --output-root 'mod-builds' --mod-name 'mcdr-singleplayer release bundle' --game-version '26.3 Fabric' --build-command 'python -m mcdreforged pack; python scripts/package_release.py'
    if ($LASTEXITCODE -ne 0) { throw 'Release archive failed' }
} finally {
    Pop-Location
}
