"""Endpoint welding with oriented spline ancestry for patch preservation."""

def weld(cn, keep=None, remove=None):
    original=list(cn.splines)
    parents=getattr(cn,'_retopo_parents',{})
    sources=getattr(cn,'_retopo_spline_sources',None)
    if sources is None:
        sources={i:((parents.get(i,i),1),) for i in range(len(original))}
    rows=[(keep if a==remove else a,h,j,keep if b==remove else b)
          if remove is not None else (a,h,j,b) for a,h,j,b in original]
    affected={tuple(sorted((rows[i][0],rows[i][3]))) for i,sp in enumerate(original)
              if remove is None or remove in (sp[0],sp[3])}
    groups={}
    for i,sp in enumerate(rows):
        if sp[0]!=sp[3]:groups.setdefault(tuple(sorted((sp[0],sp[3]))),[]).append(i)
    winners={}
    for key,ids in groups.items():
        if key in affected:
            # Prefer the boundary already attached to the destination endpoint.
            winner=min(ids,key=lambda i:(remove is not None and remove in (original[i][0],original[i][3]),i))
            for i in ids:winners[i]=winner
        else:
            for i in ids:winners[i]=i
    kept=[i for i in range(len(rows)) if winners.get(i)==i]
    remap={i:j for j,i in enumerate(kept)}
    ancestry={j:[] for j in range(len(kept))}
    for i,winner in winners.items():
        sign=1 if rows[i][0]==rows[winner][0] else -1
        ancestry[remap[winner]].extend((parent,d*sign) for parent,d in sources.get(i,()) if parent is not None)
        if i!=winner:
            targets=rows[winner][1:3] if sign==1 else tuple(reversed(rows[winner][1:3]))
            for old,new in zip(rows[i][1:3],targets):
                if old in cn.manual_handles:cn.mark_manual_handle(new)
    cn.splines=[rows[i] for i in kept]
    cn._retopo_spline_sources={i:tuple(dict.fromkeys(v)) for i,v in ancestry.items()}
    if hasattr(cn,'_retopo_parents'):
        cn._retopo_parents={j:parents.get(i) for j,i in enumerate(kept)}
    return len(original)-len(kept)
