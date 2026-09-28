$ErrorActionPreference = 'Stop'
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ build tools are required.' }
$toolset = (Get-ChildItem -LiteralPath "$vs/VC/Tools/MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = "${env:ProgramFiles(x86)}/Windows Kits/10"
$sdkVersion = (Get-ChildItem -LiteralPath "$sdkRoot/Include" -Directory | Where-Object { Test-Path -LiteralPath "$($_.FullName)/um/Windows.h" } | Sort-Object Name -Descending | Select-Object -First 1).Name
$env:INCLUDE = "$toolset/include;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/um"
$env:LIB = "$toolset/lib/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64;$sdkRoot/Lib/$sdkVersion/um/x64"

$output = Join-Path $PSScriptRoot "../bin"
New-Item -ItemType Directory -Force -Path $output | Out-Null
Push-Location $output
try {
    & "$toolset/bin/Hostx64/x64/cl.exe" /nologo /std:c++17 /O2 /W4 /EHsc /MD /LD "$PSScriptRoot/transfer.cpp" /Fe:aru_retopo_transfer_v1.dll
    if ($LASTEXITCODE -ne 0) { throw "Transfer build failed: $LASTEXITCODE" }
} finally { Pop-Location }
