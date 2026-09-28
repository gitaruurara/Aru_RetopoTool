"""Whole-loop dissolution with evenly redistributed surviving quad rows."""
from collections import defaultdict
from array import array
import math


def edge(a,b):return (min(a,b),max(a,b))


class Topology:
    def __init__(self,faces):
        self.faces=tuple(tuple(f) for f in faces)
        self.owners=defaultdict(list);self.neighbors=defaultdict(set)
        for i,f in enumerate(self.faces):
            if len(f)!=4 or len(set(f))!=4:raise ValueError('Loop reduction requires valid quads')
            for a,b in zip(f,f[1:]+f[:1]):
                self.owners[edge(a,b)].append(i);self.neighbors[a].add(b);self.neighbors[b].add(a)
        if any(len(f)>2 for f in self.owners.values()):raise ValueError('Non-manifold reduction topology')

    def continuation(self,a,b):
        """Opposite edge at regular b; a boundary endpoint terminates the chain."""
        incident=self.neighbors[b]
        boundary=[v for v in incident if len(self.owners[edge(b,v)])==1]
        if boundary:
            if len(incident)==3 and len(boundary)==2 and a not in boundary:return None
            raise ValueError('Loop reaches a corner or ambiguous boundary')
        if len(incident)!=4:raise ValueError('Loop reaches a pole or branch')
        adjacent={a}
        for fi in self.owners[edge(a,b)]:
            f=self.faces[fi];i=f.index(b)
            adjacent.update((f[i-1],f[(i+1)%4]))
        candidates=incident-adjacent
        if len(candidates)!=1:raise ValueError('No unique loop continuation')
        return next(iter(candidates))

    def loop(self,seed):
        seed=edge(*seed)
        if len(self.owners.get(seed,()))!=2:raise ValueError('A boundary edge cannot be dissolved')
        result={seed}
        for start in (seed,tuple(reversed(seed))):
            a,b=start;visited={a,b}
            while True:
                c=self.continuation(a,b)
                if c is None:break
                e=edge(b,c)
                if e==seed:break
                if c==start[0]:
                    result.add(e);break
                if c in visited:raise ValueError('Loop intersects itself')
                if len(self.owners[e])!=2:raise ValueError('Loop meets a boundary edge')
                result.add(e);visited.add(c);a,b=b,c
        return frozenset(result)

    def dissolve(self,loop,protected=()):
        removed={v for e in loop for v in e}
        if removed.intersection(protected):raise ValueError('Loop passes through a guide corner')
        used=set();replacement=[]
        for a,b in sorted(loop):
            owners=self.owners[edge(a,b)]
            if len(owners)!=2 or used.intersection(owners):raise ValueError('Adjacent loops must be reduced separately')
            used.update(owners)
            # Cancel the common directed edge, then walk the oriented hexagon.
            links={}
            for fi in owners:
                f=self.faces[fi]
                for x,y in zip(f,f[1:]+f[:1]):
                    if edge(x,y)!=edge(a,b):
                        if x in links:raise ValueError('Inconsistent face winding')
                        links[x]=y
            start=min(links);walk=[start];n=links[start]
            while n!=start:
                if n in walk or n not in links:raise ValueError('Invalid face union')
                walk.append(n);n=links[n]
            face=tuple(v for v in walk if v not in (a,b))
            if len(face)!=4 or len(set(face))!=4:raise ValueError('Reduction would make a non-quad')
            replacement.append(face)
        remaining=[f for i,f in enumerate(self.faces) if i not in used]
        if any(removed.intersection(f) for f in remaining):raise ValueError('Reduction would leave a T-junction')
        result=remaining+replacement
        # Coincident topological faces/overlapping strips are not safe reductions.
        if len({tuple(sorted(f)) for f in result})!=len(result):raise ValueError('Reduction would create duplicate faces')
        Topology(result)
        return tuple(result)


def describe(plan,seed,preferred=None):
    if isinstance(plan,ReducedPlan):
        return describe(plan.base,tuple(plan.kept[v] for v in seed),preferred)
    for key,uv in sorted(plan.edit_coordinates().items(),key=lambda item:item[0]!=preferred):
        if all(v in uv for v in seed):return {'patch':key,'edge':[list(uv[v]) for v in seed]}
    raise ValueError('Edge has no patch coordinates')


