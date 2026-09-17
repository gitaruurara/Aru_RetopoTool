// Experimental double-precision BVH closest-point projection.
struct Query { double4 position; int4 meta; };
struct Triangle { double4 a; double4 b; double4 c; double4 normal; int4 meta; };
struct Node { double4 lo; double4 hi; int4 meta; };
StructuredBuffer<Query> queries:register(t0);
StructuredBuffer<Triangle> triangles:register(t1);
StructuredBuffer<Node> nodes:register(t2);
StructuredBuffer<int> triangleOrder:register(t3);
RWStructuredBuffer<Query> result:register(u0);
StructuredBuffer<Query> targets:register(t4);
StructuredBuffer<int> offsets:register(t5);
StructuredBuffer<int> neighbors:register(t6);
StructuredBuffer<double> weights:register(t7);
struct Cached { Query source; Query answer; };
RWStructuredBuffer<Cached> history:register(u1);
cbuffer Params:register(b0) { uint count; uint triangleCount; uint guard; uint relaxing; double strength; uint cacheEnabled; uint cacheValid; };
double scalar(double3 a,double3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double3 segment(double3 p,double3 a,double3 b){double3 d=b-a;double l=scalar(d,d);return a+d*(l>1.e-30?clamp(scalar(p-a,d)/l,0.0L,1.0L):0.0L);}
double3 closest(double3 p,Triangle t){
 double3 a=t.a.xyz,b=t.b.xyz,c=t.c.xyz,ab=b-a,ac=c-a,ap=p-a;
 if(scalar(t.normal.xyz,t.normal.xyz)<.5){double3 q=segment(p,a,b),r=segment(p,b,c),s=segment(p,c,a);if(scalar(p-r,p-r)<scalar(p-q,p-q))q=r;if(scalar(p-s,p-s)<scalar(p-q,p-q))q=s;return q;}
 double d1=scalar(ab,ap),d2=scalar(ac,ap);if(d1<=0&&d2<=0)return a;
 double3 bp=p-b;double d3=scalar(ab,bp),d4=scalar(ac,bp);if(d3>=0&&d4<=d3)return b;
 double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return a+ab*(d1/(d1-d3));
 double3 cp=p-c;double d5=scalar(ab,cp),d6=scalar(ac,cp);if(d6>=0&&d5<=d6)return c;
 double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return a+ac*(d2/(d2-d6));
 double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6)));
 double den=1.0L/(va+vb+vc);return a+ab*(vb*den)+ac*(vc*den);
}
double boundDistance(int id,double3 p){Node node=nodes[id];double3 d=max(max(node.lo.xyz-p,0.0L),p-node.hi.xyz);return scalar(d,d);}
[numthreads(64,1,1)] void main(uint3 tid:SV_DispatchThreadID){
 uint i=tid.x;if(i>=count)return;
 Query query=queries[i];double3 p=query.position.xyz,q=p;int seed=query.meta.x,hit=-1,component=-1;double3 prior=0.0L;
 if(relaxing){
  double weight=weights[i];
  if(weight==1.0L){result[i]=targets[i];result[i].meta=query.meta;return;}
  double3 average=0.0L;int degree=offsets[i+1]-offsets[i];
  for(int j=offsets[i];j<offsets[i+1];++j)average+=queries[neighbors[j]].position.xyz;
  p=degree?p*(1.0L-strength)+average*(strength/degree):p;
  p=p*(1.0L-weight)+targets[i].position.xyz*weight;q=p;
 }
 Query source=query;source.position=double4(p,0.0L);
 if(cacheEnabled&&cacheValid){Cached old=history[i];if(old.source.meta.x==source.meta.x&&all(old.source.position.xyz==p)){result[i]=old.answer;return;}}
 bool seeded=seed>=0&&seed<(int)triangleCount;
 double best=asdouble(0xffffffff,0x7fefffff);
 if(seeded){Triangle t=triangles[seed];component=t.meta.x;prior=t.normal.xyz;q=closest(p,t);best=scalar(q-p,q-p);hit=seed;}
 int stack[64];double bounds[64];int top=1;stack[0]=0;bounds[0]=boundDistance(0,p);
 while(top>0){--top;int id=stack[top];double lower=bounds[top];if(lower>best)continue;Node node=nodes[id];
  if(node.meta.z<0){for(int j=node.meta.x;j<node.meta.x+node.meta.y;++j){int ti=triangleOrder[j];Triangle t=triangles[ti];
   if(guard&&seeded&&(t.meta.x!=component||scalar(t.normal.xyz,prior)<0.0L))continue;
   double3 candidate=closest(p,t);double distance=scalar(candidate-p,candidate-p);if(distance<best){best=distance;q=candidate;hit=ti;}
  }}else{int a=node.meta.z,b=node.meta.w;double da=boundDistance(a,p),db=boundDistance(b,p);if(da>db){int swap=a;a=b;b=swap;double temp=da;da=db;db=temp;}
   stack[top]=b;bounds[top]=db;++top;stack[top]=a;bounds[top]=da;++top;
  }
 }
 query.position=double4(q,0.0L);query.meta.x=hit;result[i]=query;
 if(cacheEnabled){Cached updated;updated.source=source;updated.answer=query;history[i]=updated;}
}
