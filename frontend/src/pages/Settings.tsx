import { useNavigate } from 'react-router-dom';
import { Card, Button, Space, Typography, Alert } from 'antd';
import { SettingOutlined, ArrowLeftOutlined, DatabaseOutlined } from '@ant-design/icons';
import ApiConfigManager from '../components/ApiConfigManager';

const { Title, Paragraph } = Typography;

export default function SettingsPage() {
  const navigate = useNavigate();

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: window.innerWidth <= 768 ? '20px 16px' : '40px 24px'
    }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <Card
          variant="borderless"
          style={{
            background: 'rgba(255, 255, 255, 0.95)',
            borderRadius: window.innerWidth <= 768 ? 12 : 16,
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)',
          }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* 标题栏 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Space>
                <Button
                  icon={<ArrowLeftOutlined />}
                  onClick={() => navigate('/')}
                  type="text"
                />
                <Title level={window.innerWidth <= 768 ? 3 : 2} style={{ margin: 0 }}>
                  <SettingOutlined style={{ marginRight: 8, color: '#667eea' }} />
                  设置
                </Title>
              </Space>
            </div>

            <Paragraph type="secondary" style={{ marginBottom: 16 }}>
              配置你的AI API接口参数，支持管理多个配置并设置默认配置。这些设置将用于小说生成、角色创建等AI功能。
            </Paragraph>

            {/* 数据管理入口 */}
            <Alert
              message="数据备份与恢复"
              description={
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                  <span>导出或导入你的全部数据，保护数据安全，方便版本迁移。</span>
                  <Button
                    type="primary"
                    icon={<DatabaseOutlined />}
                    onClick={() => navigate('/data-management')}
                    style={{
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      border: 'none'
                    }}
                  >
                    数据管理
                  </Button>
                </div>
              }
              type="info"
              showIcon
              icon={<DatabaseOutlined />}
              style={{ marginBottom: 24 }}
            />

            {/* API配置管理 */}
            <ApiConfigManager />
          </Space>
        </Card>
      </div>
    </div>
  );
}