def locate(plan,request,topology):
    uv=plan.edit_coordinates().get(request['patch'],{})
    a,b=request['edge'];direction=[b[k]-a[k] for k in range(2)]
    length=math.hypot(*direction)
    if length<1e-10:raise ValueError('Invalid reduction direction')
    center=[(a[k]+b[k])*.5 for k in range(2)];candidates=[]
    for e,owners in topology.owners.items():
        if len(owners)!=2 or not all(v in uv for v in e):continue
        p,q=[uv[v] for v in e];delta=[q[k]-p[k] for k in range(2)];n=math.hypot(*delta)
        if n<1e-10 or abs(sum(delta[k]*direction[k] for k in range(2)))/(n*length)<.999:continue
        # Subdivision changes may split a saved seed into shorter edges on its line.
        if abs((p[0]-a[0])*direction[1]-(p[1]-a[1])*direction[0])/length>1e-7:continue
        distance=sum(((p[k]+q[k])*.5-center[k])**2 for k in range(2))
        candidates.append((distance,e))
    if not candidates:raise ValueError('Saved loop is absent at this subdivision level')
    return min(candidates)[1]


class ReducedPlan:
    def __init__(self,base,requests):
        self.base=base;faces=base.faces;self.applied=[];self.rejected=[]
        for request in requests:
            try:
                topology=Topology(faces);seed=locate(base,request,topology)
                loop=topology.loop(seed)
                faces=topology.dissolve(loop,range(len(base.endpoints)))
                self.applied.append((request,loop))
            except ValueError as exc:self.rejected.append((request,str(exc)))
        self.kept=sorted({v for f in faces for v in f});remap={v:i for i,v in enumerate(self.kept)}
        self.faces=tuple(tuple(remap[v] for v in f) for f in faces);self.count=len(self.kept)
        self.guide_vertices={remap[v]:g for v,g in base.guide_vertices.items() if v in remap}
        self.region_keys=base.region_keys;self.region_count=base.region_count
        self._coordinates={key:{remap[v]:uv for v,uv in coords.items() if v in remap}
                           for key,coords in base.edit_coordinates().items()}
        self._resample={}
        self._base_samples={}
        self._redistribute(base,remap)
        adjacency=[set() for _ in self.kept]
        for f in self.faces:
            for a,b in zip(f,f[1:]+f[:1]):adjacency[a].add(b);adjacency[b].add(a)
        self.adj_offsets=array('i',[0]);self.adj_ids=array('i')
        for neighbors in adjacency:self.adj_ids.extend(sorted(neighbors));self.adj_offsets.append(len(self.adj_ids))

    def _redistribute(self,base,remap):
        """Redistribute surviving rows in patch coordinates, preserving corners."""
        for key,coords in base.edit_coordinates().items():
            kept={v:uv for v,uv in coords.items() if v in remap}
            if len(kept)==len(coords):continue
            loop=base.region_loops[base.region_keys.index(key)]
            if len(loop)==4:
                axes=[sorted({round(uv[k],12) for uv in kept.values()}) for k in (0,1)]
                target={v:tuple(axes[k].index(round(uv[k],12))/(len(axes[k])-1) for k in (0,1))
                        for v,uv in kept.items()}
            else:
                # General patches: uniform boundary spacing and harmonic interior.
                neighbors={v:set() for v in kept}
                for face in self.faces:
                    old=[self.kept[v] for v in face]
                    if all(v in kept for v in old):
                        for a,b in zip(old,old[1:]+old[:1]):neighbors[a].add(b);neighbors[b].add(a)
                target=dict(kept);fixed={v for v in kept if v in base.guide_vertices}
                groups=defaultdict(list)
                for v in fixed:
                    g=base.guide_vertices[v]
                    if g[0]=='side':groups[g[1]].append((g[2],v))
                for side,values in groups.items():
                    samples=sorted((g[2],coords[v]) for v,g in base.guide_vertices.items()
                                   if v in coords and g[0]=='side' and g[1]==side)
                    if len(samples)<2:continue
                    (ta,pa),(tb,pb)=samples[0],samples[-1]
                    if abs(tb-ta)<1e-12:continue
                    delta=tuple((pb[k]-pa[k])/(tb-ta) for k in (0,1))
                    origin=tuple(pa[k]-ta*delta[k] for k in (0,1))
                    for rank,(_,v) in enumerate(sorted(values),1):
                        target[v]=tuple(origin[k]+rank/(len(values)+1)*delta[k] for k in (0,1))
                for _ in range(40):
                    target={v:target[v] if v in fixed or not neighbors[v] else
                            tuple(sum(target[n][k] for n in neighbors[v])/len(neighbors[v]) for k in (0,1)) for v in kept}
            for v,uv in target.items():
                self._coordinates[key][remap[v]]=uv
                if len(loop)==4:self._resample[remap[v]]=(loop,uv)
                else:
                    for face in base.faces:
                        if not all(x in coords for x in face):continue
                        found=False
                        for tri in (face[:3],(face[0],face[2],face[3])):
                            a,b,c=[coords[x] for x in tri]
                            det=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1])
                            if abs(det)<1e-14:continue
                            x,y=uv[0]-a[0],uv[1]-a[1]
                            q=(x*(c[1]-a[1])-y*(c[0]-a[0]))/det
                            t=((b[0]-a[0])*y-(b[1]-a[1])*x)/det
                            if min(q,t,1-q-t)>=-1e-9:
                                self._base_samples[remap[v]]=tuple(zip(tri,(1-q-t,q,t)));found=True;break
                        if found:break

    @staticmethod
    def _coons_row(loop,uv,splines):
        result=defaultdict(float);u,v=uv
        def side_row(side,t,weight):
            x=min(max(t,0.),1.)*len(side);i=min(int(x),len(side)-1)
            si,d=side[i];t=x-i if d==1 else 1-(x-i);q=1-t
            for cv,w in zip(splines[si],(q*q*q,3*q*q*t,3*q*t*t,t*t*t)):result[cv]+=weight*w
        for side,t,w in ((loop[0],u,1-v),(loop[1],v,u),(loop[2],1-u,v),(loop[3],1-v,1-u)):
            side_row(side,t,w)
        for side,w in zip(loop,((1-u)*(1-v),u*(1-v),u*v,(1-u)*v)):
            side_row(side,0.,-w)
        return {i:w for i,w in result.items() if abs(w)>1e-14}

    def edit_coordinates(self, keys=None):
        return self._coordinates if keys is None else {k:v for k,v in self._coordinates.items() if k in keys}

    def compile_stencil(self,splines):
        offsets,ids,weights=self.base.compile_stencil(splines)
        out=[0];indices=[];values=[]
        for index,v in enumerate(self.kept):
            if index in self._resample:
                loop,uv=self._resample[index];row=self._coons_row(loop,uv,splines)
                indices.extend(row);values.extend(row.values())
            elif index in self._base_samples:
                row=defaultdict(float)
                for source,factor in self._base_samples[index]:
                    for j in range(offsets[source],offsets[source+1]):row[ids[j]]+=factor*weights[j]
                indices.extend(row);values.extend(row.values())
            else:
                indices.extend(ids[offsets[v]:offsets[v+1]]);values.extend(weights[offsets[v]:offsets[v+1]])
            out.append(len(indices))
        return out,indices,values

    def evaluate(self,positions,splines,stencil=None):
        values=self.base.evaluate(positions,splines,stencil)
        result=[values[v] for v in self.kept]
        for index,samples in self._base_samples.items():
            result[index]=tuple(sum(values[v][k]*w for v,w in samples) for k in range(3))
        for index,(loop,uv) in self._resample.items():
            row=self._coons_row(loop,uv,splines)
            result[index]=tuple(sum(positions[v][k]*w for v,w in row.items()) for k in range(3))
        return result


def apply(plan,requests):return ReducedPlan(plan,requests) if requests else plan
