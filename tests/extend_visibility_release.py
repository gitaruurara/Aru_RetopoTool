from pathlib import Path
p=Path('tests/visibility_release_cases.py');s=p.read_text()
needle='    from Aru_RetopoTool.editor.curvenet import maya_visibility as native'
insert='''    # Same shape in a different DAG instance, including mirrored/nonuniform scale.
    instance=cmds.instance(mesh)[0]
    cmds.setAttr(instance+'.translateX',4.)
    cmds.setAttr(instance+'.scale',-1.2,.7,1.6)
    for target in (mesh,instance):
        for view in views:
            for occlusion in (False,True):
                scalar=edit.make_visibility_test(target,view_info=view,occlusion=occlusion,use_acceleration=False)
                batched=edit.make_visibility_test(target,view_info=view,occlusion=occlusion)
                assert [scalar(p) for p in queries]==batched.many(queries.tolist())
'''
assert needle in s;s=s.replace(needle,insert+needle);p.write_text(s)
p=Path('cpp/build_maya_visibility.ps1');s=p.read_text()
s=s.replace(', [switch]$SleepingTeam, [switch]$PrecomputePath, [switch]$IdentityProjection','')
s='\n'.join(line for line in s.splitlines() if '$extraFlags=' not in line and 'if ($IdentityProjection)' not in line and 'if ($PrecomputePath)' not in line and 'if ($SleepingTeam)' not in line)+'\n'
s=s.replace('@extraFlags ','').replace(' /openmp','');p.write_text(s)
