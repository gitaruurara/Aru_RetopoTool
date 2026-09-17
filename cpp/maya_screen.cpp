// Synchronous GUI-thread projection; no retained view, camera or Maya objects.
#include <maya/M3dView.h>
#include <maya/MPoint.h>
#include <maya/MMatrix.h>
#include <maya/MStatus.h>
#include <cmath>
#include <algorithm>
#include <vector>
extern "C" __declspec(dllexport) int aru_maya_screen_points(
    const double* points,int count,short* output,unsigned char* valid){
    try{
        if(count<0 || (!points && count) || (!output && count) || (!valid && count))return 0;
        MStatus status;M3dView view=M3dView::active3dView(&status);
        if(!status)return 0;
#ifdef ARU_SCREEN_MATRIX
        MMatrix model,projection;
        if(!view.modelViewMatrix(model) || !view.projectionMatrix(projection))return 0;
        const double width=view.portWidth(),height=view.portHeight();
#endif
        for(int i=0;i<count;++i){
#ifdef ARU_SCREEN_MATRIX
            MPoint clip=MPoint(points[3*i],points[3*i+1],points[3*i+2])*model*projection;
            if(std::abs(clip.w)>1.e-12){
                double sx=(clip.x/clip.w+1.)*width*.5,sy=(clip.y/clip.w+1.)*height*.5;
                // Preserve Maya's rounding and overflow behavior near integer
                // boundaries, the eye plane, and outside the short pixel range.
                if(std::isfinite(sx)&&std::isfinite(sy)&&sx>-32767.&&sx<32767.&&sy>-32767.&&sy<32767.
                   &&std::abs(sx-std::round(sx))>1.e-5&&std::abs(sy-std::round(sy))>1.e-5){
                    output[2*i]=static_cast<short>(sx);output[2*i+1]=static_cast<short>(sy);valid[i]=1;continue;
                }
            }
#endif
            short x=0,y=0;
            // The bool reports viewport inclusion; the Python path also keeps
            // coordinates for offscreen/behind-camera points when status succeeds.
            view.worldToView(MPoint(points[3*i],points[3*i+1],points[3*i+2]),x,y,&status);
            valid[i]=status?1:0;output[2*i]=x;output[2*i+1]=y;
        }
        return 1;
    }catch(...){return 0;}
}

// Compact candidates in the same spline/segment order as the Python picker.
extern "C" __declspec(dllexport) int aru_maya_screen_segments(
 const double* positions,int vertexCount,const int* curves,int curveCount,
 double sx,double sy,double tolerance,int* indices,double* parameters,double* distances){
 try{
  if(vertexCount<0||curveCount<0||!positions||!curves||!indices||!parameters||!distances)return -1;
  MStatus status;M3dView view=M3dView::active3dView(&status);if(!status)return -1;
  double ts[25],basis[25][4];
  for(int k=0;k<=24;++k){double t=k/24.,u=1.-t;ts[k]=t;
   basis[k][0]=std::pow(u,3.);basis[k][1]=3*std::pow(u,2.)*t;
   basis[k][2]=3*u*std::pow(t,2.);basis[k][3]=std::pow(t,3.);}
#ifdef ARU_SCREEN_HULL
  MMatrix model,projection;
  const bool haveMatrices=view.modelViewMatrix(model)&&view.projectionMatrix(projection);
  struct ScreenControl{short x=0,y=0;bool bounded=false;};
  std::vector<ScreenControl> screen(vertexCount);
  if(haveMatrices)for(int i=0;i<vertexCount;++i){
   MPoint point(positions[3*i],positions[3*i+1],positions[3*i+2]);
   MPoint clip=point*model*projection;
   auto& c=screen[i];bool inside=view.worldToView(point,c.x,c.y,&status);
   // Positive homogeneous weights preserve the projected Bezier convex hull.
   // Use only on-screen controls, away from short-coordinate overflow.
   c.bounded=inside&&status&&std::isfinite(clip.w)&&clip.w>1.e-8
       &&view.portWidth()<32760&&view.portHeight()<32760
       &&c.x>=0&&c.y>=0&&c.x<int(view.portWidth())&&c.y<int(view.portHeight());
  }
  const double margin=std::sqrt(std::max(0.,tolerance))+4.;
#endif
  int found=0;
  for(int row=0;row<curveCount;++row){
   for(int j=0;j<4;++j)if(curves[4*row+j]<0||curves[4*row+j]>=vertexCount)return -1;
#ifdef ARU_SCREEN_HULL
   bool bounded=std::isfinite(sx)&&std::isfinite(sy)&&std::isfinite(margin);
   double loX=32767,loY=32767,hiX=-32768,hiY=-32768;
   for(int j=0;j<4;++j){const auto& c=screen[curves[4*row+j]];bounded=bounded&&c.bounded;
    loX=std::min(loX,double(c.x));hiX=std::max(hiX,double(c.x));
    loY=std::min(loY,double(c.y));hiY=std::max(hiY,double(c.y));}
   if(bounded&&(sx<loX-margin||sx>hiX+margin||sy<loY-margin||sy>hiY+margin))continue;
#endif
   short x[25],y[25];bool valid[25];
   for(int k=0;k<=24;++k){
    double p[3];for(int axis=0;axis<3;++axis){
     p[axis]=basis[k][0]*positions[3*curves[4*row]+axis]+basis[k][1]*positions[3*curves[4*row+1]+axis]
             +basis[k][2]*positions[3*curves[4*row+2]+axis]+basis[k][3]*positions[3*curves[4*row+3]+axis];}
    x[k]=y[k]=0;view.worldToView(MPoint(p[0],p[1],p[2]),x[k],y[k],&status);valid[k]=bool(status);
   }
   for(int k=0;k<24;++k){
    if(!valid[k]||!valid[k+1])continue;
    double ex=double(x[k+1])-x[k],ey=double(y[k+1])-y[k],length=ex*ex+ey*ey;
    double u=length<1.e-12?0.:std::max(0.,std::min(1.,((sx-x[k])*ex+(sy-y[k])*ey)/length));
    double dx=sx-(x[k]+ex*u),dy=sy-(y[k]+ey*u),distance=dx*dx+dy*dy;
    if(distance<tolerance){indices[found]=row*24+k;parameters[found]=ts[k]+(ts[k+1]-ts[k])*u;distances[found]=distance;++found;}
   }
  }
  return found;
 }catch(...){return -1;}
}
