param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)

$ErrorActionPreference = 'Stop'
$version = '0.2.0'
$archiveName = "nemo-speech-$version-windows-x86_64-cpu.zip"
$archiveUrl = "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v$version/$archiveName"
$archiveHash = '82c80451086e86194aba9af19f800da77cd66d1c28d993d0efceffd6cdb49bb8'
$work = Join-Path $env:TEMP "speak-runtime-$version"
$archive = Join-Path $work $archiveName
$extract = Join-Path $work 'extract'
$vendor = Join-Path $PSScriptRoot 'vendor\nemo-speech'
$llamaVersion = 'b11669'
$llamaArchiveName = "llama-$llamaVersion-bin-win-cpu-x64.zip"
$llamaArchiveUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$llamaVersion/$llamaArchiveName"
$llamaArchiveHash = '37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b'
$llamaWork = Join-Path $env:TEMP "speak-llama-$llamaVersion"
$llamaArchive = Join-Path $llamaWork $llamaArchiveName
$llamaExtract = Join-Path $llamaWork 'extract'
$llamaVendor = Join-Path $PSScriptRoot 'vendor\llama-cpp'

New-Item -ItemType Directory -Force $work | Out-Null
if (-not (Test-Path $archive)) {
    Invoke-WebRequest $archiveUrl -OutFile $archive
}
$actualHash = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $archiveHash) {
    Remove-Item $archive -Force
    throw "NeMo-Speech.cpp checksum mismatch: $actualHash"
}

Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $archive $extract -Force
$runtime = Get-ChildItem $extract -Directory | Select-Object -First 1
if (-not $runtime -or -not (Test-Path (Join-Path $runtime.FullName 'bin\nemo-speech.exe'))) {
    throw 'Could not find nemo-speech.exe in the verified runtime archive.'
}
Remove-Item $vendor -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Split-Path $vendor) | Out-Null
Copy-Item $runtime.FullName $vendor -Recurse

New-Item -ItemType Directory -Force $llamaWork | Out-Null
if (-not (Test-Path $llamaArchive)) {
    Invoke-WebRequest $llamaArchiveUrl -OutFile $llamaArchive
}
$actualLlamaHash = (Get-FileHash $llamaArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualLlamaHash -ne $llamaArchiveHash) {
    Remove-Item $llamaArchive -Force
    throw "llama.cpp checksum mismatch: $actualLlamaHash"
}
Remove-Item $llamaExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $llamaArchive $llamaExtract -Force
if (-not (Test-Path (Join-Path $llamaExtract 'llama-server.exe'))) {
    throw 'Could not find llama-server.exe in the verified llama.cpp archive.'
}
Remove-Item $llamaVendor -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item $llamaExtract $llamaVendor -Recurse

$venv = Join-Path $PSScriptRoot '.venv'
if (-not (Test-Path $venv)) {
    py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install application build dependencies.' }
& (Join-Path $venv 'Scripts\python.exe') -m PyInstaller --noconfirm --clean --onefile --windowed --name Speak `
    --distpath $OutputDirectory `
    --add-data "$vendor;vendor\nemo-speech" `
    --add-data "$llamaVendor;vendor\llama-cpp" `
    --collect-all sounddevice `
    (Join-Path $PSScriptRoot 'speak.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller packaging failed.' }

Write-Host "Built app: $(Join-Path $OutputDirectory 'Speak.exe')"
Write-Host 'Distribute this executable. ASR and cleanup weights download on first use.'
