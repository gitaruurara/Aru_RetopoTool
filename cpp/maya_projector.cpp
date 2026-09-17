// Bulk Maya intersector queries, same object-space metric as curve_net_edit.
#include <maya/MMeshIntersector.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MObjectHandle.h>
#include <maya/MMatrix.h>
#include <maya/MPoint.h>
#include <cmath>
#include <maya/MString.h>
#include <maya/MStatus.h>
#include <maya/MFnMesh.h>
#include <maya/MPointArray.h>
#include <maya/MIntArray.h>
#include <vector>
#include <algorithm>
#include <future>
#include <thread>
#ifdef ARU_PROJECTOR_SLEEPING_TEAM
#include "sleeping_projection_team.h"
#endif
#define API extern "C" __declspec(dllexport)
struct Projector {
#ifdef ARU_PROJECTOR_SLEEPING_TEAM
    std::unique_ptr<AruProjectionTeam> team;
    template<class F> int parallel(int n,F fn,int chunk){
        if(!team)team=std::make_unique<AruProjectionTeam>(std::min(4,static_cast<int>(std::max(1u,std::thread::hardware_concurrency()))));
        std::atomic<int> failed{0};
        team->run(n,[&](int i){if(!fn(i))failed.store(1,std::memory_order_relaxed);},chunk);
        return failed.load();
    }
#endif
    MMeshIntersector intersector;
    MMatrix matrix,inverse;
#ifdef ARU_PROJECTOR_IDENTITY
    bool identity=false;
#endif
    MObjectHandle owner;
    MPointArray worldPoints;MIntArray counts,indices;std::vector<unsigned> offsets;
};
API void* aru_maya_projector_create(const char* path) {
    Projector* p=nullptr;
    try {
        MSelectionList selection; MDagPath dag;
        if(!selection.add(MString(path)) || !selection.getDagPath(0,dag)) return nullptr;
        if(dag.hasFn(MFn::kTransform) && !dag.extendToShape()) return nullptr;
        if(!dag.hasFn(MFn::kMesh)) return nullptr;
        p=new Projector;
        p->matrix=dag.inclusiveMatrix();p->inverse=dag.inclusiveMatrixInverse();p->owner=MObjectHandle(dag.node());
#ifdef ARU_PROJECTOR_IDENTITY
        p->identity=(p->matrix==MMatrix::identity);
#endif
        MObject mesh=dag.node();
        if(!p->intersector.create(mesh)) {delete p;return nullptr;}
        MFnMesh meshFn(dag);meshFn.getPoints(p->worldPoints,MSpace::kWorld);meshFn.getVertices(p->counts,p->indices);
        p->offsets.push_back(0);for(unsigned i=0;i<p->counts.length();++i)p->offsets.push_back(p->offsets.back()+p->counts[i]);
        return p;
    } catch(...) {delete p;return nullptr;}
}
API void aru_maya_projector_destroy(void* handle) {delete static_cast<Projector*>(handle);}
API int aru_maya_projector_points(void* handle,const double* input,int count,double* output) {
    try {
        auto* p=static_cast<Projector*>(handle);
        if(!p || !p->owner.isAlive() || !p->owner.isValid() || count<0 || (!input && count) || (!output && count)) return 0;
        auto projectPoint=[&](int i)->int {
          try {
            const double* v=input+3*i;
            if(!std::isfinite(v[0]) || !std::isfinite(v[1]) || !std::isfinite(v[2])) return 0;
            MPoint query=MPoint(v[0],v[1],v[2])*p->inverse;
            MPointOnMesh hit;
            if(!p->intersector.getClosestPoint(query,hit)) return 0;
            auto q=hit.getPoint();MPoint world=MPoint(q.x,q.y,q.z)*p->matrix;
            output[3*i]=world.x;output[3*i+1]=world.y;output[3*i+2]=world.z;
            return 1;
          }catch(...){return 0;}
        };
        int failed=0;
        if(count<512){
            for(int i=0;i<count;++i)failed|=!projectPoint(i);
        }else{
#ifdef ARU_PROJECTOR_SLEEPING_TEAM
            failed=p->parallel(count,projectPoint,128);
#else
            const int threads=std::min(4,static_cast<int>(std::max(1u,std::thread::hardware_concurrency())));
            std::vector<std::future<int>> tasks;
            for(int worker=0;worker<threads;++worker){
                tasks.push_back(std::async(std::launch::async,[&,worker]{
                    int errors=0;
                    for(int i=worker;i<count;i+=threads)errors|=!projectPoint(i);
                    return errors;
                }));
            }
            for(auto& task:tasks)failed|=task.get();
#endif
        }
        return !failed;
    } catch(...) {return 0;}
}

