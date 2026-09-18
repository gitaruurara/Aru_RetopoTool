// Sparse coefficient composition; handles own all intermediate storage.
#pragma once
#include <vector>
#include <utility>
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
namespace aru_stencil_internal {
struct Result {std::vector<int> offsets{0},ids;std::vector<double> weights;};
using Row=std::vector<std::pair<int,double>>;
struct State {std::vector<Row> rows;};
API void* aru_stencil_compiler_create(const int* endpoints,int count){
 if(count<0||count>2000000||!endpoints)return nullptr;
 try {auto s=std::make_unique<State>();s->rows.resize(count);for(int i=0;i<count;++i){if(endpoints[i]<0)return nullptr;s->rows[i].emplace_back(endpoints[i],1.);}return s.release();}catch(...){return nullptr;}
}
API void aru_stencil_compiler_destroy(void* h){delete static_cast<State*>(h);}
API int aru_stencil_compiler_step(void* h,const int* offsets,int count,const int* ids,const double* weights,int entries,const int* requests,int requested){
 if(!h||!offsets||!ids||!weights||!requests||count<0||count>2000000||entries<0||requested<0||requested>count)return 0;
 if(offsets[0]!=0||offsets[count]!=entries)return 0;
 auto& s=*static_cast<State*>(h);
 for(int i=0;i<count;++i)if(offsets[i]<0||offsets[i+1]<offsets[i]||offsets[i+1]>entries)return 0;
 for(int i=0;i<entries;++i)if(ids[i]<0||static_cast<size_t>(ids[i])>=s.rows.size()||!std::isfinite(weights[i]))return 0;
 for(int i=0;i<requested;++i)if(requests[i]<0||requests[i]>=count||(i&&requests[i]<=requests[i-1]))return 0;
 try{
  std::vector<Row> result(count);
  for(int r=0;r<requested;++r){auto& row=result[requests[r]];row.reserve(32);
   for(int j=offsets[requests[r]];j<offsets[requests[r]+1];++j){
    for(const auto& value:s.rows[ids[j]]){
     auto found=std::find_if(row.begin(),row.end(),[&value](const auto& v){return v.first==value.first;});
     const double product=value.second*weights[j];
     if(!std::isfinite(product))return 0;
     if(found==row.end())row.emplace_back(value.first,0.0+product);else {const double sum=found->second+product;if(!std::isfinite(sum))return 0;found->second=sum;}
    }
   }
  }
  s.rows.swap(result);return 1;
 }catch(...){return 0;}
}
API int aru_stencil_compiler_set(void* h,const int* rows,int count,const int* offsets,const int* ids,const double* weights,int entries){
 if(!h||!rows||!offsets||!ids||!weights||count<0||count>2000000||entries<0)return 0;
 if(offsets[0]!=0||offsets[count]!=entries)return 0;
 auto& s=*static_cast<State*>(h);
 for(int i=0;i<count;++i)if(rows[i]<0||static_cast<size_t>(rows[i])>=s.rows.size()||offsets[i]<0||offsets[i+1]<offsets[i]||offsets[i+1]>entries)return 0;
 for(int i=0;i<entries;++i)if(ids[i]<0||!std::isfinite(weights[i]))return 0;
 try{
  std::vector<Row> values(count);
  for(int i=0;i<count;++i)for(int j=offsets[i];j<offsets[i+1];++j)values[i].emplace_back(ids[j],weights[j]);
  for(int i=0;i<count;++i)s.rows[rows[i]].swap(values[i]);return 1;
 }catch(...){return 0;}
}
API void* aru_stencil_compiler_pack(void* h){
 if(!h)return nullptr;
 try {auto result=std::make_unique<Result>();const auto& s=*static_cast<State*>(h);result->offsets.reserve(s.rows.size()+1);
  for(auto row:s.rows){std::sort(row.begin(),row.end(),[](const auto& a,const auto& b){return a.first<b.first;});
   for(const auto& v:row)if(std::abs(v.second)>1.e-16){if(result->ids.size()>=static_cast<size_t>(std::numeric_limits<int>::max()))return nullptr;result->ids.push_back(v.first);result->weights.push_back(v.second);}
   result->offsets.push_back(static_cast<int>(result->ids.size()));
  }return result.release();
 }catch(...){return nullptr;}
}

API void aru_stencil_result_destroy(void* h){delete static_cast<Result*>(h);}
API int aru_stencil_result_size(void* h){return h?static_cast<int>(static_cast<Result*>(h)->ids.size()):-1;}
API int aru_stencil_result_copy(void* h,int* offsets,int offsetCount,int* ids,double* weights,int entryCount){
 if(!h||!offsets||!ids||!weights)return 0;const auto& r=*static_cast<Result*>(h);
 if(offsetCount!=static_cast<int>(r.offsets.size())||entryCount!=static_cast<int>(r.ids.size()))return 0;
 std::copy(r.offsets.begin(),r.offsets.end(),offsets);std::copy(r.ids.begin(),r.ids.end(),ids);std::copy(r.weights.begin(),r.weights.end(),weights);return 1;
}
} // namespace aru_stencil_internal
