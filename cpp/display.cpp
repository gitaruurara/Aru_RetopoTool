// Batched wire visibility using the same BVH as surface projection.
#include "retopo.cpp"
static bool rayBox(const Box& b,V o,V d,double limit){
    double lo=0,hi=limit;
    for(int k=0;k<3;++k){
        if(std::abs(d[k])<1e-15){if(o[k]<b.lo[k]||o[k]>b.hi[k])return false;continue;}
        double a=(b.lo[k]-o[k])/d[k],c=(b.hi[k]-o[k])/d[k];if(a>c)std::swap(a,c);
        lo=std::max(lo,a);hi=std::min(hi,c);if(lo>hi)return false;
    }return true;
}
static bool blocked(const Surface& s,int ni,V o,V d,double limit){
    const auto& n=s.nodes[ni];if(!rayBox(n.box,o,d,limit))return false;
    if(n.left>=0)return blocked(s,n.left,o,d,limit)||blocked(s,n.right,o,d,limit);
    for(int i=n.start;i<n.start+n.count;++i){
        const auto& t=s.tris[s.order[i]];V e=t.b-t.a,f=t.c-t.a,h=cross(d,f);
        double det=dot(e,h);if(std::abs(det)<1e-15)continue;
        double inv=1/det;V q=o-t.a;double u=dot(q,h)*inv;if(u< -1e-8||u>1+1e-8)continue;
        V r=cross(q,e);double v=dot(d,r)*inv;if(v< -1e-8||u+v>1+1e-8)continue;
        double distance=dot(f,r)*inv;if(distance>1e-8&&distance<limit)return true;
    }return false;
}
static int wireVisible(void* ptr,const double* points,const int* edges,const double* normals,int count,
                          const double* eye,const double* direction,int ortho,double* output,bool compact){
    if(!ptr)return -1;const auto& s=*static_cast<Surface*>(ptr);int written=0;
    V camera=read(eye),view=read(direction);
    for(int i=0;i<count;++i){
        V a=read(points+3*edges[i*4]),b=read(points+3*edges[i*4+1]);V delta=b-a;
        double eps=std::max(std::sqrt(dot(delta,delta))*1e-4,1e-6);
        int f1=edges[i*4+2],f2=edges[i*4+3];
        bool continuing=false;
        for(int j=0;j<4;++j){
            V p=a+delta*(j/4.),q=a+delta*((j+1)/4.),mid=(p+q)*.5;
            V toEye=ortho?view*(-1):camera-mid;
            if(dot(read(normals+3*f1),toEye)<=0 && (f2<0||dot(read(normals+3*f2),toEye)<=0)){continuing=false;continue;}
            double distance=std::sqrt(dot(toEye,toEye));if(distance<1e-10)continue;
            V ray=toEye*(1/distance);
            if(!blocked(s,0,mid+ray*eps,ray,ortho?1e10:std::max(distance-eps,eps))){
                if(compact&&continuing)write(output+3*(written-1),q);
                else{write(output+3*written++,p);write(output+3*written++,q);}
                continuing=true;
            }else continuing=false;
        }
    }return written;
}

API int aru_wire_visible(void* ptr,const double* points,const int* edges,const double* normals,int count,
                          const double* eye,const double* direction,int ortho,double* output){
    return wireVisible(ptr,points,edges,normals,count,eye,direction,ortho,output,false);
}
API int aru_wire_visible_compact(void* ptr,const double* points,const int* edges,const double* normals,int count,
                          const double* eye,const double* direction,int ortho,double* output){
    return wireVisible(ptr,points,edges,normals,count,eye,direction,ortho,output,true);
}

API int aru_wire_refit(void* ptr,const double* vertices,const int* indices,int nt){
    if(!ptr)return 0;auto& s=*static_cast<Surface*>(ptr);
    if(nt!=(int)s.tris.size())return 0;
    for(int i=0;i<nt;++i){auto& t=s.tris[i];
        t.a=read(vertices+3*indices[i*3]);t.b=read(vertices+3*indices[i*3+1]);t.c=read(vertices+3*indices[i*3+2]);
        t.n=normal(cross(t.b-t.a,t.c-t.a));t.center=(t.a+t.b+t.c)*(1./3);
    }
    for(int i=(int)s.nodes.size()-1;i>=0;--i){auto& n=s.nodes[i];Box b;
        if(n.left<0){for(int j=n.start;j<n.start+n.count;++j){const auto& t=s.tris[s.order[j]];b.add(t.a);b.add(t.b);b.add(t.c);}}
        else{b.add(s.nodes[n.left].box.lo);b.add(s.nodes[n.left].box.hi);b.add(s.nodes[n.right].box.lo);b.add(s.nodes[n.right].box.hi);}
        n.box=b;
    }return 1;
}
