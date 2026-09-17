// Experimental native mesh transfer. No scene mutations during compute.
#include <maya/MPxNode.h>
#include <maya/MFnPlugin.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnMatrixAttribute.h>
#include <maya/MMatrix.h>
#include <maya/MFnDoubleArrayData.h>
#include <maya/MFnIntArrayData.h>
#include <maya/MFnMeshData.h>
#include <maya/MFnMesh.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MPointArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MIntArray.h>
#include <maya/MPlug.h>
#include <maya/MEvaluationNode.h>
#include <maya/MDGContext.h>
#include <vector>
#include <cmath>
#include <chrono>
#include <cstring>
#ifdef ARU_RETOPO_GPU_COMPUTE
#include "gpu_backend.h"
#endif

extern "C" void* aru_surface_create(const double*,int,const int*,int);
extern "C" void aru_surface_destroy(void*);
extern "C" int aru_stencil(const double*,const int*,const int*,const double*,int,double*);
extern "C" int aru_stencil_rows(const double*,const int*,const int*,const double*,const int*,int,double*);
extern "C" int aru_relax(void*,double*,int,const int*,const int*,const double*,int,double,int*,int);

class MeshBuffer final : public MPxNode {
public:
    static MTypeId id;
    static MObject positions, counts, indices, output, pointOutput, statusOutput, timings, offsets, controls, weights;
    static MObject guideMatrix, reference, projectEnabled, adjacency, neighbors, guideWeights, iterations, strength, guard;
    ~MeshBuffer() override { if(surface)aru_surface_destroy(surface); }
    static void* creator() { return new MeshBuffer; }
    SchedulingType schedulingType() const override { return kSerial; }
    MStatus setDependentsDirty(const MPlug& plug,MPlugArray&) override {
        auto attr=plug.attribute();
        if(attr==offsets || attr==controls || attr==weights)stencilDirty=true;
#ifdef ARU_RETOPO_INPUT_CACHE
        if(attr==reference)referenceDirty=true;
        if(attr==adjacency || attr==neighbors || attr==guideWeights)adjacencyDirty=true;
#endif
        return MS::kSuccess;
    }
    MStatus preEvaluation(const MDGContext&,const MEvaluationNode& node) override {
        if(node.dirtyPlugExists(offsets) || node.dirtyPlugExists(controls) || node.dirtyPlugExists(weights))stencilDirty=true;
#ifdef ARU_RETOPO_INPUT_CACHE
        if(node.dirtyPlugExists(reference))referenceDirty=true;
        if(node.dirtyPlugExists(adjacency)||node.dirtyPlugExists(neighbors)||node.dirtyPlugExists(guideWeights))adjacencyDirty=true;
#endif
        return MS::kSuccess;
    }
    static MStatus initialize() {
        MFnTypedAttribute a;
        positions=a.create("positions","pos",MFnData::kDoubleArray); addAttribute(positions);
        counts=a.create("faceCounts","fc",MFnData::kIntArray); addAttribute(counts);
        indices=a.create("faceIndices","fi",MFnData::kIntArray); addAttribute(indices);
        offsets=a.create("stencilOffsets","so",MFnData::kIntArray);addAttribute(offsets);
        controls=a.create("stencilIndices","si",MFnData::kIntArray);addAttribute(controls);
        weights=a.create("stencilWeights","sw",MFnData::kDoubleArray);addAttribute(weights);
        MFnMatrixAttribute matrixAttribute;
        guideMatrix=matrixAttribute.create("guideMatrix","gm");addAttribute(guideMatrix);
        reference=a.create("referenceMesh","rm",MFnData::kMesh);addAttribute(reference);
        adjacency=a.create("adjacencyOffsets","ao",MFnData::kIntArray);addAttribute(adjacency);
        neighbors=a.create("adjacencyIndices","ai",MFnData::kIntArray);addAttribute(neighbors);
        guideWeights=a.create("guideWeights","gw",MFnData::kDoubleArray);addAttribute(guideWeights);
        MFnNumericAttribute numeric;
        projectEnabled=numeric.create("projectToReference","pr",MFnNumericData::kBoolean,false);addAttribute(projectEnabled);
        iterations=numeric.create("relaxIterations","ri",MFnNumericData::kInt,3);numeric.setMin(0);numeric.setMax(30);addAttribute(iterations);
        strength=numeric.create("relaxStrength","rs",MFnNumericData::kDouble,.35);numeric.setMin(0.);numeric.setMax(1.);addAttribute(strength);
        guard=numeric.create("projectionGuard","pg",MFnNumericData::kBoolean,true);addAttribute(guard);
        output=a.create("outMesh","om",MFnData::kMesh);
        a.setWritable(false);a.setStorable(false);addAttribute(output);
        pointOutput=a.create("outPositions","op",MFnData::kDoubleArray);a.setWritable(false);a.setStorable(false);addAttribute(pointOutput);
        statusOutput=a.create("status","st",MFnData::kString);a.setWritable(false);a.setStorable(false);addAttribute(statusOutput);
        timings=a.create("computeMilliseconds","cms",MFnData::kDoubleArray);a.setWritable(false);a.setStorable(false);a.setHidden(true);addAttribute(timings);
        for(auto attr:{positions,counts,indices,offsets,controls,weights,guideMatrix,reference,projectEnabled,adjacency,neighbors,guideWeights,iterations,strength,guard}){attributeAffects(attr,output);attributeAffects(attr,pointOutput);attributeAffects(attr,statusOutput);attributeAffects(attr,timings);}
        return MS::kSuccess;
    }
    MStatus compute(const MPlug& plug,MDataBlock& block) override {
        if(plug.attribute()!=output && plug.attribute()!=pointOutput && plug.attribute()!=statusOutput && plug.attribute()!=timings)return MS::kUnknownParameter;
        using Clock=std::chrono::steady_clock;
        auto checkpoint=Clock::now();MDoubleArray elapsed;
        auto stamp=[&](){auto now=Clock::now();elapsed.append(std::chrono::duration<double,std::milli>(now-checkpoint).count());checkpoint=now;};
        MFnMeshData dataFn;MObject result=dataFn.create();
        const char* statusMessage="ERROR: Invalid native mesh input";
        MDoubleArray xyz;
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
        std::vector<double> coordinateBuffer;
#endif
        const bool wantsMesh=plug.attribute()==output;
        auto finish=[&](){
            if(wantsMesh){auto handle=block.outputValue(output);handle.setMObject(result);handle.setClean();}
            MFnDoubleArrayData pointData;auto pointHandle=block.outputValue(pointOutput);
            pointHandle.setMObject(pointData.create(xyz));pointHandle.setClean();
            auto text=block.outputValue(statusOutput);text.setString(statusMessage);text.setClean();
            stamp();MFnDoubleArrayData timingData;auto timingHandle=block.outputValue(timings);
            timingHandle.setMObject(timingData.create(elapsed));timingHandle.setClean();return MS::kSuccess;
        };
        MStatus status;
        MIntArray fc,fi;
        std::vector<int> faceCountsNow,faceIndicesNow;
        MString cachedStatus;
        if(block.isClean(pointOutput)){
            MFnDoubleArrayData values(block.outputValue(pointOutput).data(),&status);
            if(!status)return finish();
            xyz.copy(values.array());
            cachedStatus=block.outputValue(statusOutput).asString();statusMessage=cachedStatus.asChar();
            MFnIntArrayData countsData(block.inputValue(counts).data(),&status);if(!status)return finish();
            fc=countsData.array();
            MFnIntArrayData indicesData(block.inputValue(indices).data(),&status);if(!status)return finish();
            fi=indicesData.array();
            faceCountsNow.resize(fc.length());faceIndicesNow.resize(fi.length());
            fc.get(faceCountsNow.data());fi.get(faceIndicesNow.data());
        }else{
            auto evaluateCoordinates=[&]()->bool{
        MFnIntArrayData cfn(block.inputValue(counts).data(),&status);if(!status)return false;
        fc=cfn.array();
        if(!fc.length()){statusMessage="0 patches";return false;}
        MFnDoubleArrayData pfn(block.inputValue(positions).data(),&status);if(!status)return false;
        xyz.copy(pfn.array()); // MFn data arrays can share backing storage.
        if(xyz.length()%3)return false;
        std::vector<double> inputCheck(xyz.length());xyz.get(inputCheck.data());
        for(double value:inputCheck)if(!std::isfinite(value))return false;
        MMatrix matrix=block.inputValue(guideMatrix).asMatrix();
        if(matrix!=MMatrix::identity){
            for(size_t i=0;i<inputCheck.size();i+=3){
                MPoint q=MPoint(inputCheck[i],inputCheck[i+1],inputCheck[i+2])*matrix;
                if(!std::isfinite(q.x)||!std::isfinite(q.y)||!std::isfinite(q.z))return false;
                inputCheck[i]=q.x;inputCheck[i+1]=q.y;inputCheck[i+2]=q.z;
            }
            xyz=MDoubleArray(inputCheck.data(),unsigned(inputCheck.size()));
        }
        // Optional compiled guide stencil: transfer controls, not generated vertices.
        const bool normalContext=block.context().isNormal();
        if(stencilDirty || !normalContext || cachedControlCount!=xyz.length()/3){
            stencilDirty=true; // Leave invalid inputs dirty so recovery always revalidates.
#ifdef ARU_RETOPO_INCREMENTAL_STENCIL
            stencilValuesValid=false;
#endif
            MObject offsetData=block.inputValue(offsets).data();
            stencilRows.clear();stencilColumns.clear();stencilCoefficients.clear();
            if(!offsetData.isNull()){
                MFnIntArrayData ofn(offsetData,&status);if(!status)return false;
                MIntArray off=ofn.array();
                if(off.length()){
                    MFnIntArrayData idfn(block.inputValue(controls).data(),&status);if(!status)return false;
                    MFnDoubleArrayData wfn(block.inputValue(weights).data(),&status);if(!status)return false;
                    MIntArray ids=idfn.array();MDoubleArray w=wfn.array();
                    stencilRows.resize(off.length());stencilColumns.resize(ids.length());stencilCoefficients.resize(w.length());
                    off.get(stencilRows.data());ids.get(stencilColumns.data());w.get(stencilCoefficients.data());
                    if(stencilRows.size()<2 || stencilRows.front()!=0 || stencilColumns.size()!=stencilCoefficients.size() || stencilRows.back()!=int(stencilColumns.size()))return false;
                    for(size_t i=0;i<stencilColumns.size();++i)
                        if(stencilColumns[i]<0 || unsigned(stencilColumns[i])>=xyz.length()/3 || !std::isfinite(stencilCoefficients[i]))return false;
                    for(size_t i=1;i<stencilRows.size();++i)if(stencilRows[i]<stencilRows[i-1])return false;
                }
            }
            cachedControlCount=xyz.length()/3;stencilDirty=!normalContext;
        }
        if(!stencilRows.empty()){
#ifdef ARU_RETOPO_INCREMENTAL_STENCIL
            if(!normalContext)stencilValuesValid=false;
            auto& refined=stencilValues;const int rows=int(stencilRows.size()-1);
            if(!stencilValuesValid){
                refined.resize(size_t(rows)*3);controlRows.assign(cachedControlCount,{});
                for(int row=0;row<rows;++row)for(int j=stencilRows[row];j<stencilRows[row+1];++j)controlRows[stencilColumns[j]].push_back(row);
                if(!aru_stencil(inputCheck.data(),stencilRows.data(),stencilColumns.data(),stencilCoefficients.data(),rows,refined.data()))return false;
            }else{
                std::vector<unsigned char> changedRows(rows,0);std::vector<int> dirtyRows;
                for(unsigned cv=0;cv<cachedControlCount;++cv){
                    if(std::memcmp(inputCheck.data()+3*cv,previousControls.data()+3*cv,3*sizeof(double))==0)continue;
                    for(int row:controlRows[cv])if(!changedRows[row]){changedRows[row]=1;dirtyRows.push_back(row);}
                }
                if(dirtyRows.size()>size_t(rows/2)){
                    if(!aru_stencil(inputCheck.data(),stencilRows.data(),stencilColumns.data(),stencilCoefficients.data(),rows,refined.data())){stencilValuesValid=false;return false;}
                }else if(!aru_stencil_rows(inputCheck.data(),stencilRows.data(),stencilColumns.data(),stencilCoefficients.data(),dirtyRows.data(),int(dirtyRows.size()),refined.data())){stencilValuesValid=false;return false;}
            }
            previousControls=inputCheck;stencilValuesValid=normalContext;
#else
            std::vector<double> refined((stencilRows.size()-1)*3);
            if(!aru_stencil(inputCheck.data(),stencilRows.data(),stencilColumns.data(),stencilCoefficients.data(),int(stencilRows.size()-1),refined.data()))return false;
#endif
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
            coordinateBuffer=refined;
#else
            xyz=MDoubleArray(refined.data(),unsigned(refined.size()));
#endif
        }
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
        if(stencilRows.empty())coordinateBuffer=std::move(inputCheck);
#endif
        stamp(); // input transfer, validation and stencil
        MFnIntArrayData ifn(block.inputValue(indices).data(),&status);if(!status)return false;
        fi=ifn.array();
        if(!fc.length()){statusMessage="0 patches";return false;}
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
        if(coordinateBuffer.size()%3 || coordinateBuffer.empty())return false;
        unsigned n=unsigned(coordinateBuffer.size()/3);size_t total=0;
#else
        if(xyz.length()%3 || !xyz.length())return false;
        unsigned n=xyz.length()/3;size_t total=0;
#endif
        faceCountsNow.resize(fc.length());faceIndicesNow.resize(fi.length());
        fc.get(faceCountsNow.data());fi.get(faceIndicesNow.data());
        for(int count:faceCountsNow){if(count<3)return false;total+=count;}
        if(total!=faceIndicesNow.size())return false;
        for(int index:faceIndicesNow)if(index<0 || unsigned(index)>=n)return false;
        stamp(); // topology validation
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
        if(block.inputValue(projectEnabled).asBool() && !project(coordinateBuffer,block))return false;
#else
        if(block.inputValue(projectEnabled).asBool() && !project(xyz,block))return false;
#endif
        stamp(); // reference projection and relaxation
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
                for(double value:coordinateBuffer)if(!std::isfinite(value))return false;
                xyz=MDoubleArray(coordinateBuffer.data(),unsigned(coordinateBuffer.size()));
#else
                std::vector<double> check(xyz.length());xyz.get(check.data());
                for(double value:check)if(!std::isfinite(value))return false;
#endif
                statusMessage="Native coordinates ready";return true;
            };
            if(!evaluateCoordinates()){xyz.clear();return finish();}
        }
        if(!wantsMesh || !xyz.length())return finish();
        unsigned n=xyz.length()/3;
        std::vector<double> meshCoordinates(xyz.length());xyz.get(meshCoordinates.data());
        MPointArray points;points.setLength(n);
        for(unsigned i=0;i<n;++i){
            double x=meshCoordinates[3*i],y=meshCoordinates[3*i+1],z=meshCoordinates[3*i+2];
            if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))return finish();
            points[i]=MPoint(x,y,z);
        }
        bool changed=n!=vertices || faceCountsNow!=oldCounts || faceIndicesNow!=oldIndices;
        if(changed || mesh.isNull()){
            MFnMeshData temp;MObject storage=temp.create();MFnMesh fn;
            MObject candidate=fn.create(int(n),int(fc.length()),points,fc,fi,storage,&status);
            if(!status)return finish();
            templateData=storage;mesh=candidate;vertices=n;
            oldCounts=std::move(faceCountsNow);oldIndices=std::move(faceIndicesNow);
        }
        MFnMesh fn;fn.copy(mesh,result,&status);if(!status)return finish();
        status=fn.setPoints(points);if(!status)return status;
        statusMessage="Native mesh ready";return finish();
    }
