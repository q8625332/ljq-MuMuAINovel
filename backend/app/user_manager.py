"""
用户管理模块 - 支持 LinuxDO OAuth2
"""
import json
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel
from app.config import settings, DATA_DIR


class User(BaseModel):
    """用户模型"""
    user_id: str  # 格式: linuxdo_{linuxdo_id}
    username: str
    display_name: str
    avatar_url: Optional[str] = None
    trust_level: int = 0  # 仅用于显示
    is_admin: bool = False  # 手动设置的管理员权限
    linuxdo_id: str  # LinuxDO 用户 ID
    created_at: str
    last_login: str


class UserManager:
    """用户管理器 - 线程安全版本"""
    
    USERS_FILE = str(DATA_DIR / "users.json")
    ADMINS_FILE = str(DATA_DIR / "admins.json")
    
    def __init__(self):
        """初始化用户管理器"""
        # DATA_DIR 已在 config.py 中创建，无需重复创建
        # 添加文件锁保护并发读写
        self._users_lock = asyncio.Lock()
        self._admins_lock = asyncio.Lock()
        # 添加内存缓存
        self._users_cache: Optional[Dict[str, dict]] = None
        self._admin_cache: Optional[List[str]] = None
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """确保必要的文件存在"""
        if not os.path.exists(self.USERS_FILE):
            with open(self.USERS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
        
        if not os.path.exists(self.ADMINS_FILE):
            with open(self.ADMINS_FILE, "w", encoding="utf-8") as f:
                json.dump({"admins": []}, f, ensure_ascii=False, indent=2)
    
    def _load_users_unsafe(self) -> Dict[str, dict]:
        """加载用户数据（不加锁，内部使用）"""
        try:
            with open(self.USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载用户数据失败: {e}")
            return {}
    
    def _save_users_unsafe(self, users: Dict[str, dict]):
        """保存用户数据（不加锁，内部使用）"""
        try:
            with open(self.USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
                # 强制刷新缓冲区，确保数据立即写入磁盘
                f.flush()
                os.fsync(f.fileno())
            # 立即更新内存缓存
            self._users_cache = users.copy()
        except Exception as e:
            print(f"保存用户数据失败: {e}")
    
    async def _load_users(self) -> Dict[str, dict]:
        """加载用户数据（加锁）"""
        async with self._users_lock:
            return self._load_users_unsafe()
    
    async def _save_users(self, users: Dict[str, dict]):
        """保存用户数据（加锁）"""
        async with self._users_lock:
            self._save_users_unsafe(users)
    
    def _load_admin_list_unsafe(self) -> List[str]:
        """加载管理员列表（不加锁，内部使用）"""
        try:
            with open(self.ADMINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admins", [])
        except Exception as e:
            print(f"加载管理员列表失败: {e}")
            return []
    
    def _save_admin_list_unsafe(self, admin_list: List[str]):
        """保存管理员列表（不加锁，内部使用）"""
        try:
            with open(self.ADMINS_FILE, "w", encoding="utf-8") as f:
                json.dump({"admins": admin_list}, f, ensure_ascii=False, indent=2)
                # 强制刷新缓冲区
                f.flush()
                os.fsync(f.fileno())
            # 立即更新内存缓存
            self._admin_cache = admin_list.copy()
        except Exception as e:
            print(f"保存管理员列表失败: {e}")
    
    async def _load_admin_list(self) -> List[str]:
        """加载管理员列表（加锁）"""
        async with self._admins_lock:
            return self._load_admin_list_unsafe()
    
    async def _save_admin_list(self, admin_list: List[str]):
        """保存管理员列表（加锁）"""
        async with self._admins_lock:
            self._save_admin_list_unsafe(admin_list)
    
    async def create_or_update_from_linuxdo(
        self,
        linuxdo_id: str,
        username: str,
        display_name: str,
        avatar_url: Optional[str],
        trust_level: int
    ) -> User:
        """
        从 LinuxDO 用户信息创建或更新用户（线程安全）
        
        Args:
            linuxdo_id: LinuxDO 用户 ID（本地用户时为 local_xxx 格式）
            username: 用户名
            display_name: 显示名称
            avatar_url: 头像 URL
            trust_level: 信任等级 (仅用于显示)
            
        Returns:
            用户对象
        """
        # 如果已经是 local_ 开头，直接使用；否则添加 linuxdo_ 前缀
        if linuxdo_id.startswith("local_"):
            user_id = linuxdo_id
        else:
            user_id = f"linuxdo_{linuxdo_id}"
        
        # 使用锁保护整个读-改-写操作
        async with self._users_lock:
            async with self._admins_lock:
                users = self._load_users_unsafe()
                admin_list = self._load_admin_list_unsafe()
                
                now = datetime.now().isoformat()
                
                # 检查是否为初始管理员
                initial_admin_id = settings.INITIAL_ADMIN_LINUXDO_ID
                is_initial_admin = (initial_admin_id and linuxdo_id == initial_admin_id)
                
                # 检查是否为本地用户（所有 local_ 开头的用户默认为管理员）
                is_local_user = user_id.startswith("local_")
                
                if user_id in users:
                    # 更新现有用户
                    user_data = users[user_id]
                    user_data["username"] = username
                    user_data["display_name"] = display_name
                    user_data["avatar_url"] = avatar_url
                    user_data["trust_level"] = trust_level
                    user_data["last_login"] = now
                    
                    # 如果是初始管理员或本地用户且还不在管理员列表中，添加进去
                    if (is_initial_admin or is_local_user) and user_id not in admin_list:
                        admin_list.append(user_id)
                        self._save_admin_list_unsafe(admin_list)
                        user_data["is_admin"] = True
                    else:
                        # 从管理员列表同步 is_admin 状态
                        user_data["is_admin"] = user_id in admin_list
                else:
                    # 创建新用户（本地用户默认为管理员）
                    is_admin = is_initial_admin or is_local_user
                    if is_admin and user_id not in admin_list:
                        admin_list.append(user_id)
                        self._save_admin_list_unsafe(admin_list)
                    
                    user_data = {
                        "user_id": user_id,
                        "username": username,
                        "display_name": display_name,
                        "avatar_url": avatar_url,
                        "trust_level": trust_level,
                        "is_admin": is_admin,
                        "linuxdo_id": linuxdo_id,
                        "created_at": now,
                        "last_login": now
                    }
                    users[user_id] = user_data
                
                self._save_users_unsafe(users)
                return User(**user_data)
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """获取用户（线程安全，优先从缓存读取）"""
        async with self._users_lock:
            # 优先从缓存读取
            if self._users_cache is not None:
                users = self._users_cache
            else:
                users = self._load_users_unsafe()
                self._users_cache = users.copy()
        
        user_data = users.get(user_id)
        if user_data:
            # 同步管理员状态（也使用缓存）
            async with self._admins_lock:
                if self._admin_cache is not None:
                    admin_list = self._admin_cache
                else:
                    admin_list = self._load_admin_list_unsafe()
                    self._admin_cache = admin_list.copy()
            
            # 创建副本避免修改缓存
            user_data = user_data.copy()
            user_data["is_admin"] = user_id in admin_list
            return User(**user_data)
        return None
    
    async def get_all_users(self) -> List[User]:
        """获取所有用户（线程安全）"""
        users = await self._load_users()
        admin_list = await self._load_admin_list()
        
        user_list = []
        for user_data in users.values():
            # 同步管理员状态
            user_data["is_admin"] = user_data["user_id"] in admin_list
            user_list.append(User(**user_data))
        
        return user_list
    
    async def set_admin(self, user_id: str, is_admin: bool) -> bool:
        """
        设置用户的管理员权限（线程安全）
        
        Args:
            user_id: 用户 ID
            is_admin: 是否为管理员
            
        Returns:
            是否成功
        """
        # 使用锁保护整个读-改-写操作
        async with self._users_lock:
            async with self._admins_lock:
                users = self._load_users_unsafe()
                if user_id not in users:
                    return False
                
                admin_list = self._load_admin_list_unsafe()
                
                if is_admin:
                    # 授予管理员权限
                    if user_id not in admin_list:
                        admin_list.append(user_id)
                        self._save_admin_list_unsafe(admin_list)
                else:
                    # 撤销管理员权限
                    if user_id in admin_list:
                        # 确保至少保留一个管理员
                        if len(admin_list) <= 1:
                            return False
                        admin_list.remove(user_id)
                        self._save_admin_list_unsafe(admin_list)
                
                # 更新用户数据中的 is_admin 字段
                users[user_id]["is_admin"] = is_admin
                self._save_users_unsafe(users)
                
                return True
    
    async def delete_user(self, user_id: str) -> bool:
        """
        删除用户（线程安全）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否成功
        """
        # 使用锁保护整个读-改-写操作
        async with self._users_lock:
            async with self._admins_lock:
                users = self._load_users_unsafe()
                if user_id not in users:
                    return False
                
                # 不能删除管理员
                admin_list = self._load_admin_list_unsafe()
                if user_id in admin_list:
                    return False
                
                # 删除用户数据
                del users[user_id]
                self._save_users_unsafe(users)
        
        # 删除用户数据库文件（在锁外执行，避免阻塞）
        db_file = str(DATA_DIR / f"ai_story_user_{user_id}.db")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception as e:
                print(f"删除用户数据库文件失败: {e}")
        
        return True
    
    async def is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员（线程安全）"""
        admin_list = await self._load_admin_list()
        return user_id in admin_list


# 全局用户管理器实例
user_manager = UserManager()