#include <maya/MVector.h>
#include "path_fit.cpp"
static bool projected(Projector* p,V input,V& output,bool normal=false){
 MPoint query(input.x,input.y,input.z);
#ifdef ARU_PROJECTOR_IDENTITY
 if(!p->identity)
#endif
 query=query*p->inverse;
 MPointOnMesh hit;
 if(!p->intersector.getClosestPoint(query,hit))return false;
 if(normal){auto v=hit.getNormal();MVector n(v.x,v.y,v.z);
#ifdef ARU_PROJECTOR_IDENTITY
 if(!p->identity)
#endif
 n=n.transformAsNormal(p->matrix);if(n.length()>1e-12)n.normalize();output={n.x,n.y,n.z};}
 else{auto v=hit.getPoint();MPoint q(v.x,v.y,v.z);
#ifdef ARU_PROJECTOR_IDENTITY
 if(!p->identity)
#endif
 q=q*p->matrix;output={q.x,q.y,q.z};}
 return true;
}
static std::vector<V> resampled(const std::vector<V>& points){
 const size_t n=points.size();std::vector<double> distances(n,0.);
 for(size_t i=1;i<n;++i){V d=points[i]-points[i-1];distances[i]=distances[i-1]+std::hypot(d.x,d.y,d.z);}
 if(distances.back()<1e-12)return std::vector<V>(n,points[0]);
 std::vector<V> result;result.reserve(n);result.push_back(points[0]);size_t j=0;
 for(size_t k=1;k+1<n;++k){double want=distances.back()*k/double(n-1);while(j<n-2&&distances[j+1]<want)++j;
 double span=distances[j+1]-distances[j],u=span<1e-12?0:(want-distances[j])/span;result.push_back(points[j]+(points[j+1]-points[j])*u);}
 result.push_back(points.back());return result;
}
static bool surfaceHit(Projector* p,V v,double* out,int* meta,bool includeNormal=true){
   if(!std::isfinite(v.x)||!std::isfinite(v.y)||!std::isfinite(v.z))return 0;
   MPoint query=MPoint(v.x,v.y,v.z)*p->inverse;MPointOnMesh hit;if(!p->intersector.getClosestPoint(query,hit))return 0;
   auto local=hit.getPoint();MPoint world=MPoint(local.x,local.y,local.z)*p->matrix;V pos{world.x,world.y,world.z};
   MVector normal;
   if(includeNormal){auto n=hit.getNormal();normal=MVector(n.x,n.y,n.z).transformAsNormal(p->matrix);if(normal.length()>1e-12)normal.normalize();}
   int face=hit.faceIndex();if(face<0||static_cast<unsigned>(face)>=p->counts.length())return 0;
   unsigned start=p->offsets[face];int size=p->counts[face];if(size<1)return 0;
   auto point=[&](int i){auto q=p->worldPoints[p->indices[start+i]];return V{q.x,q.y,q.z};};
   int ids[3]={p->indices[start],-1,-1},used=1;double weights[3]={1,0,0},best=-1.;bool found=false;
   V a=point(0);
   for(int i=1;i<size-1;++i){V b=point(i),c=point(i+1),v0=b-a,v1=c-a,v2=pos-a;
    double d00=dot(v0,v0),d01=dot(v0,v1),d11=dot(v1,v1),d20=dot(v2,v0),d21=dot(v2,v1),D=d00*d11-d01*d01;
    if(std::abs(D)<1e-14)continue;
    double y=(d11*d20-d01*d21)/D,z=(d00*d21-d01*d20)/D,x=1-y-z;
    if(x<-.05||y<-.05||z<-.05)continue;
    double score=std::min({x,y,z});if(score>best){best=score;found=true;used=3;ids[0]=p->indices[start];ids[1]=p->indices[start+i];ids[2]=p->indices[start+i+1];weights[0]=x;weights[1]=y;weights[2]=z;}
   }
   if(!found && size>=3){double distance=1e30;for(int i=0;i<size;++i){V d=point(i)-pos;double value=std::sqrt(d.x*d.x+d.y*d.y+d.z*d.z);if(value<distance){distance=value;ids[0]=p->indices[start+i];}}}
   for(int k=0;k<3;++k){out[k]=pos[k];out[k+6]=weights[k];meta[k+1]=ids[k];}
   out[3]=normal.x;out[4]=normal.y;out[5]=normal.z;meta[0]=face;meta[4]=used;
   return true;
}
static int fitRoutes(void* handle,const double* controls,int count,int segments,int iterations,int samples,
 int rounds,double relax,double epsRatio,double restoreMin,double* output,double* hits=nullptr,int* metadata=nullptr){
 try {
  auto* p=static_cast<Projector*>(handle);
  if(!p||!p->owner.isAlive()||!p->owner.isValid()||count<0||segments<2||samples<1||!controls||!output)return 0;
  for(int i=0;i<count*12;++i)if(!std::isfinite(controls[i]))return 0;
  if((hits==nullptr)!=(metadata==nullptr))return 0;
  auto finish=[&](int curve)->int {
   if(!hits)return 1;
   for(int side=0;side<2;++side){int index=curve*2+side;
    if(!surfaceHit(p,read(output+3*index),hits+9*index,metadata+5*index,false))return 0;
   }
   return 1;
  };
  auto fitCurve=[&](int curve)->int {
   try {
   const double* c=controls+curve*12;V a=read(c),h=read(c+3),j=read(c+6),b=read(c+9);
   if(length(b-a)<1e-9){for(int k=0;k<3;++k){output[curve*6+k]=h[k];output[curve*6+3+k]=j[k];}return finish(curve);}
   V n0,n3;if(!projected(p,a,n0,true)||!projected(p,b,n3,true))return 0;
   std::vector<V> points;points.push_back(a);
   for(int k=1;k<segments;++k){V hit;if(!projected(p,bezier(a,h,j,b,k/double(segments)),hit))return 0;points.push_back(hit);}points.push_back(b);
   V delta=b-a;double tol=std::max(std::hypot(delta.x,delta.y,delta.z),1e-9)*1e-4;
   for(int iteration=0;iteration<std::max(1,iterations);++iteration){
    std::vector<V> next=points;
    for(int k=1;k<segments;++k)next[k]=points[k]+((points[k-1]+points[k+1])*.5-points[k])*relax;
    next=resampled(next);double moved=0.;
    for(int k=1;k<segments;++k){V hit;if(!projected(p,next[k],hit))return 0;V d=hit-points[k];moved=std::max(moved,d.x*d.x+d.y*d.y+d.z*d.z);next[k]=hit;}
    points.swap(next);if(moved<tol*tol)break;
   }
   std::vector<double> poly;for(V point:points){poly.push_back(point.x);poly.push_back(point.y);poly.push_back(point.z);}
   double normals[]={n0.x,n0.y,n0.z,n3.x,n3.y,n3.z},fitted[7];
   if(!aru_path_fit(c,poly.data(),static_cast<int>(points.size()),normals,samples,rounds,0,epsRatio,restoreMin,fitted))return 0;
   std::copy(fitted,fitted+6,output+curve*6);
   return finish(curve);
   }catch(...){return 0;}
  };
  int failed=0;
  // Join these short-lived workers before subsequent Maya/OpenMP evaluation.
  // A persistent OpenMP team increased downstream mesh evaluation in GUI tests.
#ifndef ARU_ROUTE_WORKERS
#define ARU_ROUTE_WORKERS 4
#endif
  const int threads=std::min(ARU_ROUTE_WORKERS,static_cast<int>(std::max(1u,std::thread::hardware_concurrency())));
  if(count<16 || threads==1){
   for(int curve=0;curve<count;++curve)failed|=!fitCurve(curve);
  }else{
#ifdef ARU_PROJECTOR_SLEEPING_TEAM
   failed=p->parallel(count,fitCurve,1);
#else
   std::vector<std::future<int>> tasks;
   for(int worker=0;worker<threads;++worker){
    tasks.push_back(std::async(std::launch::async,[&,worker]{
     int errors=0;
     for(int curve=worker;curve<count;curve+=threads)errors|=!fitCurve(curve);
     return errors;
    }));
   }
   for(auto& task:tasks)failed|=task.get();
#endif
  }
  return !failed;
 }catch(...){return 0;}
}

