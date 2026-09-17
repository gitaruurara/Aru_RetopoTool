// Experimental opt-in backend. One device/context per serial Maya node.
#pragma once
#define NOMINMAX
#include <windows.h>
#include <string>
#include <vector>
#include <atomic>
static std::atomic<unsigned long long> gpuBackendStats[3]; // success, failure, surface create
extern "C" __declspec(dllexport) void aru_gpu_backend_stats(unsigned long long* out){for(int j=0;j<3;++j)out[j]=gpuBackendStats[j].load();}
class GPUBackend {
 HMODULE module=nullptr;void* surface=nullptr;bool failed=false;
 using Create=void*(*)(const double*,int,const int*,int,const wchar_t*);
 using Destroy=void(*)(void*);
 using Setup=int(*)(void*,int,const int*,const int*,const double*);
 using Relax=int(*)(void*,const double*,int,double*,int*,int,double,int);
 Create create=nullptr;Destroy destroy=nullptr;Setup setup=nullptr;Relax relax=nullptr;
 std::vector<int> rows,columns;std::vector<double> weights;
 static std::wstring env(const wchar_t* name){DWORD n=GetEnvironmentVariableW(name,nullptr,0);if(!n)return {};std::wstring value(n,L'\0');DWORD got=GetEnvironmentVariableW(name,&value[0],n);if(!got||got>=n)return {};value.resize(got);return value;}
public:
 ~GPUBackend(){reset();if(module)FreeLibrary(module);}
 void reset(){if(surface&&destroy)destroy(surface);surface=nullptr;failed=false;rows.clear();columns.clear();weights.clear();}
 bool run(const std::vector<double>& vertices,const std::vector<int>& triangles,std::vector<double>& points,const std::vector<int>& offsets,const std::vector<int>& neighbors,const std::vector<double>& anchors,int iterations,double strength,std::vector<int>& seeds,int guard){
  if(failed)return false;
  auto library=env(L"ARU_RETOPO_GPU_DLL"),shader=env(L"ARU_RETOPO_GPU_SHADER");if(library.empty()||shader.empty())return false;
  try{
   if(!module){module=LoadLibraryExW(library.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);if(!module)throw 0;
    create=reinterpret_cast<Create>(GetProcAddress(module,"aru_gpu_create"));destroy=reinterpret_cast<Destroy>(GetProcAddress(module,"aru_gpu_destroy"));setup=reinterpret_cast<Setup>(GetProcAddress(module,"aru_gpu_relax_setup"));relax=reinterpret_cast<Relax>(GetProcAddress(module,"aru_gpu_relax"));}
   if(!create||!destroy||!setup||!relax)throw 0;
   if(!surface){surface=create(vertices.data(),int(vertices.size()/3),triangles.data(),int(triangles.size()/3),shader.c_str());if(!surface)throw 0;++gpuBackendStats[2];}
   if(rows!=offsets||columns!=neighbors||weights!=anchors){int dummy=0;if(!setup(surface,int(points.size()/3),offsets.data(),neighbors.empty()?&dummy:neighbors.data(),anchors.data()))throw 0;rows=offsets;columns=neighbors;weights=anchors;}
   std::vector<double> result(points.size());auto nextSeeds=seeds;
   if(!relax(surface,points.data(),int(points.size()/3),result.data(),nextSeeds.data(),iterations,strength,guard))throw 0;
   for(double value:result)if(!std::isfinite(value))throw 0;
   points.swap(result);seeds.swap(nextSeeds);++gpuBackendStats[0];return true;
  }catch(...){reset();failed=true;++gpuBackendStats[1];return false;}
 }
};
