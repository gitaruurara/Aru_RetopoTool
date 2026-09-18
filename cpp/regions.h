// Surface-oriented halfedge walks; output order matches spline traversal order.
#pragma once
namespace aru_regions_internal {
using Point=std::array<double,3>;
using Side=std::vector<int>;using Loop=std::vector<Side>;
struct Result {std::array<std::vector<int>,3> arrays;};
Point sub(Point a,Point b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
Point add(Point a,Point b){return {a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
Point mul(Point a,double b){return {a[0]*b,a[1]*b,a[2]*b};}
double dot(Point a,Point b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
Point cross(Point a,Point b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
Point unit(Point a){return mul(a,1./std::max(std::sqrt(dot(a,a)),1.e-15));}
API void* aru_regions_create(const double* points,int count,const int* splines,int splineCount,const double* normals){
 if(!points||!splines||!normals||count<0||count>2000000||splineCount<0||splineCount>2000000)return nullptr;
 for(int i=0;i<count*3;++i)if(!std::isfinite(points[i])||!std::isfinite(normals[i]))return nullptr;
 for(int i=0;i<splineCount*4;++i)if(splines[i]<0||splines[i]>=count)return nullptr;
 try {
  auto position=[&](int i)->Point{return {points[3*i],points[3*i+1],points[3*i+2]};};
  auto normal=[&](int i)->Point{return {normals[3*i],normals[3*i+1],normals[3*i+2]};};
  auto start=[&](int h){return splines[(h/2)*4+((h&1)?3:0)];};
  std::vector<std::vector<int>> incident(count);std::vector<int> next(splineCount*2,-1);
  for(int i=0;i<splineCount;++i){int a=splines[i*4],b=splines[i*4+3];if(a==b)return nullptr;incident[a].push_back(i*2);incident[b].push_back(i*2+1);}
  for(int ep=0;ep<count;++ep){auto& outgoing=incident[ep];if(outgoing.empty())continue;
   Point n=unit(normal(ep)),u=unit(cross(n,std::abs(n[0])<.8?Point{1,0,0}:Point{0,1,0})),v=cross(n,u);
   std::vector<std::pair<double,int>> ordered;ordered.reserve(outgoing.size());
   for(int h:outgoing){int base=(h/2)*4;Point tangent=sub(position(splines[base+((h&1)?2:1)]),position(ep));
    if(dot(tangent,tangent)<1.e-18)tangent=sub(position(start(h^1)),position(ep));
    ordered.emplace_back(std::atan2(dot(tangent,v),dot(tangent,u)),h);
   }
   std::stable_sort(ordered.begin(),ordered.end(),[](const auto& a,const auto& b){return a.first<b.first;});
   for(size_t i=0;i<ordered.size();++i)next[ordered[i].second^1]=ordered[(i+ordered.size()-1)%ordered.size()].second;
  }
  std::vector<unsigned char> visited(splineCount*2,0);std::vector<Loop> loops;
  for(int first=0;first<splineCount*2;++first){if(visited[first])continue;int h=first;std::vector<int> walk;
   while(!visited[h]){visited[h]=1;walk.push_back(h);h=next[h];}
   if(h!=first||walk.size()<3)continue;
   std::set<int> distinct;Point center{0,0,0},avg{0,0,0};
   for(int e:walk){int id=start(e);distinct.insert(id);center=add(center,position(id));avg=add(avg,normal(id));}
   if(distinct.size()!=walk.size())continue;
   center=mul(center,1./walk.size());avg=mul(avg,1./walk.size());Point area{0,0,0};
   for(size_t i=0;i<walk.size();++i)area=add(area,cross(sub(position(start(walk[i])),center),sub(position(start(walk[(i+1)%walk.size()])),center)));
   if(dot(area,avg)<=1.e-12)continue;
   std::vector<int> corners;for(size_t i=0;i<walk.size();++i)if(incident[start(walk[i])].size()!=2)corners.push_back(int(i));
   if(corners.size()<3){corners.resize(walk.size());std::iota(corners.begin(),corners.end(),0);}
   Loop loop;
   for(size_t i=0;i<corners.size();++i){int begin=corners[i],end=corners[(i+1)%corners.size()];if(end<=begin)end+=int(walk.size());Side side;
    for(int j=begin;j<end;++j)side.push_back(walk[j%walk.size()]);loop.push_back(std::move(side));
   }
   loops.push_back(std::move(loop));
  }
  std::vector<std::vector<int>> owners(splineCount);
  for(size_t i=0;i<loops.size();++i)for(const auto& side:loops[i])for(int h:side)owners[h/2].push_back(int(i));
  std::vector<unsigned char> remaining(loops.size(),1),excluded(loops.size(),0);
  auto bezier=[&](int si,double t){double u=1-t,w[]={u*u*u,3*u*u*t,3*u*t*t,t*t*t};Point result{0,0,0};
   for(int i=0;i<4;++i)result=add(result,mul(position(splines[si*4+i]),w[i]));return result;};
  for(size_t seed=0;seed<loops.size();++seed){if(!remaining[seed])continue;remaining[seed]=0;std::vector<int> component{int(seed)},pending{int(seed)};std::set<int> edges;
   while(!pending.empty()){int i=pending.back();pending.pop_back();
    for(const auto& side:loops[i])for(int h:side){int e=h/2;edges.insert(e);for(int neighbor:owners[e])if(remaining[neighbor]){remaining[neighbor]=0;component.push_back(neighbor);pending.push_back(neighbor);}}
   }
   if(component.size()<3)continue;bool closed=true;for(int e:edges)if(owners[e].size()!=2){closed=false;break;}if(!closed)continue;
   std::vector<std::pair<double,int>> ranked;
   for(int i:component){double total=0.;for(const auto& side:loops[i])for(int h:side){Point previous=bezier(h/2,0.);double length=0.;
     for(int k=1;k<=8;++k){Point current=bezier(h/2,k/8.),delta=sub(current,previous);length+=std::sqrt(dot(delta,delta));previous=current;}total+=length;
    }ranked.emplace_back(total,i);
   }
   std::sort(ranked.begin(),ranked.end());if(ranked.back().first>1.5*ranked[ranked.size()-2].first)excluded[ranked.back().second]=1;
  }
  auto result=std::make_unique<Result>();auto& a=result->arrays;a[0].push_back(0);a[1].push_back(0);
  for(size_t i=0;i<loops.size();++i)if(!excluded[i]){for(const auto& side:loops[i]){a[2].insert(a[2].end(),side.begin(),side.end());a[1].push_back(int(a[2].size()));}a[0].push_back(int(a[1].size())-1);}
  return result.release();
 }catch(...){return nullptr;}
}
API void aru_regions_destroy(void* p){delete static_cast<Result*>(p);}
API int aru_regions_size(void* p,int which){return p&&which>=0&&which<3?int(static_cast<Result*>(p)->arrays[which].size()):-1;}
API int aru_regions_copy(void* p,int which,int* dst,int size){if(!p||!dst||which<0||which>=3)return 0;const auto& v=static_cast<Result*>(p)->arrays[which];if(size!=int(v.size()))return 0;std::copy(v.begin(),v.end(),dst);return 1;}
}
