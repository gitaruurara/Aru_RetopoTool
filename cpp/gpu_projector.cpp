// Experimental independent D3D11 compute device; no Maya graphics state.
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <string>
#include <cstring>
#include "retopo.cpp"
using Microsoft::WRL::ComPtr;
struct GPUQuery{double p[4];int meta[4];};
struct GPUTriangle{double a[4],b[4],c[4],normal[4];int meta[4];};
struct GPUNode{double lo[4],hi[4];int meta[4];};
static_assert(sizeof(GPUQuery)==48 && sizeof(GPUTriangle)==144 && sizeof(GPUNode)==80,"GPU layout");
static thread_local std::string gpuError;
static void check(HRESULT status,const char* what){if(FAILED(status))throw std::runtime_error(std::string(what)+" HRESULT="+std::to_string(status));}
struct GPUProjector{
 ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;ComPtr<ID3D11ComputeShader> shader;
 ComPtr<ID3D11Buffer> triangleBuffer,nodeBuffer,orderBuffer,queryBuffer,resultBuffer,readback,params;
 ComPtr<ID3D11ShaderResourceView> triangleView,nodeView,orderView,queryView;
 ComPtr<ID3D11UnorderedAccessView> resultView;
 ComPtr<ID3D11Buffer> alternate,target,offsetBuffer,neighborBuffer,weightBuffer;
 ComPtr<ID3D11ShaderResourceView> resultRead,alternateRead,targetRead,offsetRead,neighborRead,weightRead;
 ComPtr<ID3D11UnorderedAccessView> alternateWrite;
 struct Cache {ComPtr<ID3D11Buffer> buffer;ComPtr<ID3D11UnorderedAccessView> view;bool valid=false;};
 std::vector<Cache> caches;int cacheCount=0,cacheGuard=-1;int cacheStage=-1;
 unsigned capacity=0,triangleCount=0,relaxCount=0;
 void prepareCaches(int n,int iterations,int guard){
  if(cacheCount!=n||cacheGuard!=guard||caches.size()!=size_t(iterations+1)){
   caches.clear();cacheCount=n;cacheGuard=guard;caches.resize(iterations+1);
   for(auto& c:caches){D3D11_BUFFER_DESC d{};d.ByteWidth=UINT(n)*sizeof(GPUQuery)*2;d.Usage=D3D11_USAGE_DEFAULT;d.BindFlags=D3D11_BIND_UNORDERED_ACCESS;d.MiscFlags=D3D11_RESOURCE_MISC_BUFFER_STRUCTURED;d.StructureByteStride=sizeof(GPUQuery)*2;check(device->CreateBuffer(&d,nullptr,&c.buffer),"cache buffer");check(device->CreateUnorderedAccessView(c.buffer.Get(),nullptr,&c.view),"cache UAV");}
  }
 }
 void bindCache(int stage){cacheStage=stage;ID3D11UnorderedAccessView*view=stage>=0?caches[stage].view.Get():nullptr;context->CSSetUnorderedAccessViews(1,1,&view,nullptr);}
 void unbindCache(){ID3D11UnorderedAccessView*empty=nullptr;context->CSSetUnorderedAccessViews(1,1,&empty,nullptr);cacheStage=-1;}
 void immutable(const void* data,UINT stride,UINT count,ComPtr<ID3D11Buffer>& buffer,ComPtr<ID3D11ShaderResourceView>& view){
  D3D11_BUFFER_DESC desc{};desc.ByteWidth=stride*count;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;desc.MiscFlags=D3D11_RESOURCE_MISC_BUFFER_STRUCTURED;desc.StructureByteStride=stride;
  D3D11_SUBRESOURCE_DATA initial{};initial.pSysMem=data;check(device->CreateBuffer(&desc,&initial,&buffer),"immutable buffer");check(device->CreateShaderResourceView(buffer.Get(),nullptr,&view),"immutable SRV");
 }
 void resize(unsigned n){
  if(n<=capacity)return;
  queryView.Reset();resultView.Reset();queryBuffer.Reset();resultBuffer.Reset();readback.Reset();
  D3D11_BUFFER_DESC d{};d.ByteWidth=n*sizeof(GPUQuery);d.Usage=D3D11_USAGE_DYNAMIC;d.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;d.BindFlags=D3D11_BIND_SHADER_RESOURCE;d.MiscFlags=D3D11_RESOURCE_MISC_BUFFER_STRUCTURED;d.StructureByteStride=sizeof(GPUQuery);
  check(device->CreateBuffer(&d,nullptr,&queryBuffer),"query buffer");check(device->CreateShaderResourceView(queryBuffer.Get(),nullptr,&queryView),"query SRV");
  d.Usage=D3D11_USAGE_DEFAULT;d.CPUAccessFlags=0;d.BindFlags=D3D11_BIND_UNORDERED_ACCESS|D3D11_BIND_SHADER_RESOURCE;check(device->CreateBuffer(&d,nullptr,&resultBuffer),"result buffer");check(device->CreateUnorderedAccessView(resultBuffer.Get(),nullptr,&resultView),"result UAV");
  d.Usage=D3D11_USAGE_STAGING;d.CPUAccessFlags=D3D11_CPU_ACCESS_READ;d.BindFlags=0;d.MiscFlags=0;d.StructureByteStride=0;check(device->CreateBuffer(&d,nullptr,&readback),"readback buffer");
  resultRead.Reset();alternateRead.Reset();targetRead.Reset();alternateWrite.Reset();alternate.Reset();target.Reset();
  check(device->CreateShaderResourceView(resultBuffer.Get(),nullptr,&resultRead),"result SRV");
  d.Usage=D3D11_USAGE_DEFAULT;d.CPUAccessFlags=0;d.BindFlags=D3D11_BIND_UNORDERED_ACCESS|D3D11_BIND_SHADER_RESOURCE;d.MiscFlags=D3D11_RESOURCE_MISC_BUFFER_STRUCTURED;d.StructureByteStride=sizeof(GPUQuery);
  check(device->CreateBuffer(&d,nullptr,&alternate),"alternate buffer");check(device->CreateShaderResourceView(alternate.Get(),nullptr,&alternateRead),"alternate SRV");check(device->CreateUnorderedAccessView(alternate.Get(),nullptr,&alternateWrite),"alternate UAV");
  d.BindFlags=D3D11_BIND_SHADER_RESOURCE;check(device->CreateBuffer(&d,nullptr,&target),"target buffer");check(device->CreateShaderResourceView(target.Get(),nullptr,&targetRead),"target SRV");capacity=n;
 }
};
API const char* aru_gpu_error(){return gpuError.c_str();}
API void* aru_gpu_create(const double* vertices,int nv,const int* indices,int nt,const wchar_t* shaderFile){
 try{
  gpuError.clear();std::unique_ptr<Surface> surface(static_cast<Surface*>(aru_surface_create(vertices,nv,indices,nt)));if(!surface)throw std::runtime_error("Invalid surface");
  auto p=std::make_unique<GPUProjector>();ComPtr<IDXGIFactory1> factory;check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
  ComPtr<IDXGIAdapter1> selected;SIZE_T memory=0;
  for(UINT i=0;;++i){ComPtr<IDXGIAdapter1> adapter;if(factory->EnumAdapters1(i,&adapter)==DXGI_ERROR_NOT_FOUND)break;DXGI_ADAPTER_DESC1 d{};adapter->GetDesc1(&d);if(!(d.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)&&(!selected||d.DedicatedVideoMemory>memory)){selected=adapter;memory=d.DedicatedVideoMemory;}}
  if(!selected)throw std::runtime_error("No hardware adapter");D3D_FEATURE_LEVEL level;
  check(D3D11CreateDevice(selected.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&p->device,&level,&p->context),"compute device");
  D3D11_FEATURE_DATA_DOUBLES doubles{};check(p->device->CheckFeatureSupport(D3D11_FEATURE_DOUBLES,&doubles,sizeof(doubles)),"double support");if(!doubles.DoublePrecisionFloatShaderOps)throw std::runtime_error("Double precision unavailable");
  ComPtr<ID3DBlob> code,errors;HRESULT compiled=D3DCompileFromFile(shaderFile,nullptr,D3D_COMPILE_STANDARD_FILE_INCLUDE,"main","cs_5_0",D3DCOMPILE_OPTIMIZATION_LEVEL3|D3DCOMPILE_IEEE_STRICTNESS,0,&code,&errors);
  if(FAILED(compiled))throw std::runtime_error(errors?std::string(static_cast<char*>(errors->GetBufferPointer()),errors->GetBufferSize()):"Shader compilation failed");
  check(p->device->CreateComputeShader(code->GetBufferPointer(),code->GetBufferSize(),nullptr,&p->shader),"compute shader");
  std::vector<GPUTriangle> triangles(nt);for(int i=0;i<nt;++i){auto&t=surface->tris[i];auto&out=triangles[i];write(out.a,t.a);write(out.b,t.b);write(out.c,t.c);write(out.normal,t.n);out.meta[0]=t.component;}
  std::vector<GPUNode> nodes(surface->nodes.size());for(size_t i=0;i<nodes.size();++i){auto&n=surface->nodes[i];auto&out=nodes[i];write(out.lo,n.box.lo);write(out.hi,n.box.hi);out.meta[0]=n.start;out.meta[1]=n.count;out.meta[2]=n.left;out.meta[3]=n.right;}
  p->immutable(triangles.data(),sizeof(GPUTriangle),nt,p->triangleBuffer,p->triangleView);p->immutable(nodes.data(),sizeof(GPUNode),UINT(nodes.size()),p->nodeBuffer,p->nodeView);p->immutable(surface->order.data(),sizeof(int),nt,p->orderBuffer,p->orderView);
  D3D11_BUFFER_DESC d{};d.ByteWidth=32;d.Usage=D3D11_USAGE_DEFAULT;d.BindFlags=D3D11_BIND_CONSTANT_BUFFER;check(p->device->CreateBuffer(&d,nullptr,&p->params),"parameters");p->triangleCount=nt;return p.release();
 }catch(const std::exception&e){gpuError=e.what();return nullptr;}
}
API void aru_gpu_destroy(void* handle){delete static_cast<GPUProjector*>(handle);}
static int gpuProject(void* handle,const double* input,int count,double* output,int* seeds,int guard,bool readback=true){
 try{
  auto*p=static_cast<GPUProjector*>(handle);if(!p||count<0||count>65535*64||(!input&&count)||(!output&&count)||(!seeds&&count))throw std::runtime_error("Invalid query");if(!count)return 1;
  p->resize(count);D3D11_MAPPED_SUBRESOURCE mapped{};check(p->context->Map(p->queryBuffer.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped),"upload map");
  auto*queries=static_cast<GPUQuery*>(mapped.pData);for(int i=0;i<count;++i){queries[i]={};for(int j=0;j<3;++j)queries[i].p[j]=input[3*i+j];queries[i].meta[0]=seeds[i];}p->context->Unmap(p->queryBuffer.Get(),0);
  struct {UINT count,triangles,guard,relaxing;double strength;UINT cacheEnabled,cacheValid;} constants{UINT(count),p->triangleCount,UINT(guard!=0),0,0,UINT(p->cacheStage>=0),UINT(p->cacheStage>=0&&p->caches[p->cacheStage].valid)};p->context->UpdateSubresource(p->params.Get(),0,nullptr,&constants,0,0);
  ID3D11ShaderResourceView* views[]={p->queryView.Get(),p->triangleView.Get(),p->nodeView.Get(),p->orderView.Get()};ID3D11UnorderedAccessView*uav=p->resultView.Get();ID3D11Buffer*cb=p->params.Get();
  p->context->CSSetShader(p->shader.Get(),nullptr,0);p->context->CSSetShaderResources(0,4,views);p->context->CSSetUnorderedAccessViews(0,1,&uav,nullptr);p->context->CSSetConstantBuffers(0,1,&cb);p->context->Dispatch((count+63)/64,1,1);
  ID3D11UnorderedAccessView*empty=nullptr;p->context->CSSetUnorderedAccessViews(0,1,&empty,nullptr);if(p->cacheStage>=0)p->caches[p->cacheStage].valid=true;p->unbindCache();if(!readback)return 1; p->context->CopyResource(p->readback.Get(),p->resultBuffer.Get());
  check(p->context->Map(p->readback.Get(),0,D3D11_MAP_READ,0,&mapped),"readback map");auto*result=static_cast<GPUQuery*>(mapped.pData);
  for(int i=0;i<count;++i){for(int j=0;j<3;++j)output[3*i+j]=result[i].p[j];seeds[i]=result[i].meta[0];}p->context->Unmap(p->readback.Get(),0);return 1;
 }catch(const std::exception&e){gpuError=e.what();return 0;}
}

