param([string]$MayaVersion = "2027", [ValidateRange(1,32)][int]$NativeThreads = 16, [string]$BinaryName = "aru_retopo_mesh_buffer_v6.mll", [switch]$NumericPipeline, [switch]$ReuseScratch, [switch]$IncrementalStencil, [switch]$InputCache, [switch]$GpuCompute, [switch]$CacheStats, [switch]$SleepingTeam, [ValidateRange(1,32)][int]$LeafSize = 8)
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
    $objectDir = Join-Path $output (".obj_" + [IO.Path]::GetFileNameWithoutExtension($BinaryName))
    New-Item -ItemType Directory -Force -Path $objectDir | Out-Null
    $extraFlags = @()
    if ($NumericPipeline) { $extraFlags += "/DARU_RETOPO_NUMERIC_PIPELINE" }
    if ($ReuseScratch) { $extraFlags += "/DARU_RETOPO_REUSE_SCRATCH" }
    if ($IncrementalStencil) { $extraFlags += "/DARU_RETOPO_INCREMENTAL_STENCIL" }
    if ($InputCache) { $extraFlags += "/DARU_RETOPO_INPUT_CACHE" }
    if ($GpuCompute) { $extraFlags += "/DARU_RETOPO_GPU_COMPUTE" }
    if ($SleepingTeam) { $extraFlags += "/DARU_RETOPO_SLEEPING_TEAM" }
    if ($CacheStats) { $extraFlags += "/DARU_RETOPO_CACHE_STATS" }
    & "$toolset/bin/Hostx64/x64/cl.exe" @extraFlags "/Fo$objectDir/" /nologo /std:c++17 /O2 /openmp /W4 /EHsc /MD /LD /DNT_PLUGIN /DREQUIRE_IOSTREAM "/DARU_RETOPO_THREADS=$NativeThreads" "/DARU_RETOPO_LEAF_SIZE=$LeafSize" "/I$mayaRoot/include" "$PSScriptRoot/mesh_buffer.cpp" "$PSScriptRoot/retopo.cpp" "/Fe:$BinaryName" /link "/LIBPATH:$mayaRoot/lib" OpenMaya.lib Foundation.lib
    if ($LASTEXITCODE -ne 0) { throw "Mesh buffer build failed: $LASTEXITCODE" }
} finally { Pop-Location }
