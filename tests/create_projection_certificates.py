from pathlib import Path
p=Path('cpp/retopo.cpp')
s=p.read_text()
if 'V projectCertified(' in s: raise SystemExit('Certificate solver is already integrated; use build_interactive.ps1.')
s=s.replace('std::vector<unsigned char> cachedValid;', 'std::vector<unsigned char> cachedValid;\n    std::vector<double> cachedSeparation;')
s=s.replace('cachedValid.assign(count,0);','cachedValid.assign(count,0);cachedSeparation.assign(count,0.);')
s=s.replace('''        cachedInputSeed[index]=seed;cachedQuery[index]=p;
        V answer=project(p,seed,guard);''','''        V answer=p;const int oldHit=cachedOutputSeed[index];bool reuse=false;
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
        else answer=projectCertified(p,seed,guard,cachedSeparation[index]);''')
marker='\n};\nAPI int aru_retopo_version()'
assert marker in s
s=s.replace(marker,'''
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
'''+marker)
assert 'else answer=projectCertified' in s
Path('cpp/retopo_certificates_candidate.cpp').write_text(s)
b=Path('cpp/build_mesh_buffer.ps1').read_text().replace('$PSScriptRoot/retopo.cpp','$PSScriptRoot/retopo_certificates_candidate.cpp')
Path('cpp/build_certificates_candidate.ps1').write_text(b)

