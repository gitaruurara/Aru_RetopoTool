// Serial Maya ray queries. Python wrapper restricts calls to the main thread.
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MFnMesh.h>
#include <maya/MString.h>
#include <maya/MStatus.h>
#include <maya/MVector.h>
#include <cmath>
#include <limits>
#define API extern "C" __declspec(dllexport)
#include <maya/MFloatPoint.h>
#include <maya/MFloatVector.h>
// Calls scene ray intersection only serially on the Python caller's main thread.
API int aru_maya_visibility(const char* path,const double* points,const double* normals,
 int count,const double* eye,const double* direction,int ortho,int occlusion,double lift,
 int accelerated,unsigned char* output){
 try{
  if(!path||count<0||count>std::numeric_limits<int>::max()/3||!eye||!direction||(!points&&count)||(!normals&&count)||(!output&&count)||!std::isfinite(lift))return 0;
  for(int i=0;i<3;++i)if(!std::isfinite(eye[i])||!std::isfinite(direction[i]))return 0;
  for(int i=0;i<count*3;++i)if(!std::isfinite(points[i])||!std::isfinite(normals[i]))return 0;
  if(!count)return 1;
  MSelectionList selection;MDagPath dag;
  if(!selection.add(MString(path))||!selection.getDagPath(0,dag))return 0;
  if(dag.hasFn(MFn::kTransform)&&!dag.extendToShape())return 0;
  MStatus status;MFnMesh mesh(dag,&status);if(!status)return 0;
  MMeshIsectAccelParams accel=mesh.autoUniformGridParams();
  for(int i=0;i<count;++i){
   const double* p=points+3*i;const double* n=normals+3*i;
   MVector toEye(ortho?-direction[0]:eye[0]-p[0],ortho?-direction[1]:eye[1]-p[1],ortho?-direction[2]:eye[2]-p[2]);
   if(n[0]*toEye.x+n[1]*toEye.y+n[2]*toEye.z<=0.){output[i]=0;continue;}
   if(!occlusion){output[i]=1;continue;}
   MFloatPoint source(float(p[0]+n[0]*lift),float(p[1]+n[1]*lift),float(p[2]+n[2]*lift));
   double maximum=1.e9;
   if(!ortho){maximum=toEye.length();if(maximum<1.e-9){output[i]=1;continue;}toEye.normalize();}
   MFloatVector ray(float(toEye.x),float(toEye.y),float(toEye.z));MFloatPoint hitPoint;
   bool hit=mesh.closestIntersection(source,ray,nullptr,nullptr,false,MSpace::kWorld,float(maximum),false,
    accelerated?&accel:nullptr,hitPoint,nullptr,nullptr,nullptr,nullptr,nullptr,1.e-6f,&status);
   output[i]=status?!hit:1;
  }
  return 1;
 }catch(...){return 0;}
}
