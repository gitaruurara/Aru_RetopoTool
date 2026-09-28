param([string]$MayaVersion = "2027", [string]$BinaryName = "aru_retopo_maya_projector_basis.dll", [switch]$SleepingTeam, [switch]$PrecomputePath, [switch]$IdentityProjection, [ValidateRange(1,24)][int]$RouteWorkers = 4)
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
    $extraFlags=@("/DARU_ROUTE_WORKERS=$RouteWorkers")
    if ($IdentityProjection) { $extraFlags += "/DARU_PROJECTOR_IDENTITY" }
    if ($PrecomputePath) { $extraFlags += "/DARU_PATH_PRECOMPUTE" }
    if ($SleepingTeam) { $extraFlags += "/DARU_PROJECTOR_SLEEPING_TEAM" }
    & "$toolset/bin/Hostx64/x64/cl.exe" @extraFlags /nologo /std:c++17 /O2 /openmp /W4 /EHsc /MD /LD /DNT_PLUGIN /DREQUIRE_IOSTREAM "/I$mayaRoot/include" "$PSScriptRoot/maya_projector_basis_candidate.cpp" "/Fe:$BinaryName" /link "/LIBPATH:$mayaRoot/lib" OpenMaya.lib Foundation.lib
    if ($LASTEXITCODE -ne 0) { throw "Maya projector build failed: $LASTEXITCODE" }
} finally { Pop-Location }
