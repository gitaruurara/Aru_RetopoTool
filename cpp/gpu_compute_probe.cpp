// Standalone capability probe; never accesses Maya's graphics device.
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <iostream>
#include <cstring>
using Microsoft::WRL::ComPtr;
int main(){
 ComPtr<IDXGIFactory1> factory;if(FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))))return 1;
 for(UINT index=0;;++index){
  ComPtr<IDXGIAdapter1> adapter;if(factory->EnumAdapters1(index,&adapter)==DXGI_ERROR_NOT_FOUND)break;
  DXGI_ADAPTER_DESC1 desc{};adapter->GetDesc1(&desc);
  char name[256]{};WideCharToMultiByte(CP_UTF8,0,desc.Description,-1,name,sizeof(name),nullptr,nullptr);
  ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;D3D_FEATURE_LEVEL level;
  HRESULT status=D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,&level,&context);
  std::cout<<"adapter="<<name<<" vendor="<<desc.VendorId<<" memory="<<desc.DedicatedVideoMemory<<" device="<<std::hex<<status<<std::dec<<"\n";
  if(FAILED(status))continue;
  D3D11_FEATURE_DATA_DOUBLES doubles{};device->CheckFeatureSupport(D3D11_FEATURE_DOUBLES,&doubles,sizeof(doubles));
  std::cout<<"double_precision="<<doubles.DoublePrecisionFloatShaderOps<<"\n";
  const char* source=R"(
StructuredBuffer<double> input:register(t0);
RWStructuredBuffer<double> output:register(u0);
[numthreads(64,1,1)] void main(uint3 id:SV_DispatchThreadID){double a=input[id.x];output[id.x]=a/(a+1.0);}
)";
  ComPtr<ID3DBlob> code,errors;
  status=D3DCompile(source,std::strlen(source),nullptr,nullptr,nullptr,"main","cs_5_0",D3DCOMPILE_OPTIMIZATION_LEVEL3|D3DCOMPILE_IEEE_STRICTNESS,0,&code,&errors);
  std::cout<<"double_shader_compile="<<std::hex<<status<<std::dec<<"\n";
  if(errors)std::cout.write(static_cast<const char*>(errors->GetBufferPointer()),errors->GetBufferSize());
  if(SUCCEEDED(status)){ComPtr<ID3D11ComputeShader> shader;status=device->CreateComputeShader(code->GetBufferPointer(),code->GetBufferSize(),nullptr,&shader);std::cout<<"double_shader_create="<<std::hex<<status<<std::dec<<"\n";}
 }
 return 0;
}
