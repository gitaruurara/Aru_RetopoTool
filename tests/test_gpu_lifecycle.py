"""Renderer ownership regression; GPU rendering is tested separately in Maya."""
import gc
import pathlib
import types
import unittest
import weakref

class Operation:
    def __init__(self,*args):pass
    def clearOperation(self):return self
    def setOverridesColors(self,*args):pass

class Lifecycle(unittest.TestCase):
    def test_reload_keeps_original_owner_and_disable_deregisters_it(self):
        registry={};panels={'panel':'previousRenderer'}
        def register(obj):
            self.assertNotIn(obj.NAME,registry)
            registry[obj.NAME]=weakref.ref(obj)
        def deregister(obj):
            keys=[key for key,value in registry.items() if value() is obj]
            self.assertEqual(len(keys),1)
            del registry[keys[0]]
        def editor(panel,**kwargs):
            if kwargs.get('q'):return panels[panel]
            self.assertIsNotNone(registry[kwargs['rendererOverrideName']]()) if kwargs['rendererOverrideName']!='previousRenderer' else None
            panels[panel]=kwargs['rendererOverrideName']
        cmds=types.SimpleNamespace(modelEditor=editor,ls=lambda **kwargs:[],refresh=lambda **kwargs:None,
                                   modelPanel=lambda *args,**kwargs:True)
        render=types.SimpleNamespace(MSceneRender=Operation,MRenderOverride=Operation,MHUDRender=Operation,
                                    MPresentTarget=Operation,MRenderer=types.SimpleNamespace(registerOverride=register,deregisterOverride=deregister))
        source=(pathlib.Path(__file__).parents[1]/'gpu_preview.py').read_text(encoding='utf-8')
        source=chr(10).join(line for line in source.splitlines() if not line.startswith(('from maya import','import maya.api.','from . import')))
        scope={'cmds':cmds,'om':types.SimpleNamespace(MSelectionList=list),'render':render}
        for i in range(20):
            exec(compile(source,'gpu_preview.py','exec'),scope)
            scope['enable']('panel')
            owner=weakref.ref(scope['_override']);registered=scope['_registered_name']
            exec(compile(source,'gpu_preview.py','exec'),scope)
            scope['Preview'].NAME='changedOnReload'
            gc.collect();self.assertIsNotNone(owner())
            scope['enable']('panel');self.assertEqual(panels['panel'],registered)
            scope['disable']();gc.collect()
            self.assertIsNone(owner());self.assertEqual(registry,{})
            self.assertEqual(panels['panel'],'previousRenderer')

if __name__=='__main__':unittest.main()
