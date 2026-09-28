// Pure numeric Bezier-to-polyline fitter. No Maya/Python objects or callbacks.
#include <cmath>
#include <algorithm>
#include <vector>
#include <limits>
struct V {
 double x,y,z;
 double& operator[](int i){return i==0?x:i==1?y:z;}
 double operator[](int i)const{return i==0?x:i==1?y:z;}
 V operator+(V b)const{return{x+b.x,y+b.y,z+b.z};}
 V operator-(V b)const{return{x-b.x,y-b.y,z-b.z};}
 V operator*(double s)const{return{x*s,y*s,z*s};}
};
static V read(const double*p){return{p[0],p[1],p[2]};}
static double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static double length(V a){return std::sqrt(dot(a,a));}
static V unit(V a){double l=length(a);return l>1e-12?a*(1/l):V{0,0,0};}
static V bezier(V a,V h,V j,V b,double t){double u=1-t;return a*(u*u*u)+h*(3*u*u*t)+j*(3*u*t*t)+b*(t*t*t);}
static V closest(const std::vector<V>& path,V p){
 if(path.size()==1)return path[0];
 double best=std::numeric_limits<double>::infinity();V answer=p;
 for(size_t i=0;i+1<path.size();++i){
  V a=path[i],v=path[i+1]-a;double vv=dot(v,v);
  double t=vv<1e-18?0:std::clamp(dot(p-a,v)/vv,0.,1.);
  V q=a+v*t;double d=dot(q-p,q-p);if(d<best){best=d;answer=q;}
 }return answer;
}
#ifdef ARU_PATH_PRECOMPUTE
// The target polyline is immutable throughout a fit. Preserve the exact
// subtraction/dot/division order while reusing segment geometry per query.
struct PreparedPath {
 const std::vector<V>& points;
 std::vector<V> vectors;
 std::vector<double> lengths;
 explicit PreparedPath(const std::vector<V>& p):points(p){
  vectors.reserve(p.size()-1);lengths.reserve(p.size()-1);
  for(size_t i=0;i+1<p.size();++i){V v=p[i+1]-p[i];vectors.push_back(v);lengths.push_back(dot(v,v));}
 }
};
static V closest(const PreparedPath& path,V p){
 if(path.points.size()==1)return path.points[0];
 double best=std::numeric_limits<double>::infinity();V answer=p;
 for(size_t i=0;i<path.vectors.size();++i){
  V a=path.points[i],v=path.vectors[i];double vv=path.lengths[i];
  double t=vv<1e-18?0:std::clamp(dot(p-a,v)/vv,0.,1.);
  V q=a+v*t;double d=dot(q-p,q-p);if(d<best){best=d;answer=q;}
 }return answer;
}
#endif
extern "C" __declspec(dllexport) int aru_path_fit(const double* controls,const double* poly,int count,
 const double* normals,int samples,int rounds,int fixed,double epsRatio,double restoreMin,double* out){
 try {
  if(!controls||!poly||!normals||!out||count<1||samples<1||rounds<0||fixed<0||fixed>2)return 0;
  for(int i=0;i<12;++i)if(!std::isfinite(controls[i]))return 0;
  for(int i=0;i<count*3;++i)if(!std::isfinite(poly[i]))return 0;
  for(int i=0;i<6;++i)if(!std::isfinite(normals[i]))return 0;
  std::vector<V> path;for(int i=0;i<count;++i)path.push_back(read(poly+3*i));
#ifdef ARU_PATH_PRECOMPUTE
  PreparedPath queryPath(path);
#else
  const auto& queryPath=path;
#endif
  V p=read(controls),h=read(controls+3),j=read(controls+6),q=read(controls+9);
  V n0=read(normals),n3=read(normals+3),bh=h,bj=j;
  double chord=length(q-p),eps=chord*epsRatio,minimum=chord*.05,maximum=chord*.75;
  struct Coefficient {double t,u,c1,c2,pu,pt;};
  std::vector<Coefficient> coefficients;coefficients.reserve(samples);
  for(int k=1;k<=samples;++k){double t=k/(samples+1.),u=1-t;coefficients.push_back({t,u,3*u*u*t,3*u*t*t,std::pow(u,3),std::pow(t,3)});}
  double best=-1;
  auto consider=[&](V a,V b){double error=0;for(int k=1;k<=samples;++k){V s=bezier(p,a,b,q,k/(samples+1.));error+=length(closest(queryPath,s)-s);}error/=samples;if(best<0||error<best){best=error;bh=a;bj=b;}return error;};
  for(int iteration=0;iteration<rounds;++iteration){
   double error=0,a11=0,a12=0,a22=0;V r1{0,0,0},r2{0,0,0};
   for(int k=1;k<=samples;++k){
    const auto& coefficient=coefficients[k-1];double t=coefficient.t,u=coefficient.u,c1=coefficient.c1,c2=coefficient.c2;
    V sample=bezier(p,h,j,q,t),target=closest(queryPath,sample);error+=length(target-sample);
    a11+=c1*c1;a12+=c1*c2;a22+=c2*c2;
    for(int axis=0;axis<3;++axis){double rhs=target[axis]-coefficient.pu*p[axis]-coefficient.pt*q[axis];r1[axis]+=c1*rhs;r2[axis]+=c2*rhs;}
   }
   error/=samples;if(best<0||error<best){best=error;bh=h;bj=j;}if(error<=eps)break;
   double det=a11*a22-a12*a12;V d1{0,0,0},d2{0,0,0};
   if(fixed==1){if(a22<1e-12)break;d1=h-p;for(int k=0;k<3;++k)d2[k]=(r2[k]-a12*d1[k])/a22-q[k];}
   else if(fixed==2){if(a11<1e-12)break;d2=j-q;for(int k=0;k<3;++k)d1[k]=(r1[k]-a12*d2[k])/a11-p[k];}
   else{if(std::abs(det)<1e-12)break;for(int k=0;k<3;++k){d1[k]=(a22*r1[k]-a12*r2[k])/det-p[k];d2[k]=(a11*r2[k]-a12*r1[k])/det-q[k];}}
   auto clamp=[&](V d,bool locked){if(locked)return d;double l=length(d);if(l>maximum)return d*(maximum/l);if(l<minimum&&l>1e-9)return d*(minimum/l);return d;};
   V nh=p+clamp(d1,fixed==1),nj=q+clamp(d2,fixed==2);bool stop=length(nh-h)<eps&&length(nj-j)<eps;h=nh;j=nj;if(stop)break;
  }
  consider(h,j);
  V gd0=count>1?path[1]-path[0]:q-p,gd3=count>1?path[count-2]-path[count-1]:p-q;
  if(length(gd0)<1e-9)gd0=q-p;if(length(gd3)<1e-9)gd3=p-q;
  auto tangent=[&](V v,V n,V fallback){double l=length(v);if(l<1e-9)return fallback;V t=v-n*dot(v,n);double tl=length(t);if(tl<l*.25)return unit(fallback)*l;if(tl<l*restoreMin)return t;return t*(l/tl);};
  V t1=fixed==1?bh-p:tangent(bh-p,n0,gd0),t2=fixed==2?bj-q:tangent(bj-q,n3,gd3);
  consider(p+t1,q+t2);
  for(int k=0;k<3;++k){out[k]=bh[k];out[k+3]=bj[k];}out[6]=best;return 1;
 }catch(...){return 0;}
}
