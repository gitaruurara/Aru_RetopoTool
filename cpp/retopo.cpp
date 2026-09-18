// Standalone C ABI: no Python ABI or Maya SDK dependency.
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numeric>
#include <vector>
#include <stdexcept>
#include <future>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <memory>
#ifdef _OPENMP
#include <omp.h>
#endif
#ifndef ARU_RETOPO_LEAF_SIZE
#define ARU_RETOPO_LEAF_SIZE 8
#endif
#ifndef ARU_RETOPO_THREADS
#define ARU_RETOPO_THREADS 4
#endif
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
#ifdef ARU_RETOPO_CACHE_STATS
#include <atomic>
static std::atomic<unsigned long long> cacheStats[4];
API void aru_cache_stats(unsigned long long* out){
    for(int i=0;i<4;++i)out[i]=cacheStats[i].exchange(0,std::memory_order_relaxed);
}
#endif
static int projectionThreads(int n){
    const int cap=n>=8192?ARU_RETOPO_THREADS:std::min(4,ARU_RETOPO_THREADS);
    return std::max(1,std::min(cap,static_cast<int>(std::thread::hardware_concurrency())));
}
template<class F> static void parallelFor(int n,F fn){
    const int threads=n>=512?projectionThreads(n):1;
    if(threads==1){for(int i=0;i<n;++i)fn(i);return;}
    // A local edit affects spatially clustered rows. Claim small blocks so
    // expensive projections are spread across both fast and slow CPU cores.
    std::atomic<int> cursor{0};
    auto work=[&]{
        for(;;){
            int start=cursor.fetch_add(128,std::memory_order_relaxed);
            if(start>=n)return;
            for(int i=start;i<std::min(n,start+128);++i)fn(i);
        }
    };
    std::vector<std::future<void>> tasks;tasks.reserve(threads-1);
    for(int worker=1;worker<threads;++worker)
        tasks.push_back(std::async(std::launch::async,work));
    work();
    for(auto& task:tasks)task.get();
}
#ifdef ARU_RETOPO_SLEEPING_TEAM
// Surface-owned sleeping workers; destruction joins before the plugin unloads.
class ProjectionTeam {
    std::mutex mutex;
    std::condition_variable wake, done;
    std::vector<std::thread> workers;
    std::function<void()> job;
    unsigned generation=0;
    int remaining=0;
    bool stopping=false;
public:
    const int size;
    explicit ProjectionTeam(int count):size(count) {
        try {
            for(int i=1;i<count;++i)workers.emplace_back([this]{
                unsigned seen=0;
                for(;;){
                    std::unique_lock<std::mutex> lock(mutex);
                    wake.wait(lock,[&]{return stopping || generation!=seen;});
                    if(stopping)return;
                    seen=generation;auto task=job;lock.unlock();task();lock.lock();
                    if(--remaining==0)done.notify_one();
                }
            });
        } catch(...) {stop();throw;}
    }
    void stop(){
        {std::lock_guard<std::mutex> lock(mutex);stopping=true;}
        wake.notify_all();for(auto& worker:workers)if(worker.joinable())worker.join();
    }
    ~ProjectionTeam(){stop();}
    template<class F> void run(int n,F fn){
        std::atomic<int> cursor{0};std::exception_ptr error;std::mutex errors;
        auto work=[&]{try{
            for(;;){int start=cursor.fetch_add(128,std::memory_order_relaxed);if(start>=n)return;
                for(int i=start;i<std::min(n,start+128);++i)fn(i);}
        }catch(...){std::lock_guard<std::mutex> lock(errors);if(!error)error=std::current_exception();}};
        {std::lock_guard<std::mutex> lock(mutex);job=work;remaining=int(workers.size());++generation;}
        wake.notify_all();work();
        {std::unique_lock<std::mutex> lock(mutex);done.wait(lock,[&]{return remaining==0;});job={};}
        if(error)std::rethrow_exception(error);
    }
};
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
    #ifdef ARU_RETOPO_SLEEPING_TEAM
    std::unique_ptr<ProjectionTeam> team;
    #endif
    template<class F> void parallel(int n,F fn){
        #ifdef ARU_RETOPO_SLEEPING_TEAM
        int count=n>=512?projectionThreads(n):1;
        if(count==1){for(int i=0;i<n;++i)fn(i);return;}
        if(!team || team->size!=count)team=std::make_unique<ProjectionTeam>(count);
        team->run(n,fn);
        #else
        parallelFor(n,fn);
        #endif
    }
#ifdef ARU_RETOPO_REUSE_SCRATCH
    std::vector<V> relaxTarget,relaxCurrent,relaxNext;