API int aru_maya_fit_routes(void* handle,const double* controls,int count,int segments,int iterations,int samples,
 int rounds,double relax,double epsRatio,double restoreMin,double* output){
 return fitRoutes(handle,controls,count,segments,iterations,samples,rounds,relax,epsRatio,restoreMin,output);
}
// Fit and collect handle bindings within the same joined worker batch. No
// Maya scene access occurs in workers; the intersector and polygon tables are immutable.
API int aru_maya_fit_routes_bound(void* handle,const double* controls,int count,int segments,int iterations,int samples,
 int rounds,double relax,double epsRatio,double restoreMin,double* output,double* hits,int* metadata){
 if(!hits||!metadata)return 0;
 return fitRoutes(handle,controls,count,segments,iterations,samples,rounds,relax,epsRatio,restoreMin,output,hits,metadata);
}

API int aru_maya_surface_hits(void* handle,const double* queries,int count,double* output,int* metadata){
 try{
  auto* p=static_cast<Projector*>(handle);
  if(!p||!p->owner.isAlive()||!p->owner.isValid()||count<0||!queries||!output||!metadata)return 0;
  for(int index=0;index<count;++index)
   if(!surfaceHit(p,read(queries+3*index),output+9*index,metadata+5*index))return 0;
  return 1;
 }catch(...){return 0;}
}

