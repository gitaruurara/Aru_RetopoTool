// Compose directly from the owned topology; no Python sparse-row round trips.
#pragma once
namespace aru_subdivision_internal {
using CoefficientRow=aru_stencil_internal::Row;
inline void addCoefficient(CoefficientRow& row,int id,double value){
 auto at=std::find_if(row.begin(),row.end(),[id](const auto& item){return item.first==id;});
 if(at==row.end())row.emplace_back(id,0.0+value);else at->second+=value;
}
inline void addRow(CoefficientRow& dst,const CoefficientRow& src,double factor){
 for(const auto& value:src)addCoefficient(dst,value.first,value.second*factor);
}
API void* aru_subdivision_plan_compile(void* handle,const int* endpoints,int endpointCount,
 const int* splines,int splineCount,const int* sideOffsets,int sideCount,
 const int* sideSplines,const int* sideDirections,int segments){
 if(!handle||!endpoints||!splines||!sideOffsets||!sideSplines||!sideDirections||
    endpointCount<0||splineCount<0||splineCount>2000000||sideCount<0||segments<0)return nullptr;
 const auto& p=*static_cast<Plan*>(handle);
 if(endpointCount!=p.baseCount||sideCount!=int(p.guideEdges.size()/2)||sideOffsets[0]!=0||sideOffsets[sideCount]!=segments)return nullptr;
 for(int i=0;i<endpointCount;++i)if(endpoints[i]<0)return nullptr;
 for(int i=0;i<splineCount*4;++i)if(splines[i]<0)return nullptr;
 for(int i=0;i<sideCount;++i)if(sideOffsets[i]<0||sideOffsets[i+1]<=sideOffsets[i]||sideOffsets[i+1]>segments)return nullptr;
 for(int i=0;i<segments;++i)if(sideSplines[i]<0||sideSplines[i]>=splineCount||(sideDirections[i]!=1&&sideDirections[i]!=-1))return nullptr;
 try {
  const int count=int(p.ints[1].size())-1;
  std::vector<int> guideSource(count,-2);std::vector<double> guideParameter(count,0.);
  for(int i=0;i<endpointCount;++i)guideSource[i]=-1;
  for(size_t i=0;i<p.ints[3].size();++i){guideSource[p.ints[3][i]]=p.ints[4][i];guideParameter[p.ints[3][i]]=p.doubles[0][i];}
  std::vector<unsigned char> needed(count,1);
  for(int id:p.ints[6])if(guideSource[id]==-2)needed[id]=0;
  std::vector<std::vector<unsigned char>> requests(p.steps.size());
  for(int level=int(p.steps.size())-1;level>=0;--level){
   const auto& s=p.steps[level]->ints;requests[level]=std::move(needed);
   int previousCount=level?int(p.steps[level-1]->ints[1].size())-1:endpointCount;
   needed.assign(previousCount,0);
   for(int i=0;i<int(requests[level].size());++i)if(requests[level][i]&&guideSource[i]==-2)
    for(int j=s[1][i];j<s[1][i+1];++j)needed[s[2][j]]=1;
  }
  auto sample=[&](int source,double t,bool reversed){
   int begin=sideOffsets[source],n=sideOffsets[source+1]-begin;
   double x=std::min(std::max(t,0.),1.)*n;int k=std::min(int(x),n-1);
   int index=begin+(reversed?n-1-k:k),direction=sideDirections[index]*(reversed?-1:1);
   double local=direction==1?x-k:1-(x-k),u=1-local;
   double weights[]={u*u*u,3*u*u*local,3*u*local*local,local*local*local};
   const int* controls=splines+sideSplines[index]*4;CoefficientRow row;row.reserve(4);
   for(int j=0;j<4;++j)addCoefficient(row,controls[j],weights[j]);return row;
  };
  aru_stencil_internal::State state;state.rows.resize(endpointCount);
  for(int i=0;i<endpointCount;++i)state.rows[i].emplace_back(endpoints[i],1.);
  for(size_t level=0;level<p.steps.size();++level){
   const auto& stage=*p.steps[level];const auto& s=stage.ints;
   std::vector<CoefficientRow> next(requests[level].size());
   for(int i=0;i<int(next.size());++i)if(requests[level][i]){
    if(guideSource[i]==-1)next[i].emplace_back(endpoints[i],1.);
    else if(guideSource[i]>=0)next[i]=sample(guideSource[i],guideParameter[i],false);
    else {auto& row=next[i];row.reserve(32);
     for(int j=s[1][i];j<s[1][i+1];++j)addRow(row,state.rows[s[2][j]],stage.weights[j]);
    }
   }
   state.rows.swap(next);
  }
  std::map<Edge,int> guideIds;
  for(int i=0;i<sideCount;++i)guideIds[{p.guideEdges[2*i],p.guideEdges[2*i+1]}]=i;
  for(size_t patch=0;patch<p.ints[7].size();++patch){
   int face=p.ints[7][patch],begin=p.baseOffsets[face];
   int sources[4];bool reversed[4];CoefficientRow corners[4];
   for(int side=0;side<4;++side){
    int a=p.baseVertices[begin+side],b=p.baseVertices[begin+(side+1)%4];
    auto found=guideIds.find(edge(a,b));if(found==guideIds.end())return nullptr;
    sources[side]=found->second;reversed[side]=a>b;
    corners[side]=sample(sources[side],0.,reversed[side]);
   }
   std::map<std::pair<int,double>,CoefficientRow> samples;
   auto boundary=[&](int side,double t)->const CoefficientRow&{
    auto key=std::make_pair(side,t);auto found=samples.find(key);
    if(found!=samples.end())return found->second;
    return samples.emplace(key,sample(sources[side],t,reversed[side])).first->second;
   };
   for(int j=p.ints[5][patch];j<p.ints[5][patch+1];++j){
    int vertex=p.ints[6][j];if(guideSource[vertex]!=-2)continue;
    double u=p.doubles[1][j],v=p.doubles[2][j];auto& row=state.rows[vertex];row.clear();row.reserve(16);
    addRow(row,boundary(0,u),1-v);addRow(row,boundary(2,1-u),v);
    addRow(row,boundary(3,1-v),1-u);addRow(row,boundary(1,v),u);
    double factors[]={(1-u)*(1-v),u*(1-v),u*v,(1-u)*v};
    for(int corner=0;corner<4;++corner)addRow(row,corners[corner],-factors[corner]);
   }
  }
  for(const auto& row:state.rows)for(const auto& value:row)if(!std::isfinite(value.second))return nullptr;
  return aru_stencil_internal::aru_stencil_compiler_pack(&state);
 }catch(...){return nullptr;}
}
}
