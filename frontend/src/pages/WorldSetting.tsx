import { Card, Descriptions, Empty, Typography } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { cardStyles } from '../components/CardStyles';

const { Title, Paragraph } = Typography;

export default function WorldSetting() {
  const { currentProject } = useStore();

  if (!currentProject) return null;

  // 检查是否有世界设定信息
  const hasWorldSetting = currentProject.world_time_period ||
    currentProject.world_location ||
    currentProject.world_atmosphere ||
    currentProject.world_rules;

  if (!hasWorldSetting) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* 固定头部 */}
        <div style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          backgroundColor: '#fff',
          padding: '16px 0',
          marginBottom: 16,
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center'
        }}>
          <GlobalOutlined style={{ fontSize: 24, marginRight: 12, color: '#1890ff' }} />
          <h2 style={{ margin: 0 }}>世界设定</h2>
        </div>
        
        {/* 可滚动内容区域 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <Empty
            description="暂无世界设定信息"
            style={{ marginTop: 60 }}
          >
            <Paragraph type="secondary">
              世界设定信息在创建项目向导中生成，用于构建小说的世界观背景。
            </Paragraph>
          </Empty>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 固定头部 */}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: '#fff',
        padding: '16px 0',
        marginBottom: 24,
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        alignItems: 'center'
      }}>
        <GlobalOutlined style={{ fontSize: 24, marginRight: 12, color: '#1890ff' }} />
        <h2 style={{ margin: 0 }}>世界设定</h2>
      </div>

      {/* 可滚动内容区域 */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <Card
        style={{
          ...cardStyles.base,
          marginBottom: 16
        }}
        title={
          <span style={{ fontSize: 18, fontWeight: 500 }}>
            基础信息
          </span>
        }
      >
        <Descriptions bordered column={1} styles={{ label: { width: 120, fontWeight: 500 } }}>
          <Descriptions.Item label="小说名称">{currentProject.title}</Descriptions.Item>
          {currentProject.description && (
            <Descriptions.Item label="小说简介">{currentProject.description}</Descriptions.Item>
          )}
          <Descriptions.Item label="小说主题">{currentProject.theme || '未设定'}</Descriptions.Item>
          <Descriptions.Item label="小说类型">{currentProject.genre || '未设定'}</Descriptions.Item>
          <Descriptions.Item label="叙事视角">{currentProject.narrative_perspective || '未设定'}</Descriptions.Item>
          <Descriptions.Item label="目标字数">
            {currentProject.target_words ? `${currentProject.target_words.toLocaleString()} 字` : '未设定'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        style={{
          ...cardStyles.base,
          marginBottom: 16
        }}
        title={
          <span style={{ fontSize: 18, fontWeight: 500 }}>
            <GlobalOutlined style={{ marginRight: 8 }} />
            小说世界观
          </span>
        }
      >
        <div style={{ padding: '16px 0' }}>
          {currentProject.world_time_period && (
            <div style={{ marginBottom: 24 }}>
              <Title level={5} style={{ color: '#1890ff', marginBottom: 12 }}>
                时间设定
              </Title>
              <Paragraph style={{ 
                fontSize: 15, 
                lineHeight: 1.8,
                padding: 16,
                background: '#f5f5f5',
                borderRadius: 8,
                borderLeft: '4px solid #1890ff'
              }}>
                {currentProject.world_time_period}
              </Paragraph>
            </div>
          )}

          {currentProject.world_location && (
            <div style={{ marginBottom: 24 }}>
              <Title level={5} style={{ color: '#52c41a', marginBottom: 12 }}>
                地点设定
              </Title>
              <Paragraph style={{
                fontSize: 15,
                lineHeight: 1.8,
                padding: 16,
                background: '#f5f5f5',
                borderRadius: 8,
                borderLeft: '4px solid #52c41a'
              }}>
                {currentProject.world_location}
              </Paragraph>
            </div>
          )}

          {currentProject.world_atmosphere && (
            <div style={{ marginBottom: 24 }}>
              <Title level={5} style={{ color: '#faad14', marginBottom: 12 }}>
                氛围设定
              </Title>
              <Paragraph style={{
                fontSize: 15,
                lineHeight: 1.8,
                padding: 16,
                background: '#f5f5f5',
                borderRadius: 8,
                borderLeft: '4px solid #faad14'
              }}>
                {currentProject.world_atmosphere}
              </Paragraph>
            </div>
          )}

          {currentProject.world_rules && (
            <div style={{ marginBottom: 0 }}>
              <Title level={5} style={{ color: '#f5222d', marginBottom: 12 }}>
                规则设定
              </Title>
              <Paragraph style={{
                fontSize: 15,
                lineHeight: 1.8,
                padding: 16,
                background: '#f5f5f5',
                borderRadius: 8,
                borderLeft: '4px solid #f5222d'
              }}>
                {currentProject.world_rules}
              </Paragraph>
            </div>
          )}
        </div>
      </Card>
      </div>
    </div>
  );
}