private:
#ifdef ARU_RETOPO_NUMERIC_PIPELINE
    bool project(std::vector<double>& coordinates,MDataBlock& block){
        const unsigned coordinateCount=unsigned(coordinates.size());
#else
    bool project(MDoubleArray& xyz,MDataBlock& block){
        const unsigned coordinateCount=xyz.length();
#endif
        MStatus status;
#ifdef ARU_RETOPO_INPUT_CACHE
        const bool normalContext=block.context().isNormal();
        if(referenceDirty || !normalContext || !surface){
        referenceDirty=true;
#endif
        auto handle=block.inputValue(reference);
        MObject ref=handle.asMesh();
        if(ref.isNull() || !ref.hasFn(MFn::kMesh))return false;
        ref=handle.asMeshTransformed();MFnMesh fn(ref,&status);if(!status)return false;
        MPointArray points;if(!fn.getPoints(points) || points.length()<3)return false;
        MIntArray triangleCounts,tri;if(!fn.getTriangles(triangleCounts,tri) || tri.length()%3)return false;
        std::vector<double> verticesNow(points.length()*3);
        for(unsigned i=0;i<points.length();++i){
            const auto& p=points[i];if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z))return false;
            verticesNow[3*i]=p.x;verticesNow[3*i+1]=p.y;verticesNow[3*i+2]=p.z;
        }
        std::vector<int> trianglesNow(tri.length());tri.get(trianglesNow.data());
        if(!surface || verticesNow!=referencePoints || trianglesNow!=referenceTriangles){
            void* next=aru_surface_create(verticesNow.data(),int(points.length()),trianglesNow.data(),int(tri.length()/3));
            if(!next)return false;
            if(trianglesNow!=referenceTriangles)seeds.clear();
            if(surface)aru_surface_destroy(surface);
            #ifdef ARU_RETOPO_GPU_COMPUTE
            gpuBackend.reset();
#endif
            surface=next;referencePoints=std::move(verticesNow);referenceTriangles=std::move(trianglesNow);
        }
#ifdef ARU_RETOPO_INPUT_CACHE
        referenceDirty=!normalContext;
        }
        unsigned n=coordinateCount/3;
        auto& off=cachedAdjacency;auto& adj=cachedNeighbors;auto& anchors=cachedAnchors;
        if(adjacencyDirty || !normalContext || cachedVertexCount!=n){
        adjacencyDirty=true;
#else
        unsigned n=coordinateCount/3;
#endif
        MFnIntArrayData afn(block.inputValue(adjacency).data(),&status);if(!status)return false;
        MFnIntArrayData nfn(block.inputValue(neighbors).data(),&status);if(!status)return false;
        MFnDoubleArrayData wfn(block.inputValue(guideWeights).data(),&status);if(!status)return false;
        MIntArray a=afn.array(),ids=nfn.array();MDoubleArray w=wfn.array();
        if(a.length()!=n+1 || w.length()!=n)return false;
#ifdef ARU_RETOPO_INPUT_CACHE
        off.resize(a.length());adj.resize(ids.length());anchors.resize(n);
#else
        std::vector<int> off(a.length()),adj(ids.length());std::vector<double> anchors(n);
#endif
        a.get(off.data());ids.get(adj.data());w.get(anchors.data());
        if(off.front()!=0 || off.back()!=int(adj.size()))return false;
        for(size_t i=1;i<off.size();++i)if(off[i]<off[i-1])return false;
        for(int index:adj)if(index<0 || unsigned(index)>=n)return false;
        for(double anchor:anchors)if(!std::isfinite(anchor) || anchor<0. || anchor>1.)return false;
#ifdef ARU_RETOPO_INPUT_CACHE
        cachedVertexCount=n;adjacencyDirty=!normalContext;
        }
