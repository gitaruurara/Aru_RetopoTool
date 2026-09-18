// One Catmull-Clark topology step. Every returned array is owned by its handle.
#pragma once
#include <map>
#include <set>
#include <array>
namespace aru_subdivision_internal {
using Edge=std::pair<int,int>;
struct Step {std::array<std::vector<int>,8> ints;std::vector<double> weights;};
inline Edge edge(int a,int b){return {std::min(a,b),std::max(a,b)};}
API void* aru_subdivision_create(int count,const int* offsets,int faceCount,const int* vertices,int entries){
 if(count<0||count>2000000||faceCount<0||faceCount>2000000||entries<0||!offsets||(!vertices&&entries)||offsets[0]!=0||offsets[faceCount]!=entries)return nullptr;
 for(int f=0;f<faceCount;++f)if(offsets[f]<0||offsets[f+1]>entries||offsets[f+1]-offsets[f]<3)return nullptr;
 for(int j=0;j<entries;++j)if(vertices[j]<0||vertices[j]>=count)return nullptr;
 try {
  auto result=std::make_unique<Step>();auto& out=result->ints;
  std::map<Edge,std::vector<int>> edgeFaces;
  std::vector<std::vector<int>> vf(count),ve(count);
  for(int f=0;f<faceCount;++f){int begin=offsets[f],end=offsets[f+1];
   for(int j=begin;j<end;++j){int a=vertices[j],b=vertices[j+1==end?begin:j+1];if(a==b)return nullptr;
    vf[a].push_back(f);edgeFaces[edge(a,b)].push_back(f);
   }
  }
  std::vector<Edge> edges;std::map<Edge,int> ids;
  for(const auto& entry:edgeFaces){if(entry.second.size()>2)return nullptr;int id=int(edges.size());edges.push_back(entry.first);ids[entry.first]=count+id;
   ve[entry.first.first].push_back(id);ve[entry.first.second].push_back(id);
   out[0].push_back(entry.first.first);out[0].push_back(entry.first.second);
  }
  int faceBase=count+int(edges.size());out[1].push_back(0);
  auto emit=[&](const std::map<int,double>& row){for(auto value:row){out[2].push_back(value.first);result->weights.push_back(value.second);}out[1].push_back(int(out[2].size()));};
  auto addFace=[&](std::map<int,double>& row,int f,double factor){double w=1./(offsets[f+1]-offsets[f]);for(int j=offsets[f];j<offsets[f+1];++j)row[vertices[j]]+=w*factor;};
  for(int v=0;v<count;++v){std::map<int,double> row;std::vector<int> boundary;
   for(int ei:ve[v])if(edgeFaces[edges[ei]].size()==1)boundary.push_back(ei);
   if(!boundary.empty()){row[v]=.75;for(int ei:boundary){const auto& e=edges[ei];row[e.first==v?e.second:e.first]+=.25/boundary.size();}}
   else {double n=double(vf[v].size());if(!n)return nullptr;row[v]=(n-3)/n;
    for(int f:vf[v])addFace(row,f,1/(n*n));
    for(int ei:ve[v]){const auto& e=edges[ei];row[e.first]+=1/(n*n);row[e.second]+=1/(n*n);}
   }
   emit(row);
  }
  for(const auto& e:edges){const auto& fs=edgeFaces[e];std::map<int,double> row;
   if(fs.size()==1){row[e.first]=.5;row[e.second]=.5;}
   else {row[e.first]=.25;row[e.second]=.25;for(int f:fs)addFace(row,f,.25);}
   emit(row);
  }
  for(int f=0;f<faceCount;++f){std::map<int,double> row;addFace(row,f,1.);emit(row);
   int begin=offsets[f],end=offsets[f+1];
   for(int j=begin;j<end;++j){int a=vertices[j],b=vertices[j+1==end?begin:j+1],c=vertices[j==begin?end-1:j-1];
    out[3].insert(out[3].end(),{a,ids[edge(a,b)],faceBase+f,ids[edge(c,a)]});
   }
  }
  for(int k=0;k<2;++k){auto& off=out[4+k*2];auto& values=out[5+k*2];off.push_back(0);
   const auto& source=k?ve:vf;
   for(const auto& row:source){values.insert(values.end(),row.begin(),row.end());off.push_back(int(values.size()));}
  }
  return result.release();
 }catch(...){return nullptr;}
}
API void aru_subdivision_destroy(void* p){delete static_cast<Step*>(p);}
API int aru_subdivision_size(void* p,int which){if(!p||which<0||which>8)return -1;auto& s=*static_cast<Step*>(p);return int(which==8?s.weights.size():s.ints[which].size());}
API int aru_subdivision_copy_int(void* p,int which,int* dst,int size){if(!p||!dst||which<0||which>=8)return 0;const auto& v=static_cast<Step*>(p)->ints[which];if(size!=int(v.size()))return 0;std::copy(v.begin(),v.end(),dst);return 1;}
API int aru_subdivision_copy_weights(void* p,double* dst,int size){if(!p||!dst)return 0;const auto& v=static_cast<Step*>(p)->weights;if(size!=int(v.size()))return 0;std::copy(v.begin(),v.end(),dst);return 1;}
}
namespace aru_subdivision_internal {
struct Plan {
 std::vector<std::unique_ptr<Step>> steps;
 std::array<std::vector<int>,8> ints;
 std::array<std::vector<double>,3> doubles;
};
struct Guide {int source;double a,b;};
using UV=std::pair<double,double>;
API void* aru_subdivision_plan_create(int count,const int* offsets,int faceCount,const int* vertices,int entries,const int* guideEdges,int guideCount,int levels){
 if((!guideEdges&&guideCount)||guideCount<0||levels<1||levels>6)return nullptr;
 try {
  auto p=std::make_unique<Plan>();
  // Validate all topology before indexing the initial faces or guide endpoints.
  std::unique_ptr<Step> first(static_cast<Step*>(aru_subdivision_create(count,offsets,faceCount,vertices,entries)));
  if(!first)return nullptr;
  std::vector<int> off(offsets,offsets+faceCount+1),verts;
  if(entries)verts.assign(vertices,vertices+entries);
  std::vector<std::map<int,UV>> patches;
  for(int f=0;f<faceCount;++f)if(off[f+1]-off[f]==4){std::map<int,UV> uv;UV corners[]={{0,0},{1,0},{1,1},{0,1}};
   for(int j=0;j<4;++j)uv[verts[off[f]+j]]=corners[j];patches.push_back(std::move(uv));p->ints[7].push_back(f);
  }
  std::map<Edge,Guide> guides;
  for(int i=0;i<guideCount;++i){int a=guideEdges[2*i],b=guideEdges[2*i+1];if(a<0||b<=a||b>=count)return nullptr;guides[{a,b}]={i,0.,1.};}
  for(int level=0;level<levels;++level){
   auto step=level==0?std::move(first):std::unique_ptr<Step>(static_cast<Step*>(aru_subdivision_create(count,off.data(),int(off.size())-1,verts.data(),int(verts.size()))));
   if(!step)return nullptr;auto& s=step->ints;int edgeCount=int(s[0].size()/2),faceBase=count+edgeCount;
   std::map<Edge,int> edgeIds;for(int i=0;i<edgeCount;++i)edgeIds[{s[0][2*i],s[0][2*i+1]}]=count+i;
   for(auto& uv:patches){std::set<int> localEdges,localFaces;
    for(const auto& v:uv){int id=v.first;for(int j=s[6][id];j<s[6][id+1];++j)localEdges.insert(s[7][j]);for(int j=s[4][id];j<s[4][id+1];++j)localFaces.insert(s[5][j]);}
    std::map<int,UV> additions;
    for(int ei:localEdges){auto a=uv.find(s[0][ei*2]),b=uv.find(s[0][ei*2+1]);if(a!=uv.end()&&b!=uv.end())additions[count+ei]={(a->second.first+b->second.first)*.5,(a->second.second+b->second.second)*.5};}
    for(int f:localFaces){double u=0,v=0;bool inside=true;for(int j=off[f];j<off[f+1];++j){auto at=uv.find(verts[j]);if(at==uv.end()){inside=false;break;}u+=at->second.first;v+=at->second.second;}
     if(inside){double n=off[f+1]-off[f];additions[faceBase+f]={u/n,v/n};}
    }
    uv.insert(additions.begin(),additions.end());
   }
   std::map<Edge,Guide> next;
   for(const auto& entry:guides){auto at=edgeIds.find(entry.first);if(at==edgeIds.end())return nullptr;int a=entry.first.first,b=entry.first.second,mid=at->second;const auto& g=entry.second;double t=(g.a+g.b)*.5;
    p->ints[3].push_back(mid);p->ints[4].push_back(g.source);p->doubles[0].push_back(t);
    next[edge(a,mid)]={g.source,g.a,t};
    next[edge(mid,b)]=mid<b?Guide{g.source,t,g.b}:Guide{g.source,g.b,t};
   }
   guides.swap(next);count=int(s[1].size())-1;verts=s[3];off.resize(verts.size()/4+1);for(size_t i=0;i<off.size();++i)off[i]=int(i*4);
   p->steps.push_back(std::move(step));
  }
  p->ints[0]=std::move(verts);std::vector<std::set<int>> adj(count);
  for(size_t i=0;i<p->ints[0].size();i+=4)for(int j=0;j<4;++j){int a=p->ints[0][i+j],b=p->ints[0][i+(j+1)%4];adj[a].insert(b);adj[b].insert(a);}
  p->ints[1].push_back(0);for(const auto& row:adj){p->ints[2].insert(p->ints[2].end(),row.begin(),row.end());p->ints[1].push_back(int(p->ints[2].size()));}
  p->ints[5].push_back(0);for(const auto& uv:patches){for(const auto& item:uv){p->ints[6].push_back(item.first);p->doubles[1].push_back(item.second.first);p->doubles[2].push_back(item.second.second);}p->ints[5].push_back(int(p->ints[6].size()));}
  return p.release();
 }catch(...){return nullptr;}
}
API void aru_subdivision_plan_destroy(void* p){delete static_cast<Plan*>(p);}
API void* aru_subdivision_plan_step(void* p,int level){if(!p||level<0||level>=int(static_cast<Plan*>(p)->steps.size()))return nullptr;return static_cast<Plan*>(p)->steps[level].get();}
API int aru_subdivision_plan_size(void* p,int which){if(!p||which<0||which>10)return -1;const auto& s=*static_cast<Plan*>(p);return int(which<8?s.ints[which].size():s.doubles[which-8].size());}
API int aru_subdivision_plan_copy_int(void* p,int which,int* dst,int size){if(!p||!dst||which<0||which>=8)return 0;const auto& v=static_cast<Plan*>(p)->ints[which];if(size!=int(v.size()))return 0;std::copy(v.begin(),v.end(),dst);return 1;}
API int aru_subdivision_plan_copy_double(void* p,int which,double* dst,int size){if(!p||!dst||which<0||which>=3)return 0;const auto& v=static_cast<Plan*>(p)->doubles[which];if(size!=int(v.size()))return 0;std::copy(v.begin(),v.end(),dst);return 1;}
}
