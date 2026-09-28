#include "maya_projector.cpp"
#include <climits>
API int aru_maya_relax_endpoints(void* handle,const double* xyz,int vertices,const int* ids,const int* offsets,const int* neighbors,const double* weights,int count,double strength,int smooth,double* hits,int* metadata){
 try {
 auto* p=static_cast<Projector*>(handle);
 if(!p||!p->owner.isAlive()||!p->owner.isValid()||vertices<0||vertices>INT_MAX/3||count<0||count>INT_MAX/9||!xyz||!ids||!offsets||!neighbors||!weights||!hits||!metadata||!std::isfinite(strength)||offsets[0]!=0)return 0;
 for(int i=0;i<vertices*3;++i)if(!std::isfinite(xyz[i]))return 0;
 for(int i=0;i<count;++i){if(ids[i]<0||ids[i]>=vertices||!std::isfinite(weights[i])||offsets[i]<0||offsets[i+1]<offsets[i])return 0;}
 for(int i=0;i<offsets[count];++i)if(neighbors[i]<0||neighbors[i]>=vertices)return 0;
 auto endpoint=[&](int i)->int{
 try{
 V original=read(xyz+3*ids[i]),target=original;
 int degree=offsets[i+1]-offsets[i];
 if(smooth&&degree>=2){
 V projectedPoint,normal;if(!projected(p,original,projectedPoint)||!projected(p,projectedPoint,normal,true))return 0;
 V center{0,0,0};for(int j=offsets[i];j<offsets[i+1];++j)center=center+read(xyz+3*neighbors[j]);
 for(int k=0;k<3;++k)center[k]/=degree;
 V delta=center-original;double normalLength=dot(normal,normal),dn=dot(delta,normal)/std::max(normalLength,1e-12);
 for(int k=0;k<3;++k)target[k]=projectedPoint[k]+strength*weights[i]*(delta[k]-dn*normal[k]);
 }
 return surfaceHit(p,target,hits+9*i,metadata+5*i);
 }catch(...){return 0;}
 };
 int failed=0;
 if(count<64){for(int i=0;i<count;++i)failed|=!endpoint(i);}
 else{
 const int workers=4;std::vector<std::future<int>> tasks;
 for(int w=0;w<workers;++w)tasks.push_back(std::async(std::launch::async,[&,w]{int errors=0;for(int i=w;i<count;i+=workers)errors|=!endpoint(i);return errors;}));
 for(auto& task:tasks)failed|=task.get();
 }
 return !failed;
 }catch(...){return 0;}
}
