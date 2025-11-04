# 数据导出导入功能修复说明

## 问题描述

1. **JSON导出缺少API配置数据**：导出的JSON文件中只包含`settings`表，但缺少`api_configs`表的数据
2. **导入不支持SQLite数据库文件**：只支持JSON格式导入，不支持直接导入.db文件

## 修复内容

### 1. 添加ApiConfig表的导出支持

**修改文件**：`backend/app/api/data_export.py`

#### 变更点：

1. **导入ApiConfig模型**（第20行）
   ```python
   from app.models import (
       ...,
       ApiConfig  # 新增
   )
   ```

2. **导出ApiConfig数据**（第80行）
   ```python
   api_configs = await self.export_table_data(ApiConfig)
   ```

3. **添加到导出数据中**（第108行）
   ```python
   "data": {
       ...,
       "api_configs": api_configs,  # 新增
   }
   ```

4. **更新元数据统计**（第95行）
   ```python
   "metadata": {
       ...,
       "total_api_configs": len(api_configs),  # 新增
   }
   ```

5. **导入统计中添加api_configs**（第128行）
   ```python
   self.import_stats = {
       ...,
       "api_configs": 0  # 新增
   }
   ```

6. **导入时处理api_configs表**（第190行）
   ```python
   tables_to_import = [
       ...,
       ("api_configs", ApiConfig),  # 新增
   ]
   ```

7. **清空数据时包含ApiConfig**（第217行）
   ```python
   tables_to_clear = [
       ...,
       ApiConfig,  # 新增
   ]
   ```

8. **导出信息统计中添加api_configs**（第332、361行）
   ```python
   api_configs = await db.execute(select(ApiConfig))
   api_configs_count = len(api_configs.scalars().all())
   ```

### 2. 添加SQLite数据库文件导入导出支持

**修改文件**：
- `backend/app/api/data_export.py`
- `backend/app/database.py`

#### 变更点：

1. **添加必要的导入**（第1-8行）
   ```python
   import shutil
   import os
   from pathlib import Path
   from fastapi.responses import FileResponse
   ```

2. **添加get_db_path函数**（`database.py`第36-45行）
   ```python
   def get_db_path(user_id: str) -> str:
       """获取用户数据库文件路径"""
       return f"data/ai_story_user_{user_id}.db"
   ```

3. **导出API支持format参数**（第226行）
   ```python
   @router.get("/export-data")
   async def export_user_data(
       format: str = Query("json", description="导出格式: json 或 db"),
       ...
   ):
   ```

4. **SQLite文件导出逻辑**（第235-245行）
   ```python
   if format == "db":
       db_path = get_db_path(user_id)
       return FileResponse(
           path=db_path,
           filename=filename,
           media_type="application/x-sqlite3"
       )
   ```

5. **导入API支持SQLite文件**（第262行）
   ```python
   @router.post("/import-data")
   async def import_user_data(
       file: UploadFile = File(..., description="导入的备份文件 (JSON或SQLite)"),
       ...
   ):
   ```

6. **自动检测文件类型**（第274-276行）
   ```python
   if file.filename.endswith('.db') or content[:16] == b'SQLite format 3\x00':
       # SQLite数据库文件导入
   ```

7. **SQLite导入逻辑**（第277-293行）
   - 自动备份现有数据库（非替换模式）
   - 直接覆盖数据库文件
   - 支持替换模式

## 使用方法

### 导出数据

#### JSON格式（默认）
```bash
GET /api/export-data?format=json
# 或
GET /api/export-data
```

#### SQLite数据库文件
```bash
GET /api/export-data?format=db
```

### 导入数据

#### JSON格式
```bash
POST /api/import-data
Content-Type: multipart/form-data

file: mumuai_backup.json
replace: false  # 追加模式（默认）或 true（替换模式）
```

#### SQLite数据库文件
```bash
POST /api/import-data
Content-Type: multipart/form-data

file: mumuai_backup.db
replace: false  # 是否备份现有数据库
```

## 数据完整性

修复后，导出的JSON文件将包含以下所有表的数据：

1. ✅ `projects` - 项目
2. ✅ `relationship_types` - 关系类型
3. ✅ `characters` - 角色
4. ✅ `chapters` - 章节
5. ✅ `outlines` - 大纲
6. ✅ `generation_history` - 生成历史
7. ✅ `character_relationships` - 角色关系
8. ✅ `organizations` - 组织
9. ✅ `organization_members` - 组织成员
10. ✅ `settings` - 设置（旧版API配置）
11. ✅ **`api_configs` - API配置（新增）**

## 测试建议

1. **测试JSON导出**
   - 验证导出的JSON包含`api_configs`字段
   - 验证`metadata.total_api_configs`统计正确

2. **测试JSON导入**
   - 导入包含`api_configs`的JSON文件
   - 验证API配置正确恢复

3. **测试SQLite导出**
   - 导出.db文件
   - 使用SQLite工具验证文件完整性

4. **测试SQLite导入**
   - 导入.db文件（追加模式）
   - 导入.db文件（替换模式）
   - 验证自动备份功能

## 注意事项

1. **SQLite导入会直接覆盖数据库文件**，建议在非替换模式下会自动创建备份
2. **API配置包含敏感信息**（API密钥），导出时请妥善保管
3. **版本兼容性**：当前导出版本为`2.0.0`，只支持相同版本的导入
4. **文件大小**：SQLite文件通常比JSON文件小，导出速度更快

## 部署说明

修改后需要重新部署后端服务：

```bash
# Docker部署
docker-compose down
docker-compose up -d --build

# 或使用无缓存构建
docker-compose build --no-cache
docker-compose up -d