#endif
    std::vector<V> cachedQuery,cachedAnswer;
    std::vector<int> cachedInputSeed,cachedOutputSeed;
    std::vector<unsigned char> cachedValid;
    std::vector<double> cachedSeparation;
    int cacheCount=0,cacheIterations=0;bool cacheGuard=false;
    void prepareCache(int n,int iterations,bool guard){
        if(cacheCount==n && cacheIterations==iterations && cacheGuard==guard)return;
        cacheCount=n;cacheIterations=iterations;cacheGuard=guard;
        size_t count=size_t(n)*(iterations+1);
        cachedQuery.resize(count);cachedAnswer.resize(count);
        cachedInputSeed.resize(count);cachedOutputSeed.resize(count);cachedValid.assign(count,0);cachedSeparation.assign(count,0.);
    }
    V cachedProject(size_t index,V p,int& seed,bool guard){
        V previous=cachedQuery[index];
#ifdef ARU_RETOPO_CACHE_STATS
        // Cold / changed query / changed seed only / exact cache hit.
        int reason=!cachedValid[index]?0:
            (p.x!=previous.x || p.y!=previous.y || p.z!=previous.z)?1:
            cachedInputSeed[index]!=seed?2:3;
        cacheStats[reason].fetch_add(1,std::memory_order_relaxed);
#endif
        if(cachedValid[index] && cachedInputSeed[index]==seed && p.x==previous.x && p.y==previous.y && p.z==previous.z){
            seed=cachedOutputSeed[index];return cachedAnswer[index];
        }
        V answer=p;const int oldHit=cachedOutputSeed[index];bool reuse=false;
        if(cachedValid[index] && oldHit>=0 && oldHit<int(tris.size())){
            const bool validSeed=seed>=0 && seed<int(tris.size());const auto& t=tris[oldHit];
            if(!guard || !validSeed || (t.component==tris[seed].component && dot(t.n,tris[seed].n)>=0.)){
                const V candidate=closest(p,t),delta=p-previous;
                const double margin=1.e-10*(1.+std::sqrt(dot(p,p))+std::sqrt(dot(candidate,candidate)));
                const double separation=cachedSeparation[index]-std::sqrt(dot(delta,delta))-margin;
                if(separation>0. && dot(candidate-p,candidate-p)<separation*separation){
                    answer=candidate;cachedSeparation[index]=separation;reuse=true;
                }
            }
        }
        cachedInputSeed[index]=seed;cachedQuery[index]=p;
        if(reuse)seed=oldHit;
        else answer=projectCertified(p,seed,guard,cachedSeparation[index]);
        cachedAnswer[index]=answer;cachedOutputSeed[index]=seed;cachedValid[index]=1;
        return answer;
    }
    std::vector<Tri> tris;std::vector<int> order;std::vector<Node> nodes;
    int build(int begin,int end){
        int id=(int)nodes.size();nodes.push_back({});Box box,centers;
        for(int i=begin;i<end;++i){auto&t=tris[order[i]];box.add(t.a);box.add(t.b);box.add(t.c);centers.add(t.center);}
        nodes[id].box=box;nodes[id].start=begin;nodes[id].count=end-begin;
        if(end-begin>ARU_RETOPO_LEAF_SIZE){V size=centers.hi-centers.lo;int axis=size.y>size.x?1:0;if(size.z>size[axis])axis=2;
            int mid=(begin+end)/2;std::nth_element(order.begin()+begin,order.begin()+mid,order.begin()+end,
                [&](int a,int b){return tris[a].center[axis]<tris[b].center[axis];});
            int left=build(begin,mid),right=build(mid,end);nodes[id].left=left;nodes[id].right=right;}
        return id;
    }
    void search(int id,V p,int component,V priorNormal,bool guard,double& best,V& q,int& hit,double lower)const{
        const auto& node=nodes[id];if(lower>best)return;
        if(node.left<0){for(int i=node.start;i<node.start+node.count;++i){int ti=order[i];const auto&t=tris[ti];
            if(guard&&(t.component!=component||dot(t.n,priorNormal)<0.0))continue;
            V candidate=closest(p,t);double d=dot(candidate-p,candidate-p);
            if(d<best){best=d;q=candidate;hit=ti;}}
        }else{int a=node.left,b=node.right;
            double da=nodes[a].box.distance(p),db=nodes[b].box.distance(p);
            if(da>db){std::swap(a,b);std::swap(da,db);}
            search(a,p,component,priorNormal,guard,best,q,hit,da);
            search(b,p,component,priorNormal,guard,best,q,hit,db);}
    }
    V project(V p,int& seed,bool guard)const{
        bool valid=seed>=0&&seed<(int)tris.size();V q=p;double best=std::numeric_limits<double>::max();int hit=-1;
        int comp=valid?tris[seed].component:-1;V n=valid?tris[seed].n:V{0,0,0};
        if(valid){q=closest(p,tris[seed]);best=dot(q-p,q-p);hit=seed;}
        search(0,p,comp,n,guard&&valid,best,q,hit,nodes[0].box.distance(p));seed=hit;return q;
    }
    // Conservative lower bounds include pruned boxes and guard exclusions.
    void searchCertified(int id,V p,int component,V priorNormal,bool guard,
                         double& best,V& q,int& hit,double lower,double& rival)const{
        const auto& node=nodes[id];
        if(lower>best){rival=std::min(rival,lower);return;}
        if(node.left<0){
            for(int i=node.start;i<node.start+node.count;++i){
                const int ti=order[i];const auto& t=tris[ti];
                if(ti==hit)continue;
                if(guard && (t.component!=component || dot(t.n,priorNormal)<0.)){
                    rival=0.;continue;
                }
                const V candidate=closest(p,t);const double d=dot(candidate-p,candidate-p);
                if(d<best){if(hit>=0)rival=std::min(rival,best);best=d;q=candidate;hit=ti;}
                else rival=std::min(rival,d);
            }
        }else{
            int a=node.left,b=node.right;
            double da=nodes[a].box.distance(p),db=nodes[b].box.distance(p);
            if(da>db){std::swap(a,b);std::swap(da,db);}
            searchCertified(a,p,component,priorNormal,guard,best,q,hit,da,rival);
            searchCertified(b,p,component,priorNormal,guard,best,q,hit,db,rival);
        }
    }
    V projectCertified(V p,int& seed,bool guard,double& separation)const{
        const bool valid=seed>=0 && seed<int(tris.size());
        V q=p;double best=std::numeric_limits<double>::max(),rival=best;int hit=-1;
        const int comp=valid?tris[seed].component:-1;const V n=valid?tris[seed].n:V{0,0,0};
        if(valid){q=closest(p,tris[seed]);best=dot(q-p,q-p);hit=seed;}
        searchCertified(0,p,comp,n,guard&&valid,best,q,hit,nodes[0].box.distance(p),rival);
        separation=std::max(0.,std::sqrt(rival)-1.e-10*(1.+std::sqrt(dot(p,p))+std::sqrt(dot(q,q))));
        seed=hit;return q;
    }

};
API int aru_retopo_version(){return 8;}
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
    try{parallelFor(n,[&](int i){V q{0,0,0};for(int j=offsets[i];j<offsets[i+1];++j)q=q+read(input+3*ids[j])*weights[j];write(output+3*i,q);});return 1;}catch(...){return 0;}
}
API int aru_stencil_rows(const double* input,const int* offsets,const int* ids,const double* weights,const int* rows,int count,double* output){
    try{parallelFor(count,[&](int k){int i=rows[k];V q{0,0,0};for(int j=offsets[i];j<offsets[i+1];++j)q=q+read(input+3*ids[j])*weights[j];write(output+3*i,q);});return 1;}catch(...){return 0;}
}
API int aru_relax(void* p,double* points,int n,const int* offsets,const int* neighbors,
                  const double* guide_weights,int iterations,double strength,int* seeds,int guard){
    try{if(!p)return 0;auto&s=*static_cast<Surface*>(p);
#ifdef ARU_RETOPO_REUSE_SCRATCH
        auto& target=s.relaxTarget;auto& current=s.relaxCurrent;auto& next=s.relaxNext;
        target.resize(n);current.resize(n);next.resize(n);
#else
        std::vector<V> target(n),current(n),next(n);
#endif
        s.prepareCache(n,iterations,guard!=0);
        s.parallel(n,[&](int i){target[i]=current[i]=s.cachedProject(i,read(points+3*i),seeds[i],guard!=0);});
        for(int k=0;k<iterations;++k){
        s.parallel(n,[&](int i){if(guide_weights[i]==1.){next[i]=target[i];return;}
            V avg{0,0,0};int degree=offsets[i+1]-offsets[i];
            for(int j=offsets[i];j<offsets[i+1];++j)avg=avg+current[neighbors[j]];
            V q=degree?current[i]*(1-strength)+avg*(strength/degree):current[i];
            q=q*(1-guide_weights[i])+target[i]*guide_weights[i];next[i]=s.cachedProject(size_t(k+1)*n+i,q,seeds[i],guard!=0);
        });current.swap(next);}
        for(int i=0;i<n;++i)write(points+3*i,current[i]);return 1;
    }catch(...){return 0;}
}

#include "stencil_compiler.h"
#include "subdivision.h"

#include "regions.h"
