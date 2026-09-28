// Pure numeric endpoint ancestry. Ordered candidates preserve first-match semantics.
#include <array>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <cmath>
#include <cstdint>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
namespace {
using Cell=std::array<double,3>;
struct Hash {
 size_t operator()(const Cell& c) const {
  size_t h=0;for(double v:c)h^=std::hash<double>{}(v)+0x9e3779b9+(h<<6)+(h>>2);return h;
 }
};
Cell cell(const double* p){return {std::floor(p[0]/1e-6),std::floor(p[1]/1e-6),std::floor(p[2]/1e-6)};}
bool close(const double* a,const double* b){
 double x=a[0]-b[0],y=a[1]-b[1],z=a[2]-b[2];return x*x+y*y+z*z<1e-12;
}
}
API int aru_match_spline_endpoints(const double* oldPoints,int oldCount,const int* oldSplines,int oldSize,
 const double* newPoints,int newCount,const int* newSplines,int newSize,int* result){
 if(oldCount<0||newCount<0||oldSize<0||newSize<0)return 0;
 if((oldCount&&!oldPoints)||(newCount&&!newPoints)||(oldSize&&!oldSplines)||(newSize&&(!newSplines||!result)))return 0;
 for(int i=0;i<oldCount*3;++i)if(!std::isfinite(oldPoints[i]))return 0;
 for(int i=0;i<newCount*3;++i)if(!std::isfinite(newPoints[i]))return 0;
 for(int i=0;i<oldSize*4;++i)if(oldSplines[i]<0||oldSplines[i]>=oldCount)return 0;
 for(int i=0;i<newSize*4;++i)if(newSplines[i]<0||newSplines[i]>=newCount)return 0;
 try{
  std::unordered_map<Cell,std::vector<int>,Hash> buckets;
  for(int j=0;j<oldSize;++j){
   buckets[cell(oldPoints+3*oldSplines[4*j])].push_back(j);
   buckets[cell(oldPoints+3*oldSplines[4*j+3])].push_back(j);
  }
  std::unordered_map<Cell,std::vector<int>,Hash> candidates;
  for(int i=0;i<newSize;++i){
   result[2*i]=-1;result[2*i+1]=1;
   auto p=newPoints+3*newSplines[4*i];auto q=newPoints+3*newSplines[4*i+3];Cell base=cell(p);
   auto cache=candidates.find(base);
   if(cache==candidates.end()){
    std::vector<int> list;
    for(int x=-1;x<=1;++x)for(int y=-1;y<=1;++y)for(int z=-1;z<=1;++z){
     auto found=buckets.find({base[0]+x,base[1]+y,base[2]+z});
     if(found!=buckets.end())list.insert(list.end(),found->second.begin(),found->second.end());
    }
    std::sort(list.begin(),list.end());list.erase(std::unique(list.begin(),list.end()),list.end());
    cache=candidates.emplace(base,std::move(list)).first;
   }
   for(int j:cache->second){
    auto a=oldPoints+3*oldSplines[4*j];auto b=oldPoints+3*oldSplines[4*j+3];
    if(close(a,p)&&close(b,q)){result[2*i]=j;break;}
    if(close(a,q)&&close(b,p)){result[2*i]=j;result[2*i+1]=-1;break;}
   }
  }
  return 1;
 }catch(...){return 0;}
}
