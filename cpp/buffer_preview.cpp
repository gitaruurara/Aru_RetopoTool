// Experimental direct VP2 preview. DG access is confined to updateDG.
#include <maya/MPxLocatorNode.h>
#include <maya/MBoundingBox.h>
#include <maya/MPxGeometryOverride.h>
#include <maya/MFnPlugin.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnDoubleArrayData.h>
#include <maya/MFnIntArrayData.h>
#include <maya/MDoubleArray.h>
#include <maya/MIntArray.h>
#include <maya/MPlug.h>
#include <maya/MFnMesh.h>
#include <maya/MFnMeshData.h>
#include <maya/MPointArray.h>
#include <set>
#include <utility>
#include <maya/MDrawRegistry.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MShaderManager.h>
#include <maya/MHWGeometry.h>
#include <vector>
#include <cmath>
#include <cstring>
#ifdef ARU_BUFFER_TIMING
#include <atomic>
#include <chrono>
static std::atomic<long long> bufferNanos[3],bufferCalls[3],bufferSizes[2],bufferEnabled[2],bufferHashes[2];
extern "C" __declspec(dllexport) void aru_buffer_items(long long* values){for(int i=0;i<2;++i){values[i]=bufferSizes[i].load();values[i+2]=bufferEnabled[i].load();values[i+4]=bufferHashes[i].load();}}
struct BufferTimer {
    int stage;std::chrono::steady_clock::time_point start;
    explicit BufferTimer(int i):stage(i),start(std::chrono::steady_clock::now()){}
    ~BufferTimer(){bufferNanos[stage].fetch_add(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count(),std::memory_order_relaxed);bufferCalls[stage].fetch_add(1,std::memory_order_relaxed);}
};
extern "C" __declspec(dllexport) void aru_buffer_stats(double* ms,long long* calls){
    for(int i=0;i<3;++i){ms[i]=bufferNanos[i].exchange(0)/1.e6;calls[i]=bufferCalls[i].exchange(0);}
}
#define BUFFER_TIMER(i) BufferTimer timer(i)
#else
#define BUFFER_TIMER(i)
#endif
using namespace MHWRender;
namespace {
const MString classification("drawdb/geometry/aruRetopoBufferPreview");
const MString registrant("aruRetopoBufferPreviewRegistrant");
class PreviewNode : public MPxLocatorNode {
public:
    static MTypeId id;
    static MObject positions, triangles, edges, counts, indices;
    static void* creator() { return new PreviewNode; }
    static MStatus initialize() {
        MFnTypedAttribute a;
        positions=a.create("positions","pos",MFnData::kDoubleArray); addAttribute(positions);
        triangles=a.create("triangleIndices","tri",MFnData::kIntArray); addAttribute(triangles);
        edges=a.create("edgeIndices","edg",MFnData::kIntArray); addAttribute(edges);
        counts=a.create("faceCounts","fc",MFnData::kIntArray); addAttribute(counts);
        indices=a.create("faceIndices","fi",MFnData::kIntArray); addAttribute(indices);
        return MS::kSuccess;
    }
    // Object-set render passes still use DAG bounds for their visibility list.
    // An empty origin box drops retopo geometry far from the world origin.
    bool isBounded() const override { return true; }
    MBoundingBox boundingBox() const override {
        MStatus status;
        MFnDoubleArrayData data(MPlug(thisMObject(),positions).asMObject(),&status);
        MBoundingBox box;
        if(status) {
            const MDoubleArray values=data.array();
            for(unsigned i=0;i+2<values.length();i+=3)
                if(std::isfinite(values[i]) && std::isfinite(values[i+1]) && std::isfinite(values[i+2]))
                    box.expand(MPoint(values[i],values[i+1],values[i+2]));
        }
        return box;
    }
    MStatus setDependentsDirty(const MPlug&,MPlugArray&) override {
        MRenderer::setGeometryDrawDirty(thisMObject()); return MS::kSuccess;
    }
};
MTypeId PreviewNode::id(0x00131AD7);
MObject PreviewNode::positions,PreviewNode::triangles,PreviewNode::edges,PreviewNode::counts,PreviewNode::indices;
class PreviewGeometry : public MPxGeometryOverride {
    MObject node;
    std::vector<float> xyz;
    std::vector<unsigned int> triangles,edges;
    bool valid=false;
    bool indexingDirty=true;
    std::vector<int> previousCounts,previousIndices;
    size_t previousVertexCount=0;
    std::vector<unsigned int> cachedTriangles,cachedEdges;
    static bool readIndices(const MObject& node,const MObject& attr,
                            size_t count,unsigned stride,std::vector<unsigned int>& out) {
        MStatus status;
        MObject data=MPlug(node,attr).asMObject();
        MFnIntArrayData fn(data,&status);
        if (!status) return false;
        MIntArray values=fn.array();
        if (values.length()%stride) return false;
        std::vector<int> raw(values.length());
        if (!raw.empty()) values.get(raw.data());
        out.clear(); out.reserve(raw.size());
        for (int i:raw) { if(i<0 || static_cast<size_t>(i)>=count) return false; out.push_back(i); }
        return true;
    }
public:
    explicit PreviewGeometry(const MObject& obj):MPxGeometryOverride(obj),node(obj) {}
    static MPxGeometryOverride* creator(const MObject& obj) { return new PreviewGeometry(obj); }
    DrawAPI supportedDrawAPIs() const override { return kAllDevices; }
#ifdef ARU_BUFFER_STABLE_INDICES
    bool isIndexingDirty(const MRenderItem&) override { return indexingDirty; }
#endif
    void updateDG() override {
        BUFFER_TIMER(0);
        const bool wasValid=valid; indexingDirty=true;
        valid=false; xyz.clear(); triangles.clear(); edges.clear();
        MStatus status;
        MFnDoubleArrayData fn(MPlug(node,PreviewNode::positions).asMObject(),&status);
        if (!status) return;
        MDoubleArray values=fn.array();
        if(values.length()%3) return;
        std::vector<double> raw(values.length());
        if (!raw.empty()) values.get(raw.data());
        xyz.reserve(raw.size());
        for(double v:raw) { float f=static_cast<float>(v); if(!std::isfinite(f)) {xyz.clear();return;} xyz.push_back(f); }
        MObject countData=MPlug(node,PreviewNode::counts).asMObject();
        if(!countData.isNull()) {
            MFnIntArrayData cfn(countData,&status); if(!status) return;
            MIntArray counts=cfn.array();
            MFnIntArrayData ifn(MPlug(node,PreviewNode::indices).asMObject(),&status); if(!status) return;
            MIntArray indices=ifn.array();
            std::vector<int> fc(counts.length()),fi(indices.length());
            if(!fc.empty()) counts.get(fc.data()); if(!fi.empty()) indices.get(fi.data());
            size_t total=0;
            for(int n:fc) {if(n<3) return; total+=static_cast<size_t>(n);}
            if(total!=fi.size()) return;
            for(int i:fi) if(i<0 || static_cast<size_t>(i)>=xyz.size()/3) return;
            bool changed=fc!=previousCounts || fi!=previousIndices || previousVertexCount!=xyz.size()/3;
            indexingDirty=changed || !wasValid;
            if(changed) {
                previousVertexCount=static_cast<size_t>(-1);
                cachedTriangles.clear(); cachedEdges.clear();
                if(!fc.empty()) {
                    MPointArray points;
                    for(size_t i=0;i<raw.size();i+=3) points.append(MPoint(raw[i],raw[i+1],raw[i+2]));
                    MFnMeshData dataFn; MObject meshData=dataFn.create(); MFnMesh mesh;
                    mesh.create(points.length(),counts.length(),points,counts,indices,meshData,&status);
                    if(!status) return;
                    MIntArray triangleCounts,triangleIndices; mesh.getTriangles(triangleCounts,triangleIndices);
                    for(unsigned i=0;i<triangleIndices.length();++i) cachedTriangles.push_back(triangleIndices[i]);
                    std::set<std::pair<int,int>> uniqueEdges;
                    size_t offset=0;
                    for(int n:fc) {
                        for(int j=0;j<n;++j) {
                            int a=fi[offset+j],b=fi[offset+(j+1)%n];
                            if(a>b) std::swap(a,b); uniqueEdges.emplace(a,b);
                        }
                        offset+=n;
                    }
                    for(auto edge:uniqueEdges) {cachedEdges.push_back(edge.first);cachedEdges.push_back(edge.second);}
                }
                previousCounts=fc;previousIndices=fi;previousVertexCount=xyz.size()/3;
            }
            triangles=cachedTriangles;edges=cachedEdges;valid=true;return;
        }
        valid=readIndices(node,PreviewNode::triangles,xyz.size()/3,3,triangles)
           && readIndices(node,PreviewNode::edges,xyz.size()/3,2,edges);
    }
    void updateRenderItems(const MDagPath&,MRenderItemList& list) override {
        BUFFER_TIMER(1);
        auto* renderer=MRenderer::theRenderer();
        if(!renderer) return;
        auto* manager=renderer->getShaderManager();
        if(!manager) return;
        const char* names[]={"retopoSurface","retopoEdges"};
        for(unsigned i=0;i<2;++i) {
            int index=list.indexOf(names[i]);
            MRenderItem* item=index<0 ? nullptr : list.itemAt(index);
            if(!item) {
                indexingDirty=true;
                item=MRenderItem::Create(names[i],MRenderItem::DecorationItem,i?MGeometry::kLines:MGeometry::kTriangles);
                item->setAllowIsolateSelectCopy(true);
                item->setDrawMode(MGeometry::kAll);
                item->depthPriority(i?5:0);
                item->castsShadows(false); item->receivesShadows(false);
                auto* shader=manager->getStockShader(MShaderManager::k3dSolidShader);
                if(shader) {
                    const float surface[]={0.08f,0.65f,0.68f,1.f};
                    const float wire[]={0.015f,0.045f,0.055f,1.f};
                    shader->setParameter("solidColor",i?wire:surface);
                    item->setShader(shader); manager->releaseShader(shader);
                }
                list.append(item);
            }
            item->enable(valid && !(i?edges:triangles).empty());
#ifdef ARU_BUFFER_TIMING
            bufferEnabled[i].store(valid && !(i?edges:triangles).empty());
#endif
        }
    }
    void populateGeometry(const MGeometryRequirements& requirements,
                          const MRenderItemList& items,MGeometry& geometry) override {
        BUFFER_TIMER(2);
        if(!valid || xyz.empty()) return;
        const auto& descriptors=requirements.vertexRequirements();
        for(int i=0;i<descriptors.length();++i) {
            MVertexBufferDescriptor d; descriptors.getDescriptor(i,d);
            if(d.semantic()!=MGeometry::kPosition || d.dataType()!=MGeometry::kFloat || d.dimension()!=3) continue;
            auto* b=geometry.createVertexBuffer(d);
            if(!b) continue;
            void* dst=b->acquire(static_cast<unsigned>(xyz.size()/3),true);
            if(dst) {std::memcpy(dst,xyz.data(),xyz.size()*sizeof(float));b->commit(dst);}
        }
        for(int i=0;i<items.length();++i) {
            const auto* item=items.itemAt(i);
            const auto& indices=item->primitive()==MGeometry::kTriangles?triangles:edges;
            if(indices.empty()) continue;
#ifdef ARU_BUFFER_TIMING
            int slot=item->primitive()==MGeometry::kTriangles?0:1;
            unsigned long long hash=1469598103934665603ULL;
            for(unsigned value:indices){hash^=value;hash*=1099511628211ULL;}
            bufferSizes[slot].store(static_cast<long long>(indices.size()));bufferHashes[slot].store(static_cast<long long>(hash));
#endif
            auto* b=geometry.createIndexBuffer(MGeometry::kUnsignedInt32);
            if(!b) continue;
            void* dst=b->acquire(static_cast<unsigned>(indices.size()),true);
            if(dst) {std::memcpy(dst,indices.data(),indices.size()*sizeof(unsigned));b->commit(dst);item->associateWithIndexBuffer(b);}
        }
    }
    void cleanUp() override {}
};
}
MStatus initializePlugin(MObject obj) {
    MFnPlugin plugin(obj,"Aruurara","0.1","Any");
    MStatus status=plugin.registerNode("aruRetopoBufferPreview",PreviewNode::id,PreviewNode::creator,
        PreviewNode::initialize,MPxNode::kLocatorNode,&classification);
    if(!status) return status;
    status=MDrawRegistry::registerGeometryOverrideCreator(classification,registrant,PreviewGeometry::creator);
    if(!status) plugin.deregisterNode(PreviewNode::id);
    return status;
}
MStatus uninitializePlugin(MObject obj) {
    MStatus status=MDrawRegistry::deregisterGeometryOverrideCreator(classification,registrant);
    if(!status) return status;
    return MFnPlugin(obj).deregisterNode(PreviewNode::id);
}