API int aru_gpu_project(void* handle,const double* input,int count,double* output,int* seeds,int guard){return gpuProject(handle,input,count,output,seeds,guard);}
API int aru_gpu_relax_setup(void* handle,int count,const int* offsets,const int* neighbors,const double* weights){
 try{
  auto*p=static_cast<GPUProjector*>(handle);if(!p||count<=0||!offsets||!neighbors||!weights||offsets[0]!=0)throw std::runtime_error("Invalid relax topology");
  for(int j=0;j<count;++j)if(offsets[j+1]<offsets[j]||!std::isfinite(weights[j]))throw std::runtime_error("Invalid relax offsets/weights");
  for(int j=0;j<offsets[count];++j)if(neighbors[j]<0||neighbors[j]>=count)throw std::runtime_error("Invalid neighbor");
  p->relaxCount=0;p->caches.clear();
  p->offsetRead.Reset();p->neighborRead.Reset();p->weightRead.Reset();p->offsetBuffer.Reset();p->neighborBuffer.Reset();p->weightBuffer.Reset();
  p->immutable(offsets,sizeof(int),count+1,p->offsetBuffer,p->offsetRead);
  int dummy=0;p->immutable(offsets[count]?neighbors:&dummy,sizeof(int),std::max(1,offsets[count]),p->neighborBuffer,p->neighborRead);
  p->immutable(weights,sizeof(double),count,p->weightBuffer,p->weightRead);p->relaxCount=count;return 1;
 }catch(const std::exception&e){gpuError=e.what();return 0;}
}
API int aru_gpu_relax(void* handle,const double* input,int count,double* output,int* seeds,int iterations,double strength,int guard){
 try{
  auto*p=static_cast<GPUProjector*>(handle);if(!p||p->relaxCount!=unsigned(count)||iterations<0||!std::isfinite(strength))throw std::runtime_error("Invalid relax parameters");
  p->prepareCaches(count,iterations,guard);p->bindCache(0);
  if(!gpuProject(handle,input,count,output,seeds,guard,iterations==0)){p->unbindCache();return 0;}
  if(!iterations)return 1;
  p->context->CopyResource(p->target.Get(),p->resultBuffer.Get());
  struct {UINT count,triangles,guard,relaxing;double strength;UINT cacheEnabled,cacheValid;} constants{UINT(count),p->triangleCount,UINT(guard!=0),1,strength,1,0};
  p->context->UpdateSubresource(p->params.Get(),0,nullptr,&constants,0,0);
  ID3D11ShaderResourceView* emptyViews[8]={};ID3D11UnorderedAccessView*empty=nullptr;
  for(int step=0;step<iterations;++step){
   bool odd=step%2!=0;p->bindCache(step+1);constants.cacheValid=p->caches[step+1].valid;
   p->context->UpdateSubresource(p->params.Get(),0,nullptr,&constants,0,0);
   ID3D11ShaderResourceView* views[]={odd?p->alternateRead.Get():p->resultRead.Get(),p->triangleView.Get(),p->nodeView.Get(),p->orderView.Get(),p->targetRead.Get(),p->offsetRead.Get(),p->neighborRead.Get(),p->weightRead.Get()};
   ID3D11UnorderedAccessView*uav=odd?p->resultView.Get():p->alternateWrite.Get();
   p->context->CSSetShaderResources(0,8,views);p->context->CSSetUnorderedAccessViews(0,1,&uav,nullptr);p->context->Dispatch((count+63)/64,1,1);
   p->context->CSSetUnorderedAccessViews(0,1,&empty,nullptr);p->context->CSSetShaderResources(0,8,emptyViews);p->caches[step+1].valid=true;p->unbindCache();
  }
  p->context->CopyResource(p->readback.Get(),iterations%2?p->alternate.Get():p->resultBuffer.Get());
  D3D11_MAPPED_SUBRESOURCE mapped{};check(p->context->Map(p->readback.Get(),0,D3D11_MAP_READ,0,&mapped),"relax readback");auto*result=static_cast<GPUQuery*>(mapped.pData);
  for(int i=0;i<count;++i){for(int j=0;j<3;++j)output[3*i+j]=result[i].p[j];seeds[i]=result[i].meta[0];}p->context->Unmap(p->readback.Get(),0);return 1;
 }catch(const std::exception&e){gpuError=e.what();return 0;}
}
