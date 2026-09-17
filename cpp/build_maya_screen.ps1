param([string]$MayaVersion = "2027", [string]$BinaryName = "aru_retopo_maya_screen_v1.dll", [switch]$Matrix, [switch]$Hull)
$ErrorActionPreference = 'Stop'
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ build tools are required.' }
$toolset = (Get-ChildItem -LiteralPath "$vs/VC/Tools/MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = "${env:ProgramFiles(x86)}/Windows Kits/10"
$sdkVersion = (Get-ChildItem -LiteralPath "$sdkRoot/Include" -Directory | Where-Object { Test-Path -LiteralPath "$($_.FullName)/um/Windows.h" } | Sort-Object Name -Descending | Select-Object -First 1).Name
$env:INCLUDE = "$toolset/include;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/um"
$env:LIB = "$toolset/lib/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64;$sdkRoot/Lib/$sdkVersion/um/x64"

$mayaRoot = "C:/Program Files/Autodesk/Maya$MayaVersion"
$output = Join-Path $PSScriptRoot "../bin/$MayaVersion"
New-Item -ItemType Directory -Force -Path $output | Out-Null
Push-Location $output
try {
    $extraFlags=@()
    if ($Hull) { $extraFlags += "/DARU_SCREEN_HULL" }
    if ($Matrix) { $extraFlags += "/DARU_SCREEN_MATRIX" }
    & "$toolset/bin/Hostx64/x64/cl.exe" @extraFlags /nologo /std:c++17 /O2 /W4 /EHsc /MD /LD /DNT_PLUGIN /DREQUIRE_IOSTREAM "/I$mayaRoot/include" "$PSScriptRoot/maya_screen.cpp" "/Fe:$BinaryName" /link "/LIBPATH:$mayaRoot/lib" OpenMaya.lib OpenMayaUI.lib Foundation.lib
    if ($LASTEXITCODE -ne 0) { throw "Maya screen projection build failed: $LASTEXITCODE" }
} finally { Pop-Location }
