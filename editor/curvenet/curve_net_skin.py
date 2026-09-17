"""
RetopoGuide SkinCluster -- EP weight to handle auto-propagation
=============================================================
"""

from __future__ import annotations

import maya.OpenMaya as om1
import maya.OpenMayaMPx as ompx


class RetopoGuideSkinCluster(ompx.MPxSkinCluster):
    """Handle vertices auto-inherit parent EP weights via custom skinCluster.

    Standard LBS, but handle vertices use their parent EP's weights
    so that EP and handle always receive the same blend transform matrix.
    """

    kNodeId = om1.MTypeId(0x00131AD3)
    kNodeName = "retopoGuideSkinCluster"

    # epMap[vtx_index] = parent_ep_index  (-1 = use own weights = EP)
    aEPMap = om1.MObject()
    # oppositeEpMap[handle_vtx] = opposite_ep_index
    aOppositeEpMap = om1.MObject()

    @staticmethod
    def creator():
        return ompx.asMPxPtr(RetopoGuideSkinCluster())

    @staticmethod
    def initialize():
        nAttr = om1.MFnNumericAttribute()
        RetopoGuideSkinCluster.aEPMap = nAttr.create(
            "epMap", "epm", om1.MFnNumericData.kInt, -1)
        nAttr.setArray(True)
        nAttr.setUsesArrayDataBuilder(True)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideSkinCluster.addAttribute(RetopoGuideSkinCluster.aEPMap)

        RetopoGuideSkinCluster.aOppositeEpMap = nAttr.create(
            "oppositeEpMap", "oepm", om1.MFnNumericData.kInt, -1)
        nAttr.setArray(True)
        nAttr.setUsesArrayDataBuilder(True)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideSkinCluster.addAttribute(RetopoGuideSkinCluster.aOppositeEpMap)

    # ------------------------------------------------------------------
    def deform(self, block, geomIter, localToWorldMatrix, multiIndex):
        fn = om1.MFnDependencyNode(self.thisMObject())

        # ---- envelope ------------------------------------------------
        envelope = block.inputValue(fn.attribute("envelope")).asFloat()
        if envelope < 1e-6:
            return

        # ---- influence world matrices --------------------------------
        matrixAttr = fn.attribute("matrix")
        transformsHandle = block.inputArrayValue(matrixAttr)
        numTransforms = transformsHandle.elementCount()
        if numTransforms == 0:
            return

        transforms = []
        transformIndices = []
        for i in range(numTransforms):
            logIdx = transformsHandle.elementIndex()
            transforms.append(
                om1.MFnMatrixData(
                    transformsHandle.inputValue().data()).matrix())
            transformIndices.append(logIdx)
            if i < numTransforms - 1:
                transformsHandle.next()

        # ---- bind pre-matrices: final = bindPre * world --------------
        bindAttr = fn.attribute("bindPreMatrix")
        bindHandle = block.inputArrayValue(bindAttr)
        for i, logIdx in enumerate(transformIndices):
            try:
                bindHandle.jumpToElement(logIdx)
                bpm = om1.MFnMatrixData(
                    bindHandle.inputValue().data()).matrix()
                transforms[i] = bpm * transforms[i]
            except Exception:
                pass

        # ---- EP map (handle_vtx -> parent_ep_vtx) --------------------
        epMap = {}
        try:
            epMapHandle = block.inputArrayValue(RetopoGuideSkinCluster.aEPMap)
        except RuntimeError:
            epMapHandle = None
        cnt = epMapHandle.elementCount() if epMapHandle is not None else 0
        for i in range(cnt):
            logical = epMapHandle.elementIndex()
            val = epMapHandle.inputValue().asInt()
            if val >= 0:
                epMap[logical] = val
            if i < cnt - 1:
                epMapHandle.next()

        # ---- pre-cache all vertex weights ----------------------------
        weightListAttr = fn.attribute("weightList")
        weightsAttr = fn.attribute("weights")
        weightListHandle = block.inputArrayValue(weightListAttr)
        weightCache = {}  # vtx_idx -> {transform_logical_idx: weight}
        wlCount = weightListHandle.elementCount()
        for i in range(wlCount):
            vtxIdx = weightListHandle.elementIndex()
            wl_input = weightListHandle.inputValue()
            w_child = wl_input.child(weightsAttr)
            wh = om1.MArrayDataHandle(w_child)
            wDict = {}
            whCount = wh.elementCount()
            for j in range(whCount):
                tidx = wh.elementIndex()
                wDict[tidx] = wh.inputValue().asDouble()
                if j < whCount - 1:
                    wh.next()
            weightCache[vtxIdx] = wDict
            if i < wlCount - 1:
                weightListHandle.next()

        # ---- LBS deformation ----------------------------------------
        geomIter.reset()
        while not geomIter.isDone():
            pt = geomIter.position()
            vtxIdx = geomIter.index()

            srcIdx = epMap.get(vtxIdx, vtxIdx)
            wDict = weightCache.get(srcIdx, {})

            if not wDict:
                geomIter.next()
                continue

            # ---- standard LBS for all vertices (EP + handle) ----
            # ハンドルは epMap により親 EP のウェイトを使用するため、
            # EP と同一のジョイントブレンド行列で変形される。
            sx, sy, sz = 0.0, 0.0, 0.0
            wTotal = 0.0
            for i, logIdx in enumerate(transformIndices):
                w = wDict.get(logIdx, 0.0)
                if abs(w) > 1e-10:
                    tp = pt * transforms[i]
                    sx += tp.x * w
                    sy += tp.y * w
                    sz += tp.z * w
                    wTotal += w

            if wTotal < 1e-10:
                geomIter.next()
                continue

            if abs(wTotal - 1.0) > 1e-6:
                sx += pt.x * (1.0 - wTotal)
                sy += pt.y * (1.0 - wTotal)
                sz += pt.z * (1.0 - wTotal)

            fx = pt.x + (sx - pt.x) * envelope
            fy = pt.y + (sy - pt.y) * envelope
            fz = pt.z + (sz - pt.z) * envelope
            geomIter.setPosition(om1.MPoint(fx, fy, fz))
            geomIter.next()
