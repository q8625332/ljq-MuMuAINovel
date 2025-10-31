# JWT认证升级指南

## 📝 变更说明

已将Cookie认证升级为JWT（JSON Web Token）认证，解决跨IP访问和HTTP环境下的Cookie问题。

## 🔧 主要变更

### 后端变更

1. **新增依赖** (`backend/requirements.txt`)
   - `python-jose[cryptography]==3.3.0` - JWT处理
   - `passlib[bcrypt]==1.7.4` - 密码加密（预留）

2. **新增文件**
   - `backend/app/utils/jwt_handler.py` - JWT工具类

3. **修改文件**
   - `backend/app/middleware/auth_middleware.py` - 支持JWT和Cookie双认证
   - `backend/app/api/auth.py` - 登录API返回JWT令牌

### 前端变更

1. **修改文件**
   - `frontend/src/services/api.ts` - 自动添加JWT令牌到请求头
   - `frontend/src/pages/Login.tsx` - 保存JWT令牌到localStorage
   - `frontend/src/components/UserMenu.tsx` - 退出时清除JWT令牌

## 🚀 部署步骤

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 重新构建前端

```bash
cd frontend
npm install
npm run build
```

### 3. 重启服务

```bash
# 开发环境
cd backend
python -m app.main

# 生产环境（Docker）
docker-compose down
docker-compose up -d --build
```

## 🧪 测试步骤

### 1. 清除旧数据

在浏览器开发者工具中：
- 清除所有Cookie（Application → Cookies）
- 清除localStorage（Application → Local Storage）

### 2. 测试登录

1. 访问登录页面
2. 使用配置的账号密码登录
3. 登录成功后检查：
   - localStorage中应该有 `access_token`
   - 控制台显示：`JWT令牌已保存到localStorage`

### 3. 验证认证

1. 刷新页面，应该保持登录状态
2. 访问其他页面，应该能正常访问
3. 检查后端日志，应该显示：`通过JWT验证用户: local_xxx`

### 4. 测试退出

1. 点击退出登录
2. localStorage中的 `access_token` 应该被清除
3. 自动跳转到登录页面

## 🔍 问题排查

### 登录后仍然401

1. **检查localStorage**
   ```javascript
   // 在浏览器控制台执行
   console.log(localStorage.getItem('access_token'));
   ```
   应该输出JWT令牌字符串

2. **检查请求头**
   在开发者工具的Network标签中，查看API请求：
   - Headers应该包含：`Authorization: Bearer eyJ...`

3. **检查后端日志**
   ```
   # 成功的日志
   DEBUG: 通过JWT验证用户: local_21232f297a57a5a7
   
   # 失败的日志
   WARNING: JWT令牌验证失败: ...
   ```

### JWT令牌过期

- 默认有效期：7天
- 过期后需要重新登录
- 可以在 `backend/app/utils/jwt_handler.py` 中修改 `ACCESS_TOKEN_EXPIRE_DAYS`

## 📊 认证流程

### 登录流程

```
用户输入账号密码
    ↓
POST /api/auth/local/login
    ↓
后端验证账号密码
    ↓
生成JWT令牌
    ↓
返回：{ access_token, user }
    ↓
前端保存到localStorage
```

### 请求认证流程

```
前端发起API请求
    ↓
axios拦截器添加 Authorization 头
    ↓
后端AuthMiddleware验证JWT
    ↓
提取user_id并注入request.state
    ↓
API处理请求
```

## 🔐 安全建议

1. **生产环境配置**
   - 在 `.env` 中设置强密码作为JWT密钥
   - 使用HTTPS（JWT令牌在localStorage中相对安全）

2. **令牌刷新**
   - 当前实现：7天过期后需重新登录
   - 未来可实现：refresh token机制

3. **跨域配置**
   - JWT方式支持跨域访问
   - 确保CORS配置正确

## ✅ 优势

相比Cookie方案：

✅ **解决跨IP访问问题** - 令牌存储在localStorage，不受域名限制  
✅ **HTTP环境友好** - 不需要secure属性  
✅ **更灵活** - 可以在请求头中自由携带  
✅ **无状态** - 后端不需要session存储  
✅ **跨域友好** - 适合微服务架构

## 📝 配置说明

### JWT密钥配置

在 `backend/.env` 中：
```env
# JWT会使用LOCAL_AUTH_PASSWORD作为密钥
LOCAL_AUTH_PASSWORD=your-strong-password-here
```

如果未配置，将使用默认密钥（不建议用于生产环境）。

## 🔄 向后兼容

当前实现**同时支持JWT和Cookie**两种方式：
- 优先使用JWT（从Authorization头）
- 如果没有JWT，回退到Cookie
- 登录时同时设置JWT和Cookie

这样可以平滑迁移，不影响现有用户。