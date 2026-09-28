#include <vector>
#include <utility>
#include <algorithm>
#include <cmath>
struct Result { std::vector<int> offsets{0}, ids; std::vector<double> weights; };
extern "C" __declspec(dllexport) void aru_compose_destroy(void* handle) { delete static_cast<Result*>(handle); }
extern "C" __declspec(dllexport) void* aru_compose_rows(const int* po,int pn,const int* pi,const double* pw,int pe,
 const int* so,int sn,const int* si,const double* sw,int se,const int* requests,int count) {
 if(!po||!so||pn<0||sn<0||pe<0||se<0||count<0||pn>2000000||sn>2000000||count>sn||!pi||!pw||!si||!sw||!requests) return nullptr;
 if(po[0]!=0||so[0]!=0||po[pn]!=pe||so[sn]!=se)return nullptr;
 for(int i=0;i<pn;++i)if(po[i]<0||po[i+1]<po[i]||po[i+1]>pe)return nullptr;
 for(int i=0;i<sn;++i)if(so[i]<0||so[i+1]<so[i]||so[i+1]>se)return nullptr;
 for(int i=0;i<pe;++i)if(pi[i]<0||!std::isfinite(pw[i]))return nullptr;
 for(int i=0;i<se;++i)if(si[i]<0||si[i]>=pn||!std::isfinite(sw[i]))return nullptr;
 for(int i=0;i<count;++i)if(requests[i]<0||requests[i]>=sn)return nullptr;
 Result* out=nullptr;
 try {
  out=new Result();out->offsets.reserve(count+1);
  for(int q=0;q<count;++q){
   std::vector<std::pair<int,double>> row;row.reserve(32);
   const int r=requests[q];
   for(int j=so[r];j<so[r+1];++j){
    const int p=si[j];const double factor=sw[j];
    for(int k=po[p];k<po[p+1];++k){
     const int id=pi[k];auto found=std::find_if(row.begin(),row.end(),[id](const auto& v){return v.first==id;});
     const double product=pw[k]*factor;
     if(found==row.end())row.emplace_back(id,0.0+product);else found->second=found->second+product;
    }
   }
   for(const auto& v:row){out->ids.push_back(v.first);out->weights.push_back(v.second);}
   out->offsets.push_back(static_cast<int>(out->ids.size()));
  }
  return out;
 } catch(...) {delete out;return nullptr;}
}
extern "C" __declspec(dllexport) int aru_compose_size(void* h){return h?static_cast<int>(static_cast<Result*>(h)->ids.size()):-1;}
extern "C" __declspec(dllexport) int aru_compose_copy(void* h,int* offsets,int* ids,double* weights){
 if(!h||!offsets||!ids||!weights)return 0;auto& r=*static_cast<Result*>(h);
 std::copy(r.offsets.begin(),r.offsets.end(),offsets);std::copy(r.ids.begin(),r.ids.end(),ids);std::copy(r.weights.begin(),r.weights.end(),weights);return 1;
}