// Normal-only consumers do not need world hit positions or polygon bindings.
API int aru_maya_normals(void* handle,const double* queries,int count,double* output){
 try{
  auto* p=static_cast<Projector*>(handle);
  if(!p||!p->owner.isAlive()||!p->owner.isValid()||count<0||!queries||!output)return 0;
  for(int i=0;i<count;++i){
   V v=read(queries+3*i);if(!std::isfinite(v.x)||!std::isfinite(v.y)||!std::isfinite(v.z))return 0;
   MPoint query=MPoint(v.x,v.y,v.z)*p->inverse;MPointOnMesh hit;
   if(!p->intersector.getClosestPoint(query,hit))return 0;
   auto n=hit.getNormal();MVector normal=MVector(n.x,n.y,n.z).transformAsNormal(p->matrix);
   if(normal.length()>1e-12)normal.normalize();
   output[3*i]=normal.x;output[3*i+1]=normal.y;output[3*i+2]=normal.z;
  }
  return 1;
 }catch(...){return 0;}
}

// Fused projected length iterations. All Maya scene reads precede worker launch;
// workers use only immutable intersector data and disjoint numeric output rows.
API int aru_maya_junction_lengths(void* handle,const double* bases,const double* directions,
 const double* initial,const double* chords,const double* coefficients,const double* inverses,
 int count,double* output){
 try{
  auto* p=static_cast<Projector*>(handle);
  if(!p||!p->owner.isAlive()||!p->owner.isValid()||count<0||!bases||!directions||!initial||!chords||!coefficients||!inverses||!output)return 0;
  auto finite=[](const double* values,size_t n){for(size_t i=0;i<n;++i)if(!std::isfinite(values[i]))return false;return true;};
  if(!finite(bases,size_t(count)*45)||!finite(directions,size_t(count)*6)||!finite(initial,size_t(count)*2)||!finite(chords,count)||!finite(coefficients,30)||!finite(inverses,size_t(count)*94))return 0;
  auto fit=[&](int i)->int{
   try{
    const double* base=bases+45*i;const double* ds=directions+6*i;const double* inv=inverses+94*i;
    double lengths[2]={initial[2*i],initial[2*i+1]};double rhs[47];
    if(chords[i]<1e-9)return 0;
    for(int iteration=0;iteration<4;++iteration){
     for(int sample=0;sample<15;++sample){
      double query[3];double c0=coefficients[2*sample],c1=coefficients[2*sample+1];
      for(int k=0;k<3;++k)query[k]=base[3*sample+k]+(c0*lengths[0])*ds[k]+(c1*lengths[1])*ds[3+k];
      if(!finite(query,3))return 0;
      V hit;if(!projected(p,read(query),hit))return 0;
      for(int k=0;k<3;++k)rhs[3*sample+k]=hit[k]-base[3*sample+k];
     }
     rhs[45]=lengths[0]*.1;rhs[46]=lengths[1]*.1;
     for(int side=0;side<2;++side){
      double value=0;for(int k=0;k<47;++k)value+=inv[47*side+k]*rhs[k];
      if(!std::isfinite(value))return 0;
      lengths[side]=std::clamp(value,chords[i]*.05,chords[i]*.6);
     }
    }
    output[2*i]=lengths[0];output[2*i+1]=lengths[1];return 1;
   }catch(...){return 0;}
  };
  int failed=0;
  if(count<16){for(int i=0;i<count;++i)failed|=!fit(i);}
  else{
#ifdef ARU_PROJECTOR_SLEEPING_TEAM
   failed=p->parallel(count,fit,1);
#else
   int workers=std::min(4,static_cast<int>(std::max(1u,std::thread::hardware_concurrency())));
   std::vector<std::future<int>> tasks;
   for(int worker=0;worker<workers;++worker)tasks.push_back(std::async(std::launch::async,[&,worker]{int errors=0;for(int i=worker;i<count;i+=workers)errors|=!fit(i);return errors;}));
   for(auto& task:tasks)failed|=task.get();
#endif
  }
  return !failed;
 }catch(...){return 0;}
}