#endif
#ifndef ARU_RETOPO_NUMERIC_PIPELINE
        std::vector<double> coordinates(xyz.length());xyz.get(coordinates.data());
#endif
        int steps=block.inputValue(iterations).asInt();double amount=block.inputValue(strength).asDouble();
        if(steps<0 || steps>30 || !std::isfinite(amount) || amount<0. || amount>1.)return false;
        if(seeds.size()!=n)seeds.assign(n,-1);
        bool gpuDone=false;
#ifdef ARU_RETOPO_GPU_COMPUTE
        gpuDone=gpuBackend.run(referencePoints,referenceTriangles,coordinates,off,adj,anchors,steps,amount,seeds,block.inputValue(guard).asBool()?1:0);
#endif
        if(!gpuDone && !aru_relax(surface,coordinates.data(),int(n),off.data(),adj.data(),anchors.data(),steps,amount,seeds.data(),block.inputValue(guard).asBool()?1:0))return false;
#ifndef ARU_RETOPO_NUMERIC_PIPELINE
        xyz=MDoubleArray(coordinates.data(),unsigned(coordinates.size()));
#endif
        return true;
    }
#ifdef ARU_RETOPO_INPUT_CACHE
    bool referenceDirty=true,adjacencyDirty=true;
    unsigned cachedVertexCount=0;
    std::vector<int> cachedAdjacency,cachedNeighbors;
    std::vector<double> cachedAnchors;
