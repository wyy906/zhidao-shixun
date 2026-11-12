"""适配器注册表 —— 导出所有内置适配器"""
from app.adapters.base import register_adapter, get_adapter, list_adapters  # noqa: F401
from app.adapters.python_adapter import PythonWebAdapter  # noqa: F401
from app.adapters.mysql_adapter import MySQLWorkbenchAdapter  # noqa: F401
