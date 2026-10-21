param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)

$ErrorActionPreference = 'Stop'
$nemoVersion = '0.2.0'
$llamaVersion = 'b11669'
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()

if ($IsWindows -and $architecture -eq 'x64') {
    $platform = 'windows-x64'
    $nemoAsset = "nemo-speech-$nemoVersion-windows-x86_64-cpu.zip"
    $nemoHash = '82c80451086e86194aba9af19f800da77cd66d1c28d993d0efceffd6cdb49bb8'
    $llamaAsset = "llama-$llamaVersion-bin-win-vulkan-x64.zip"
    $llamaHash = '2c07574e7bde71321cb785282b20cc821e951132149eeceeea32ddebdbf0598e'
} elseif ($IsMacOS -and $architecture -eq 'arm64') {
    $platform = 'macos-arm64'
    $nemoAsset = "nemo-speech-$nemoVersion-macos-aarch64-metal.tar.gz"
    $nemoHash = '5cb02ba7c04f0b5585ce5cde9c830be5f0b7dfb4c83083c500109c381b4f2da9'
    $llamaAsset = "llama-$llamaVersion-bin-macos-arm64.tar.gz"
    $llamaHash = 'dbed55493d72bc1ba2babc8770d669c2289b5bc4ee9fb2a4dfc158d45b7d13fd'
} elseif ($IsMacOS -and $architecture -eq 'x64') {
    $platform = 'macos-x64'
    $nemoAsset = "nemo-speech-$nemoVersion-macos-x86_64-cpu.tar.gz"
    $nemoHash = 'd52c318d8197511d4f7eee02bcf05511f7e91b300555a130b562e571695a0f39'
    $llamaAsset = "llama-$llamaVersion-bin-macos-x64.tar.gz"
    $llamaHash = 'cab28238d78158109b48deb27b05d50e0dcef56275d2e76da9ca8281526c7532'
} elseif ($IsLinux -and $architecture -eq 'x64') {
    $platform = 'linux-x86_64'
    $nemoAsset = "nemo-speech-$nemoVersion-linux-x86_64-cpu.tar.gz"
    $nemoHash = 'f396057150f1b774935c7414fd32ebc04195a795a34120d78d8c9ecefa1b7507'
    $llamaAsset = "llama-$llamaVersion-bin-ubuntu-x64.tar.gz"
    $llamaHash = 'cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac'
} else {
    throw "Unsupported build platform: $([System.Runtime.InteropServices.RuntimeInformation]::OSDescription) $architecture"
}

$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $PSScriptRoot $OutputDirectory }
$outputPath = [System.IO.Path]::GetFullPath($outputPath)
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "speak-build-$PID"
$vendor = Join-Path $PSScriptRoot 'vendor'
$nemoVendor = Join-Path $vendor 'nemo-speech'
$llamaVendor = Join-Path $vendor 'llama-cpp'
$archiveRoot = "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v$nemoVersion"
$llamaRoot = "https://github.com/ggml-org/llama.cpp/releases/download/$llamaVersion"
$nemoArchive = Join-Path $tempRoot $nemoAsset
$llamaArchive = Join-Path $tempRoot $llamaAsset