#endif
#ifdef ARU_RETOPO_INCREMENTAL_STENCIL
    bool stencilValuesValid=false;
    std::vector<double> previousControls,stencilValues;
    std::vector<std::vector<int>> controlRows;
#endif
    bool stencilDirty=true;
    unsigned cachedControlCount=0;
    std::vector<int> stencilRows,stencilColumns;
    std::vector<double> stencilCoefficients;
    void* surface=nullptr;
#ifdef ARU_RETOPO_GPU_COMPUTE
    GPUBackend gpuBackend;
#endif
    std::vector<double> referencePoints;
    std::vector<int> referenceTriangles,seeds;
    MObject templateData,mesh;unsigned vertices=0;
    std::vector<int> oldCounts,oldIndices;
};
MTypeId MeshBuffer::id(0x00131AD5); // local development ID
MObject MeshBuffer::positions,MeshBuffer::counts,MeshBuffer::indices,MeshBuffer::output,MeshBuffer::pointOutput,MeshBuffer::statusOutput,MeshBuffer::timings,MeshBuffer::offsets,MeshBuffer::controls,MeshBuffer::weights;
MObject MeshBuffer::guideMatrix,MeshBuffer::reference,MeshBuffer::projectEnabled,MeshBuffer::adjacency,MeshBuffer::neighbors,MeshBuffer::guideWeights,MeshBuffer::iterations,MeshBuffer::strength,MeshBuffer::guard;
MStatus initializePlugin(MObject obj){
    MFnPlugin plugin(obj,"Aru","0.1.0","Any");
    return plugin.registerNode("aruRetopoMeshBuffer",MeshBuffer::id,MeshBuffer::creator,MeshBuffer::initialize);
}
MStatus uninitializePlugin(MObject obj){
    MFnPlugin plugin(obj);return plugin.deregisterNode(MeshBuffer::id);
}
