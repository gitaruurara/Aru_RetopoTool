from pathlib import Path
s=Path('tests/native_relax_replay.py').read_text()
s=s.replace('for i in range(12):','''for i in range(24):
        if i in (2,4,6,8):
            points=[list(p) for p in data['reference_points']]
            triangles=list(data['reference_indices'])
            if i==2:
                for p in points:p[2]+=.015*p[0]
            if i==6:
                for j in range(0,len(triangles),3):triangles[j+1],triangles[j+2]=triangles[j+2],triangles[j+1]
            storage=om.MFnMeshData().create()
            om.MFnMesh().create(om.MPointArray(points),[3]*(len(triangles)//3),triangles,parent=storage)
            dep.findPlug('referenceMesh',False).setMObject(storage)
        if i in (10,14):
            weights=list(data['arrays']['guideWeights'])
            if i==10:weights=[v*.5 for v in weights]
            dep.findPlug('guideWeights',False).setMObject(om.MFnDoubleArrayData().create(weights))
        if i in (12,14):
            adjacency=list(data['arrays']['adjacencyIndices'])
            if i==12:
                offsets=data['arrays']['adjacencyOffsets']
                for j in range(len(offsets)-1):adjacency[offsets[j]:offsets[j+1]]=reversed(adjacency[offsets[j]:offsets[j+1]])
            dep.findPlug('adjacencyIndices',False).setMObject(om.MFnIntArrayData().create(adjacency))
        if i==16:
            cmds.setAttr(node+'.relaxIterations',3);cmds.setAttr(node+'.projectionGuard',False)
        if i==18:cmds.setAttr(node+'.projectToReference',False)
        if i==20:
            for key,value in data['settings'].items():cmds.setAttr(node+'.'+key,value)
        if i==22:
            cmds.setAttr(node+'.guideMatrix',1,0,0,0,0,1,0,0,0,0,1,0,.02,0,0,1,type='matrix')''')
s=s.replace("row={'ms':elapsed,", "row={'output_hash':hashes[str(i%2)],'frame':i,'ms':elapsed,")
s=s.replace("'native_relax_replay_'+version", "'projection_certificates_node_state_'+version")
s=s.replace("print('NATIVE RELAX REPLAY PASSED'", "print('CERTIFICATE NODE STATE PASSED'")
Path('tests/projection_certificates_node_state.py').write_text(s)
s=Path('tests/run_native_relax_replay.bat').read_text().replace('native_relax_replay.py','projection_certificates_node_state.py')
Path('tests/run_projection_certificates_node_state.bat').write_text(s)
