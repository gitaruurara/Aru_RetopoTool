from pathlib import Path
p=Path('tests/projection_certificates_cases.py');s=p.read_text()
s=s.replace("root/'bin/2027'", "root/'bin'/cmds.about(version=True)")
s=s.replace('for case in range(6):','for case in range(8):')
s=s.replace('if case==3:tri.extend((0,0,1,0,1,1,2,2,2))','''if case==3:tri.extend((0,0,1,0,1,1,2,2,2))
        if case==6:tri.extend(tri[:6])  # exact duplicate triangles / tied winners
        if case==7:tri=[j for i in range(0,len(tri),3) for j in (tri[i],tri[i+2],tri[i+1])]''')
s=s.replace('for frame in range(80):','''for frame in range(80):
                count=127 if 32<=frame<48 else 512
                offsets=ints([i*2 for i in range(count+1)])
                neighbors=ints([j for i in range(count) for j in ((i-1)%count,(i+1)%count)])
                seeds=(seeds+[-1]*count)[:count]''')
s=s.replace('for p in positions for value in p','for p in positions[:count] for value in p')
s=s.replace('seeds=[rng.randrange(-1,len(t)//3) for _ in range(count)]','seeds=[rng.randrange(-3,len(t)//3+3) for _ in range(count)]')
s=s.replace('seeds=outputs[0][1];checks+=1','''if frame%10==0:
                    fresh=candidate.aru_surface_create(v,len(v)//3,t,len(t)//3)
                    try:
                        values=doubles(raw);ids=ints(seeds)
                        assert candidate.aru_relax(fresh,values,count,offsets,neighbors,weights,steps,strength,ids,guard)==1
                        assert (list(values),list(ids))==outputs[0],('cold',case,frame)
                    finally:candidate.aru_surface_destroy(fresh)
                seeds=outputs[0][1];checks+=1''')
s=s.replace("'points_per_comparison':512", "'point_counts':[127,512],'maya':cmds.about(version=True),'cold_comparisons':64")
s=s.replace("'large translation']", "'large translation','duplicate triangles','reversed winding']")
s=s.replace("root/'tests/projection_certificates_cases.json'", "root/'tests'/('projection_certificates_cases_'+cmds.about(version=True)+'.json')")
p.write_text(s)
p=Path('tests/projection_certificates_stroke.py');s=p.read_text().replace("'bin/2027/aru_retopo_mesh_buffer_'", "'bin/'+cmds.about(version=True)+'/aru_retopo_mesh_buffer_'")
s=s.replace("node='aruRetopoGuideShape1';native='aruRetopoNative1'", """owners=[p for p in cmds.pluginInfo(q=True,listPlugins=True) or [] if 'aruRetopoMeshBuffer' in (cmds.pluginInfo(p,q=True,dependNode=True) or [])]
    assert len(owners)==1,owners
    loaded=cmds.pluginInfo(owners[0],q=True,path=True)
    assert Path(loaded).name=='aru_retopo_mesh_buffer_'+version+'.mll',loaded
    node='aruRetopoGuideShape1';native='aruRetopoNative1'""")
s=s.replace("report={'version':version,", "report={'version':version,'maya':cmds.about(version=True),'loaded_plugin':loaded,")
s=s.replace("'projection_certificates_stroke_'+version+'.json'", "'projection_certificates_stroke_'+version+'_'+cmds.about(version=True)+'.json'")
p.write_text(s)
