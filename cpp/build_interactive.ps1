param([string]$MayaVersion = "2027")
$ErrorActionPreference = 'Stop'
# Keep the ordinary UI backend reproducible with all adopted fast paths.
& "$PSScriptRoot/build_mesh_buffer.ps1" -MayaVersion $MayaVersion -NativeThreads 16 -BinaryName aru_retopo_mesh_buffer_certified.mll -NumericPipeline -ReuseScratch -IncrementalStencil -InputCache
if (-not $?) { throw 'Interactive mesh backend build failed.' }
