#include "maya_projector.cpp"
API int aru_maya_junction_compact(void* handle,const double* controls,const double* directions,
 const double* initial,const double* chords,const double* coefficients,
 int count,double* output){
 try{
  auto* p=static_cast<Projector*>(handle);
  if(!p||!p->owner.isAlive()||!p->owner.isValid()||count<0||!controls||!directions||!initial||!chords||!coefficients||!output)return 0;
  auto finite=[](const double* values,size_t n){for(size_t i=0;i<n;++i)if(!std::isfinite(values[i]))return false;return true;};
  if(!finite(controls,size_t(count)*12)||!finite(directions,size_t(count)*6)||!finite(initial,size_t(count)*2)||!finite(chords,count)||!finite(coefficients,60))return 0;
  auto fit=[&](int i)->int{
   try{
    const double* ds=directions+6*i;const double* control=controls+12*i;
    double base[45],rows[47][2],inv[94];
    for(int sample=0;sample<15;++sample){
     const double* c=coefficients+4*sample;
     for(int axis=0;axis<3;++axis){
      int row=3*sample+axis;
      base[row]=c[2]*control[axis]+c[3]*control[9+axis];
      rows[row][0]=c[0]*ds[axis];rows[row][1]=c[1]*ds[3+axis];
     }
    }
    rows[45][0]=.1;rows[45][1]=0;rows[46][0]=0;rows[46][1]=.1;
    double aa=0,ab=0,bb=0;
    for(int row=0;row<47;++row){aa+=rows[row][0]*rows[row][0];ab+=rows[row][0]*rows[row][1];bb+=rows[row][1]*rows[row][1];}
    double determinant=aa*bb-ab*ab;if(!(determinant>0)||!std::isfinite(determinant))return 0;
    for(int row=0;row<47;++row){inv[row]=(bb*rows[row][0]-ab*rows[row][1])/determinant;inv[47+row]=(aa*rows[row][1]-ab*rows[row][0])/determinant;}

    double lengths[2]={initial[2*i],initial[2*i+1]};double rhs[47];
    if(chords[i]<1e-9)return 0;
    for(int iteration=0;iteration<4;++iteration){
     for(int sample=0;sample<15;++sample){
      double query[3];double c0=coefficients[4*sample],c1=coefficients[4*sample+1];
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

