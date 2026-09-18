"""Depth-neutral point expansion for the retopo guide render pass.

Use Maya's installed point shader graph, retaining its API-specific expansion,
selection semantics and pixel sizing. Its extra size-dependent Z displacement
is intended for Maya's component overlay and conflicts with shared scene depth.
The guide pass already supplies its display bias, so remove only that second
Z displacement from our private copy. Never replace Maya's registered shader.
"""
import re
import maya.api.OpenMayaRender as render

_GEOMETRY='aruRetopoDepthPointQuad'
_GRAPH='aruRetopoDepthPointShaderV2'


def shader(manager):
    fragments=render.MRenderer.getFragmentManager()
    if not fragments.hasFragment(_GRAPH):
        geometry=fragments.getFragmentXML('mayaPoint2Quad')
        if not geometry:
            raise RuntimeError('Maya point shader fragments are unavailable.')
        # Pc was already initialized from the input clip position plus XY size.
        geometry,count=re.subn(r'outS\.Pc\.z\s*=\s*(?:inputs\[0\]\.Pc|gl_in\[0\]\.gl_Position)\.z\s*-\s*dp\s*;',
                               '',geometry)
        if count<2:
            raise RuntimeError('Unsupported Maya point shader depth implementation.')
        geometry=geometry.replace('mayaPoint2Quad',_GEOMETRY)
        graph=_graph_xml()
        if not fragments.hasFragment(_GEOMETRY):
            fragments.addShadeFragmentFromBuffer(geometry.encode('utf-8'),False)
        fragments.addFragmentGraphFromBuffer(graph.encode('utf-8'))
        if not fragments.hasFragment(_GRAPH):
            raise RuntimeError('Retopo point shader registration failed.')
    return manager.getFragmentShader(_GRAPH,'outColor',True)


def _graph_xml():
    # Build our own graph: Maya may serialize an already-compiled stock graph
    # without its vertex-stage connection and auto-bound input properties.
    properties=[]
    for kind,name,ref,semantic,flags in (
        ('float4','solidColor','color.solidColor','',''),
        ('struct','inputs','quad.inputs','',''),
        ('float2','pointSize','quad.pointSize','',''),
        ('float2','screenSize','quad.screenSize','viewportPixelSize',''),
        ('float4','quadPositionUV','quad.quadPositionUV','quadPositionUVType0',''),
        ('float4x4','viewprojectioninverse','quad.viewprojectioninverse','viewprojectioninverse',''),
        ('bool','isCulled','quad.isCulled','',''),
        ('float','DepthPriorityUnit','quad.DepthPriorityUnit','DepthPriorityUnit',''),
        ('bool','orthographic','quad.orthographic','isorthographic',''),
        ('float','depthPriorityThreshold','quad.depthPriorityThreshold','mayadepthprioritythreshold',''),
        ('float3','Pm','vertex.Pm','POSITION','varyingInputParam'),
        ('float4x4','WorldViewProj','vertex.WorldViewProj','worldviewprojection',''),
        ('float','DepthPriority','vertex.DepthPriority','DepthPriority',''),
        ('float','depthPriorityScale','vertex.depthPriorityScale','mayadepthprioirtyscale',''),
    ):
        attributes=' name="%s" ref="%s"'%(name,ref)
        if semantic:attributes+=' semantic="%s"'%semantic
        if flags:attributes+=' flags="%s"'%flags
        properties.append('<%s%s />'%(kind,attributes))
    return ('<fragment_graph name="%s" ref="%s" class="FragmentGraph" version="1.0">'
            '<keyword value="componentShader"/><fragments>'
            '<fragment_ref name="color" ref="mayaSolidColorGS"/>'
            '<fragment_ref name="quad" ref="%s"/>'
            '<fragment_ref name="vertex" ref="mayaDepthPriorityShader"/>'
            '</fragments><connections>'
            '<connect from="quad.GPUStage" to="color.GPUStage" name="GPUStage"/>'
            '<connect from="vertex.GPUStage" to="quad.GPUStage" name="GPUStage"/>'
            '</connections><properties>%s</properties>'
            '<values><float4 name="solidColor" value="1,1,1,1"/>'
            '<float2 name="pointSize" value="6,6"/>'
            '<bool name="isCulled" value="false"/></values>'
            '<outputs><float4 name="outColor" ref="color.mayaSolidColorGS"/></outputs>'
            '</fragment_graph>')%(_GRAPH,_GRAPH,_GEOMETRY,''.join(properties))