// Numeric branch pairing and tangent blending. Inputs are owned caller buffers;
// no scene access or callbacks are used by this kernel.
#include <tuple>
API int aru_maya_junction_directions(const double* points,const double* normals,
 const double* weights,double amount,const int* offsets,const double* branches,
 int count,int branchCount,int* selected,double* directions){
 try{
  if(count<0||branchCount<0||!points||!normals||!weights||!offsets||!branches||!selected||!directions||!std::isfinite(amount))return -1;
  if(offsets[0]!=0||offsets[count]!=branchCount)return -1;
  for(int i=0;i<count;++i)if(offsets[i]<0||offsets[i+1]<offsets[i]||offsets[i+1]>branchCount)return -1;
  auto finite=[](const double* v,size_t n){for(size_t i=0;i<n;++i)if(!std::isfinite(v[i]))return false;return true;};
  if(!finite(points,size_t(count)*3)||!finite(normals,size_t(count)*3)||!finite(weights,count)||!finite(branches,size_t(branchCount)*6))return -1;
  auto divided=[](V v,double d){return V{v.x/d,v.y/d,v.z/d};};
  struct Branch {int source;V direction;};
  std::vector<Branch> valid;
  std::vector<std::tuple<double,int,int>> pairs;
  std::vector<unsigned char> used;
  int outputCount=0;
  for(int row=0;row<count;++row){
   V p=read(points+3*row),n=read(normals+3*row);double normalLength=length(n);if(!std::isfinite(normalLength))return -1;n=divided(n,std::max(normalLength,1e-12));
   valid.clear();pairs.clear();
   for(int index=offsets[row];index<offsets[row+1];++index){
    V v=read(branches+6*index)-p;v=v-n*dot(v,n);double magnitude=length(v);if(!std::isfinite(magnitude))return -1;
    if(magnitude>1e-9)valid.push_back({index,divided(v,std::max(magnitude,1e-12))});
   }
   for(int i=0;i<static_cast<int>(valid.size());++i)
    for(int j=i+1;j<static_cast<int>(valid.size());++j)pairs.emplace_back(dot(valid[i].direction,valid[j].direction),i,j);
   std::sort(pairs.begin(),pairs.end());used.assign(valid.size(),0);
   for(auto pair:pairs){
    double alignment=std::get<0>(pair);int i=std::get<1>(pair),j=std::get<2>(pair);
    if(alignment>-.3||used[i]||used[j])continue;
    used[i]=used[j]=1;
    V axis=valid[i].direction-valid[j].direction;axis=divided(axis,length(axis));
    for(int side=0;side<2;++side){
     const Branch& branch=valid[side?j:i];V target=axis*(side?-1.:1.);
     V v=read(branches+6*branch.source+3)-p;v=v-n*dot(v,n);double magnitude=length(v);if(!std::isfinite(magnitude))return -1;
     v=magnitude>1e-9?divided(v,std::max(magnitude,1e-12)):branch.direction;
     double alpha=std::min(1.,amount*weights[row]);V d=v*(1-alpha)+target*alpha;
     double magnitudeD=length(d);if(!std::isfinite(magnitudeD))return -1;d=divided(d,std::max(magnitudeD,1e-12));
     selected[outputCount]=branch.source;
     for(int k=0;k<3;++k)directions[3*outputCount+k]=d[k];
     ++outputCount;
    }
   }
  }
  return outputCount;
 }catch(...){return -1;}
}
