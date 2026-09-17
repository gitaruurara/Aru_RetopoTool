// Standalone C ABI: no Python ABI or Maya SDK dependency.
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numeric>
#include <vector>
#include <stdexcept>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
struct V {
    double x,y,z;
    double operator[](int i) const { return i==0?x:i==1?y:z; }
    V operator+(V b)const{return {x+b.x,y+b.y,z+b.z};}
    V operator-(V b)const{return {x-b.x,y-b.y,z-b.z};}
    V operator*(double s)const{return {x*s,y*s,z*s};}
};
static V read(const double* p){return {p[0],p[1],p[2]};}
static void write(double* p,V a){p[0]=a.x;p[1]=a.y;p[2]=a.z;}
static double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static V normal(V a){double l=std::sqrt(dot(a,a));return l>1e-20?a*(1/l):V{0,0,0};}
struct Tri{V a,b,c,n,center; int component;};
struct Box{
    V lo{1e300,1e300,1e300},hi{-1e300,-1e300,-1e300};
    void add(V p){lo={std::min(lo.x,p.x),std::min(lo.y,p.y),std::min(lo.z,p.z)};
                  hi={std::max(hi.x,p.x),std::max(hi.y,p.y),std::max(hi.z,p.z)};}
    double distance(V p)const{double d=0;for(int k=0;k<3;++k){double x=std::max({lo[k]-p[k],0.,p[k]-hi[k]});d+=x*x;}return d;}
};
struct Node{Box box; int start,count,left=-1,right=-1;};
static V segment(V p,V a,V b){V d=b-a;double l=dot(d,d);return a+d*(l>1e-30?std::clamp(dot(p-a,d)/l,0.,1.):0.);}
static V closest(V p,const Tri& t){
    V a=t.a,b=t.b,c=t.c,ab=b-a,ac=c-a,ap=p-a;
    if(dot(t.n,t.n)<.5){V q=segment(p,a,b),r=segment(p,b,c),s=segment(p,c,a);
        if(dot(p-r,p-r)<dot(p-q,p-q))q=r;if(dot(p-s,p-s)<dot(p-q,p-q))q=s;return q;}
    double d1=dot(ab,ap),d2=dot(ac,ap);if(d1<=0&&d2<=0)return a;
    V bp=p-b;double d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return b;
    double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return a+ab*(d1/(d1-d3));
    V cp=p-c;double d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6)return c;
    double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return a+ac*(d2/(d2-d6));
    double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6)));
    double den=1/(va+vb+vc);return a+ab*(vb*den)+ac*(vc*den);
}
struct Surface{
    std::vector<Tri> tris;std::vector<int> order;std::vector<Node> nodes;
    int build(int begin,int end){
        int id=(int)nodes.size();nodes.push_back({});Box box,centers;
        for(int i=begin;i<end;++i){auto&t=tris[order[i]];box.add(t.a);box.add(t.b);box.add(t.c);centers.add(t.center);}
        nodes[id].box=box;nodes[id].start=begin;nodes[id].count=end-begin;
        if(end-begin>8){V size=centers.hi-centers.lo;int axis=size.y>size.x?1:0;if(size.z>size[axis])axis=2;
            int mid=(begin+end)/2;std::nth_element(order.begin()+begin,order.begin()+mid,order.begin()+end,
                [&](int a,int b){return tris[a].center[axis]<tris[b].center[axis];});
            int left=build(begin,mid),right=build(mid,end);nodes[id].left=left;nodes[id].right=right;}
        return id;
    }
    void search(int id,V p,int component,V priorNormal,bool guard,double& best,V& q,int& hit)const{
        const auto& node=nodes[id];if(node.box.distance(p)>best)return;
        if(node.left<0){for(int i=node.start;i<node.start+node.count;++i){int ti=order[i];const auto&t=tris[ti];
            if(guard&&(t.component!=component||dot(t.n,priorNormal)<0.0))continue;
            V candidate=closest(p,t);double d=dot(candidate-p,candidate-p);
            if(d<best){best=d;q=candidate;hit=ti;}}
        }else{int a=node.left,b=node.right;if(nodes[a].box.distance(p)>nodes[b].box.distance(p))std::swap(a,b);
            search(a,p,component,priorNormal,guard,best,q,hit);search(b,p,component,priorNormal,guard,best,q,hit);}
    }
    V project(V p,int& seed,bool guard)const{
        bool valid=seed>=0&&seed<(int)tris.size();V q=p;double best=std::numeric_limits<double>::max();int hit=-1;
        int comp=valid?tris[seed].component:-1;V n=valid?tris[seed].n:V{0,0,0};
        search(0,p,comp,n,guard&&valid,best,q,hit);seed=hit;return q;
    }
};
API int aru_retopo_version(){return 1;}
API void* aru_surface_create(const double* vertices,int nv,const int* indices,int nt){
    Surface* s=nullptr;try{
        if(nv<3||nt<1)return nullptr;
        s=new Surface;std::vector<int> parent(nv);std::iota(parent.begin(),parent.end(),0);
        auto root=[&](int a){while(parent[a]!=a){parent[a]=parent[parent[a]];a=parent[a];}return a;};
        for(int i=0;i<nt*3;++i)if(indices[i]<0||indices[i]>=nv)throw std::runtime_error("index");
        for(int i=0;i<nt;++i){int a=indices[3*i],b=indices[3*i+1],c=indices[3*i+2];parent[root(b)]=root(a);parent[root(c)]=root(a);}
        s->tris.reserve(nt);
        for(int i=0;i<nt;++i){V a=read(vertices+3*indices[3*i]),b=read(vertices+3*indices[3*i+1]),c=read(vertices+3*indices[3*i+2]);
            s->tris.push_back({a,b,c,normal(cross(b-a,c-a)),(a+b+c)*(1./3),root(indices[3*i])});}
        s->order.resize(nt);std::iota(s->order.begin(),s->order.end(),0);s->build(0,nt);return s;
    }catch(...){delete s;return nullptr;}
}
API void aru_surface_destroy(void* p){delete static_cast<Surface*>(p);}
API int aru_project(void* p,const double* input,int n,double* output,int* seeds,double* normals,int guard){
    try{if(!p)return 0;auto&s=*static_cast<Surface*>(p);for(int i=0;i<n;++i){
        V q=s.project(read(input+3*i),seeds[i],guard!=0);write(output+3*i,q);
        if(normals)write(normals+3*i,seeds[i]>=0?s.tris[seeds[i]].n:V{0,0,0});}return 1;
    }catch(...){return 0;}
}
API int aru_stencil(const double* input,const int* offsets,const int* ids,const double* weights,int n,double* output){
    for(int i=0;i<n;++i){V q{0,0,0};for(int j=offsets[i];j<offsets[i+1];++j)q=q+read(input+3*ids[j])*weights[j];write(output+3*i,q);}return 1;
}
API int aru_relax(void* p,double* points,int n,const int* offsets,const int* neighbors,
                  const double* guide_weights,int iterations,double strength,int* seeds,int guard){
    try{if(!p)return 0;auto&s=*static_cast<Surface*>(p);std::vector<V> target(n),current(n),next(n);
        for(int i=0;i<n;++i)target[i]=current[i]=s.project(read(points+3*i),seeds[i],guard!=0);
        for(int k=0;k<iterations;++k){for(int i=0;i<n;++i){V avg{0,0,0};int degree=offsets[i+1]-offsets[i];
            for(int j=offsets[i];j<offsets[i+1];++j)avg=avg+current[neighbors[j]];
            V q=degree?current[i]*(1-strength)+avg*(strength/degree):current[i];
            q=q*(1-guide_weights[i])+target[i]*guide_weights[i];next[i]=s.project(q,seeds[i],guard!=0);
        }current.swap(next);}
        for(int i=0;i<n;++i)write(points+3*i,current[i]);return 1;
    }catch(...){return 0;}
}
