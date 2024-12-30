import json
import os
from typing import Dict, Any, Optional
import logging
import time
import glob

logger = logging.getLogger(__name__)

class StaticDataManager:
    _instance = None
    _data_cache = {}
    _file_mtimes = {}  # 存储文件最后修改时间
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StaticDataManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.static_path = os.path.join("app", "static")
        # 初始化时预加载所有JSON文件
        self._load_all_json_files()
        
    def _load_all_json_files(self):
        """加载static目录下的所有JSON文件"""
        json_pattern = os.path.join(self.static_path, "**", "*.json")
        json_files = glob.glob(json_pattern, recursive=True)
        for file_path in json_files:
            relative_path = os.path.relpath(file_path, self.static_path)
            self._load_json_file(relative_path)
            
    def _should_reload(self, file_path: str, file_name: str) -> bool:
        """检查文件是否需要重新加载"""
        try:
            current_mtime = os.path.getmtime(file_path)
            last_mtime = self._file_mtimes.get(file_name)
            
            if last_mtime is None or current_mtime > last_mtime:
                self._file_mtimes[file_name] = current_mtime
                return True
            return False
        except OSError:
            return True
            
    def _load_json_file(self, file_name: str) -> Dict[str, Any]:
        """加载JSON文件"""
        file_path = os.path.join(self.static_path, file_name)
        
        # 如果文件在缓存中且未被修改，直接返回缓存数据
        if file_name in self._data_cache and not self._should_reload(file_path, file_name):
            return self._data_cache[file_name]
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                try:
                    data = json.loads(content)
                    self._data_cache[file_name] = data
                    logger.info(f"已重新加载静态文件: {file_name}")
                    return data
                except json.JSONDecodeError as je:
                    # 获取错误上下文
                    error_context = content[max(0, je.pos - 50):min(len(content), je.pos + 50)]
                    logger.error(f"JSON解析错误 {file_name}:")
                    logger.error(f"错误位置: 行 {je.lineno}, 列 {je.colno}")
                    logger.error(f"错误信息: {str(je)}")
                    logger.error(f"错误上下文: ...{error_context}...")
                    return self._data_cache.get(file_name, {})  # 如果解析失败，返回旧的缓存数据
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            return {}
        except Exception as e:
            logger.error(f"加载静态文件失败 {file_name}: {str(e)}")
            return self._data_cache.get(file_name, {})  # 如果加载失败，返回旧的缓存数据
            
    def get_data(self, file_name: str, key: Optional[str] = None) -> Any:
        """
        通用的获取数据方法
        :param file_name: JSON文件名（相对于static目录）
        :param key: 可选的键名，如果提供则返回对应的值
        :return: 请求的数据
        """
        data = self._load_json_file(file_name)
        if key is not None:
            return data.get(str(key))
        return data
            
    def get_item_data(self, item_id: int) -> Optional[Dict[str, Any]]:
        """获取物品数据"""
        return self.get_data("item.json", str(item_id))
        
    def get_all_items(self) -> Dict[str, Any]:
        """获取所有物品数据"""
        return self.get_data("item.json")
        
    def reload_all(self):
        """重新加载所有静态数据"""
        self._data_cache.clear()
        self._file_mtimes.clear()
        self._load_all_json_files()
        
static_data = StaticDataManager() 