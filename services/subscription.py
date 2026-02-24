import copy
import json
import os
import threading
from typing import Dict, List, Optional

from astrbot.api import logger


class SubscriptionManager:
    """
    UP主订阅管理器，使用 JSON 文件持久化存储

    数据结构:
    {
        "subscriptions": {
            "unified_msg_origin_xxx": {
                "up_list": [
                    {"mid": "12345", "name": "UP主名", "last_bvid": "BVxxx"}
                ]
            }
        }
    }
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.data_file = os.path.join(data_dir, "subscriptions.json")
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载订阅数据失败: {e}")
        return {"subscriptions": {}}

    def _save(self):
        with self._lock:
            try:
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存订阅数据失败: {e}")

    def add_subscription(self, origin: str, mid: str, name: str) -> bool:
        """
        添加订阅

        :return: True=新增成功, False=已存在
        """
        subs = self._data["subscriptions"]
        if origin not in subs:
            subs[origin] = {"up_list": []}

        for up in subs[origin]["up_list"]:
            if up["mid"] == mid:
                return False

        subs[origin]["up_list"].append({
            "mid": mid,
            "name": name,
            "last_bvid": ""
        })
        self._save()
        return True

    def remove_subscription(self, origin: str, mid: str) -> bool:
        """
        取消订阅

        :return: True=删除成功, False=不存在
        """
        subs = self._data["subscriptions"]
        if origin not in subs:
            return False

        original_len = len(subs[origin]["up_list"])
        subs[origin]["up_list"] = [
            up for up in subs[origin]["up_list"] if up["mid"] != mid
        ]

        if len(subs[origin]["up_list"]) == original_len:
            return False

        if not subs[origin]["up_list"]:
            del subs[origin]

        self._save()
        return True

    def get_subscriptions(self, origin: str) -> List[Dict]:
        """获取某会话的订阅列表"""
        subs = self._data["subscriptions"]
        if origin not in subs:
            return []
        return copy.deepcopy(subs[origin]["up_list"])

    def get_subscription_count(self, origin: str) -> int:
        """获取某会话的订阅数量"""
        return len(self.get_subscriptions(origin))

    def get_all_subscriptions(self) -> Dict[str, List[Dict]]:
        """
        获取所有会话的订阅（定时检查用）

        :return: {origin: [up_dict, ...]}
        """
        result = {}
        for origin, data in self._data["subscriptions"].items():
            result[origin] = copy.deepcopy(data["up_list"])
        return result

    def update_last_video(self, origin: str, mid: str, bvid: str):
        """更新某UP主已推送的最新视频BVID"""
        subs = self._data["subscriptions"]
        if origin not in subs:
            return

        for up in subs[origin]["up_list"]:
            if up["mid"] == mid:
                up["last_bvid"] = bvid
                break

        self._save()

    # ==================== 推送目标管理 ====================

    def add_push_target(self, origin: str, label: str = "") -> bool:
        """
        添加推送目标

        :param origin: unified_msg_origin
        :param label: 友好名称（如群号或QQ号）
        :return: True=新增, False=已存在
        """
        targets = self._data.setdefault("push_targets", [])
        for t in targets:
            if t["origin"] == origin:
                return False
        targets.append({"origin": origin, "label": label})
        self._save()
        return True

    def remove_push_target(self, target_id: str) -> bool:
        """
        移除推送目标（按 label 或 origin 匹配）

        :return: True=删除成功, False=不存在
        """
        targets = self._data.get("push_targets", [])
        original_len = len(targets)
        self._data["push_targets"] = [
            t for t in targets
            if t["label"] != target_id and t["origin"] != target_id
        ]
        if len(self._data["push_targets"]) == original_len:
            return False
        self._save()
        return True

    def get_push_targets(self) -> List[Dict]:
        """获取所有推送目标"""
        return self._data.get("push_targets", [])

    def get_push_origins(self) -> List[str]:
        """获取所有推送目标的 origin 列表"""
        return [t["origin"] for t in self._data.get("push_targets", [])]

