import pkgutil
import importlib
import inspect

from zhenxun.configs.utils import AbstractTool

tools_registry: dict[str, AbstractTool] = {}

for module_info in pkgutil.iter_modules(__path__):
    module_name = module_info.name
    module = importlib.import_module(f'.{module_name}', package=__name__)
    
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, AbstractTool) and obj is not AbstractTool:
            instance = obj()
            if instance.name and instance.description:
                tools_registry[instance.name] = instance