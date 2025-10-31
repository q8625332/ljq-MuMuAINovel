import { useState, useEffect } from 'react';
import { Dropdown, Avatar, Space, Typography, message, Modal, Table, Button, Tag, Popconfirm, Pagination } from 'antd';
import { UserOutlined, LogoutOutlined, TeamOutlined, CrownOutlined } from '@ant-design/icons';
import { authApi, userApi } from '../services/api';
import type { User } from '../types';
import type { MenuProps } from 'antd';

const { Text } = Typography;

export default function UserMenu() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showUserManagement, setShowUserManagement] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  useEffect(() => {
    loadCurrentUser();
  }, []);

  const loadCurrentUser = async () => {
    try {
      const user = await authApi.getCurrentUser();
      setCurrentUser(user);
    } catch (error) {
      console.error('获取用户信息失败:', error);
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
      // 清除JWT令牌
      localStorage.removeItem('access_token');
      message.success('已退出登录');
      window.location.href = '/login';
    } catch (error) {
      console.error('退出登录失败:', error);
      // 即使API调用失败也要清除本地令牌
      localStorage.removeItem('access_token');
      message.error('退出登录失败');
    }
  };

  const handleShowUserManagement = async () => {
    if (!currentUser?.is_admin) {
      message.warning('只有管理员可以访问用户管理');
      return;
    }

    setShowUserManagement(true);
    loadUsers();
  };

  const loadUsers = async () => {
    try {
      setLoading(true);
      const userList = await userApi.listUsers();
      setUsers(userList);
    } catch (error) {
      console.error('获取用户列表失败:', error);
      message.error('获取用户列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSetAdmin = async (userId: string, isAdmin: boolean) => {
    try {
      await userApi.setAdmin(userId, isAdmin);
      message.success(isAdmin ? '已设置为管理员' : '已取消管理员权限');
      loadUsers();
    } catch (error) {
      console.error('设置管理员失败:', error);
      message.error('设置管理员失败');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    try {
      await userApi.deleteUser(userId);
      message.success('用户已删除');
      loadUsers();
    } catch (error) {
      console.error('删除用户失败:', error);
      message.error('删除用户失败');
    }
  };

  const menuItems: MenuProps['items'] = [
    {
      key: 'user-info',
      label: (
        <div style={{ padding: '8px 0' }}>
          <Text strong>{currentUser?.display_name || currentUser?.username}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Trust Level: {currentUser?.trust_level}
            {currentUser?.is_admin && ' · 管理员'}
          </Text>
        </div>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    ...(currentUser?.is_admin ? [{
      key: 'user-management',
      icon: <TeamOutlined />,
      label: '用户管理',
      onClick: handleShowUserManagement,
    }, {
      type: 'divider' as const,
    }] : []),
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      render: (text: string, record: User) => (
        <Space>
          <Avatar src={record.avatar_url} icon={<UserOutlined />} size="small" />
          <div>
            <div>{record.display_name || text}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>{text}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Trust Level',
      dataIndex: 'trust_level',
      key: 'trust_level',
      width: 120,
      render: (level: number) => <Tag color="blue">{level}</Tag>,
    },
    {
      title: '角色',
      dataIndex: 'is_admin',
      key: 'is_admin',
      width: 100,
      render: (isAdmin: boolean) => (
        isAdmin ? <Tag color="gold" icon={<CrownOutlined />}>管理员</Tag> : <Tag>普通用户</Tag>
      ),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login',
      key: 'last_login',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: User) => {
        const isSelf = record.user_id === currentUser?.user_id;
        return (
          <Space>
            {record.is_admin ? (
              <Popconfirm
                title="确定要取消管理员权限吗？"
                onConfirm={() => handleSetAdmin(record.user_id, false)}
                disabled={isSelf}
              >
                <Button size="small" disabled={isSelf}>
                  取消管理员
                </Button>
              </Popconfirm>
            ) : (
              <Button
                size="small"
                type="primary"
                onClick={() => handleSetAdmin(record.user_id, true)}
              >
                设为管理员
              </Button>
            )}
            <Popconfirm
              title="确定要删除该用户吗？此操作不可恢复！"
              onConfirm={() => handleDeleteUser(record.user_id)}
              disabled={isSelf}
            >
              <Button size="small" danger disabled={isSelf}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  if (!currentUser) {
    return null;
  }

  return (
    <>
      <Dropdown menu={{ items: menuItems }} placement="bottomRight">
        <div
          style={{
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '8px 16px',
            background: 'rgba(255, 255, 255, 0.95)',
            backdropFilter: 'blur(10px)',
            WebkitBackdropFilter: 'blur(10px)',
            borderRadius: 24,
            border: '1px solid rgba(102, 126, 234, 0.2)',
            transition: 'all 0.3s ease',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(255, 255, 255, 1)';
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.3)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.95)';
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.1)';
          }}
        >
          <div style={{ position: 'relative' }}>
            <Avatar
              src={currentUser.avatar_url}
              icon={<UserOutlined />}
              size={40}
              style={{
                backgroundColor: '#1890ff',
                border: '3px solid #fff',
                boxShadow: '0 2px 8px rgba(102, 126, 234, 0.3)',
              }}
            />
            {currentUser.is_admin && (
              <div style={{
                position: 'absolute',
                bottom: -2,
                right: -2,
                width: 18,
                height: 18,
                background: 'linear-gradient(135deg, #ffd700 0%, #ffaa00 100%)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '2px solid white',
                boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
              }}>
                <CrownOutlined style={{ fontSize: 9, color: '#fff' }} />
              </div>
            )}
          </div>
          <Space direction="vertical" size={0} style={{ display: window.innerWidth <= 768 ? 'none' : 'flex' }}>
            <Text strong style={{
              color: '#262626',
              fontSize: 14,
              lineHeight: '20px',
            }}>
              {currentUser.display_name || currentUser.username}
            </Text>
            <Text style={{
              color: '#8c8c8c',
              fontSize: 12,
              lineHeight: '18px',
            }}>
              {currentUser.is_admin ? '👑 管理员' : `🎖️ Trust Level ${currentUser.trust_level}`}
            </Text>
          </Space>
        </div>
      </Dropdown>

      <Modal
        title="用户管理"
        open={showUserManagement}
        onCancel={() => setShowUserManagement(false)}
        footer={null}
        width={900}
        centered
        styles={{
          body: {
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 200px)',
          }
        }}
      >
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
        }}>
          <div style={{
            flex: 1,
            overflow: 'hidden',
            padding: '0 12px',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <Table
              columns={columns}
              dataSource={users.slice((currentPage - 1) * pageSize, currentPage * pageSize)}
              rowKey="user_id"
              loading={loading}
              pagination={false}
              scroll={{ x: 800, y: 'calc(100vh - 340px)' }}
              sticky
            />
          </div>
          <div style={{
            padding: '16px 24px',
            borderTop: '1px solid #f0f0f0',
            background: '#fff',
            display: 'flex',
            justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={users.length}
              showSizeChanger
              showTotal={(total) => `共 ${total} 个用户`}
              pageSizeOptions={['10', '20', '50', '100']}
              onChange={(page, newPageSize) => {
                setCurrentPage(page);
                setPageSize(newPageSize);
              }}
            />
          </div>
        </div>
      </Modal>
    </>
  );
}