New-Item -ItemType Directory -Force $tempRoot, $outputPath | Out-Null
try {
    Invoke-WebRequest "$archiveRoot/$nemoAsset" -OutFile $nemoArchive
    Invoke-WebRequest "$llamaRoot/$llamaAsset" -OutFile $llamaArchive
    foreach ($asset in @(@{ Path = $nemoArchive; Hash = $nemoHash; Name = 'NeMo-Speech.cpp' },
                         @{ Path = $llamaArchive; Hash = $llamaHash; Name = 'llama.cpp' })) {
        $actualHash = (Get-FileHash $asset.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $asset.Hash) { throw "$($asset.Name) checksum mismatch: $actualHash" }
    }

    $nemoExtract = Join-Path $tempRoot 'nemo'
    $llamaExtract = Join-Path $tempRoot 'llama'
    New-Item -ItemType Directory -Force $nemoExtract, $llamaExtract | Out-Null
    if ($nemoAsset.EndsWith('.zip')) { Expand-Archive $nemoArchive $nemoExtract -Force }
    else { & tar -xzf $nemoArchive -C $nemoExtract; if ($LASTEXITCODE -ne 0) { throw 'NeMo archive extraction failed.' } }
    if ($llamaAsset.EndsWith('.zip')) { Expand-Archive $llamaArchive $llamaExtract -Force }
    else { & tar -xzf $llamaArchive -C $llamaExtract; if ($LASTEXITCODE -ne 0) { throw 'llama archive extraction failed.' } }

    $nemoExecutableName = if ($IsWindows) { 'nemo-speech.exe' } else { 'nemo-speech' }
    $llamaExecutableName = if ($IsWindows) { 'llama-server.exe' } else { 'llama-server' }
    $nemoExecutable = Get-ChildItem $nemoExtract -Recurse -File | Where-Object {
        $_.Name -eq $nemoExecutableName -and (Split-Path $_.DirectoryName -Leaf) -eq 'bin'
    } | Select-Object -First 1
    $llamaExecutable = Get-ChildItem $llamaExtract -Recurse -File | Where-Object { $_.Name -eq $llamaExecutableName } | Select-Object -First 1
    if (-not $nemoExecutable -or -not $llamaExecutable) { throw 'Expected runtime executables were not found in the verified archives.' }

    Remove-Item $nemoVendor, $llamaVendor -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $vendor, $nemoVendor, $llamaVendor | Out-Null
    $nemoRuntime = Split-Path (Split-Path $nemoExecutable.FullName -Parent) -Parent
    Get-ChildItem $nemoRuntime -Force | Copy-Item -Destination $nemoVendor -Recurse -Force
    $llamaRuntime = Split-Path $llamaExecutable.FullName -Parent
    if ((Split-Path $llamaRuntime -Leaf) -eq 'bin') { $llamaRuntime = Split-Path $llamaRuntime -Parent }
    $llamaRelativeExecutable = $llamaExecutable.FullName.Substring($llamaRuntime.Length).TrimStart([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    Get-ChildItem $llamaRuntime -Force | Copy-Item -Destination $llamaVendor -Recurse -Force
    if (-not $IsWindows) {
        & chmod +x (Join-Path $nemoVendor 'bin/nemo-speech') (Join-Path $llamaVendor $llamaRelativeExecutable)
        if ($LASTEXITCODE -ne 0) { throw 'Could not mark runtime executables as executable.' }
    }

    $venv = Join-Path $PSScriptRoot '.venv'
    $python = if ($IsWindows) { Join-Path $venv 'Scripts/python.exe' } else { Join-Path $venv 'bin/python' }
    if (-not (Test-Path $python)) {
        & python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
    }
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install application build dependencies.' }
    $notices = Join-Path $PSScriptRoot 'build/THIRD_PARTY_NOTICES.txt'
    & $python (Join-Path $PSScriptRoot 'tools/make_notices.py') $notices
    if ($LASTEXITCODE -ne 0) { throw 'Could not create third-party notices.' }

    $dataSeparator = if ($IsWindows) { ';' } else { ':' }
    $pyinstallerArgs = @('--noconfirm', '--clean', '--windowed', '--name', 'Speak',
        '--distpath', $outputPath,
        '--add-data', "$nemoVendor${dataSeparator}vendor/nemo-speech",
        '--add-data', "$llamaVendor${dataSeparator}vendor/llama-cpp",
        '--add-data', "$notices${dataSeparator}.",
        '--additional-hooks-dir', (Join-Path $PSScriptRoot 'tools/hooks'),
        '--exclude-module', 'tkinter')
    if ($IsWindows) {
        $icon = Join-Path $PSScriptRoot 'build/speak.ico'
        & $python (Join-Path $PSScriptRoot 'tools/make_icon.py') $icon
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the app icon.' }
        $pyinstallerArgs += @('--onefile', '--icon', $icon)
    } elseif ($IsMacOS) {
        $pyinstallerArgs += @('--onedir', '--osx-bundle-identifier', 'com.speak.app')
    } else {
        $pyinstallerArgs += '--onedir'
    }
    $pyinstallerArgs += (Join-Path $PSScriptRoot 'main.py')
    & $python -m PyInstaller @pyinstallerArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller packaging failed.' }

    if ($IsMacOS) {
        $app = Join-Path $outputPath 'Speak.app'
        $plist = Join-Path $app 'Contents/Info.plist'
        & /usr/libexec/PlistBuddy -c 'Add :NSMicrophoneUsageDescription string "Speak uses the microphone to transcribe your speech locally."' $plist
        if ($LASTEXITCODE -ne 0) { throw 'Could not add the macOS microphone usage description.' }
        & ditto -c -k --sequesterRsrc --keepParent $app (Join-Path $outputPath "Speak-$platform.zip")
        if ($LASTEXITCODE -ne 0) { throw 'Could not archive the macOS app.' }
    } elseif ($IsLinux) {
        & tar -czf (Join-Path $outputPath "Speak-$platform.tar.gz") -C $outputPath Speak
        if ($LASTEXITCODE -ne 0) { throw 'Could not archive the Linux app.' }
    }
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Built $platform package in $outputPath"
