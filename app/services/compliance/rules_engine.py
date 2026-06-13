"""
合规规则引擎
------------
YAML 配置驱动，支持热更新和版本管理。
所有合规模块（数据边界、注入检测、PII脱敏、输出审核）均从此获取规则。
"""
import yaml
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


class RulesEngine:
    """
    合规规则引擎
    - 从 YAML 文件加载规则
    - 检测文件 hash 变更，自动热加载
    - 记录规则版本号，审计时可追溯
    """

    def __init__(self, rules_dir: str = None):
        if rules_dir is None:
            rules_dir = Path(__file__).parent / "rules"
        self.rules_dir = Path(rules_dir)
        self.rules_dir.mkdir(exist_ok=True)

        self._rules: Dict[str, Any] = {}
        self._version: str = "0.0.0"
        self._last_hash: str = ""
        self._lock = threading.Lock()

        self._load_rules()

    def _load_rules(self) -> None:
        """加载所有 YAML 规则文件，检测 hash 变更自动热更新"""
        yaml_files = list(self.rules_dir.glob("*.yaml")) + list(self.rules_dir.glob("*.yml"))
        if not yaml_files:
            self._rules = {}
            return

        combined = {}
        for yaml_file in yaml_files:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                combined.update(data)

        content = yaml.dump(combined, sort_keys=True)
        new_hash = hashlib.sha256(content.encode()).hexdigest()

        with self._lock:
            if new_hash != self._last_hash:
                self._rules = combined
                self._version = combined.get("version", datetime.now().strftime("%Y%m%d%H%M%S"))
                self._last_hash = new_hash

    def get_rules(self, category: str) -> Dict[str, Any]:
        """获取指定类别的规则，每次查询时自动检测热更新"""
        self._load_rules()
        return self._rules.get(category, {})

    def get_patterns(self, category: str) -> List[Dict[str, str]]:
        """获取指定类别的模式列表（用于正则匹配）"""
        rules = self.get_rules(category)
        return rules.get("patterns", [])

    def get_keywords(self, category: str) -> List[str]:
        """获取指定类别的关键词列表"""
        rules = self.get_rules(category)
        return rules.get("keywords", [])

    def get_version(self) -> str:
        """获取当前规则版本号"""
        return self._version

    def get_all_rules(self) -> Dict[str, Any]:
        """获取全部规则（用于调试）"""
        self._load_rules()
        return self._rules


# 全局单例，供所有护栏节点使用
rules_engine = RulesEngine()