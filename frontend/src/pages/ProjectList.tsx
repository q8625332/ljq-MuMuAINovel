import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Empty, Modal, message, Spin, Row, Col, Statistic, Space, Tag, Progress, Typography, Tooltip, Badge } from 'antd';
import { EditOutlined, DeleteOutlined, BookOutlined, RocketOutlined, CalendarOutlined, FileTextOutlined, TrophyOutlined, FireOutlined, SettingOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useProjectSync } from '../store/hooks';
import type { ReactNode } from 'react';
import { cardStyles, cardHoverHandlers, gridConfig } from '../components/CardStyles';
import UserMenu from '../components/UserMenu';

const { Title, Text, Paragraph } = Typography;

export default function ProjectList() {
  const navigate = useNavigate();
  const { projects, loading } = useStore();

  const { refreshProjects, deleteProject } = useProjectSync();

  useEffect(() => {
    refreshProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        refreshProjects();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = (id: string) => {
    const isMobile = window.innerWidth <= 768;
    Modal.confirm({
      title: '确认删除',
      content: '删除项目将同时删除所有相关数据，此操作不可恢复。确定要删除吗？',
      okText: '确定',
      cancelText: '取消',
      okType: 'danger',
      centered: true,
      ...(isMobile && {
        style: { top: 'auto' }
      }),
      onOk: async () => {
        try {
          await deleteProject(id);
          message.success('项目删除成功');
        } catch {
          message.error('删除项目失败');
        }
      },
    });
  };

  const handleEnterProject = (id: string) => {
    const project = projects.find(p => p.id === id);
    if (project) {
      console.log('项目信息:', {
        id: project.id,
        title: project.title,
        wizard_status: project.wizard_status,
        wizard_step: project.wizard_step
      });
      
      if (project.wizard_status === 'incomplete' || !project.wizard_status) {
        console.log('向导未完成，跳转到向导页面');
        navigate(`/wizard?projectId=${id}&step=${project.wizard_step || 0}`);
      } else {
        console.log('向导已完成，进入项目管理界面');
        navigate(`/project/${id}`);
      }
    }
  };

  const getStatusTag = (status: string) => {
    const statusConfig: Record<string, { color: string; text: string; icon: ReactNode }> = {
      planning: { color: 'blue', text: '规划中', icon: <CalendarOutlined /> },
      writing: { color: 'green', text: '创作中', icon: <EditOutlined /> },
      revising: { color: 'orange', text: '修改中', icon: <FileTextOutlined /> },
      completed: { color: 'purple', text: '已完成', icon: <TrophyOutlined /> },
    };
    const config = statusConfig[status] || statusConfig.planning;
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  const getProgress = (current: number, target: number) => {
    if (!target) return 0;
    return Math.min(Math.round((current / target) * 100), 100);
  };

  const getProgressColor = (progress: number) => {
    if (progress >= 80) return '#52c41a';
    if (progress >= 50) return '#1890ff';
    if (progress >= 20) return '#faad14';
    return '#ff4d4f';
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days}天前`;
    if (days < 30) return `${Math.floor(days / 7)}周前`;
    return date.toLocaleDateString('zh-CN');
  };

  const totalWords = projects.reduce((sum, p) => sum + (p.current_words || 0), 0);
  const activeProjects = projects.filter(p => p.status === 'writing').length;

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: window.innerWidth <= 768 ? '20px 16px' : '40px 24px'
    }}>
      <div style={{
        maxWidth: 1400,
        margin: '0 auto',
        marginBottom: window.innerWidth <= 768 ? 20 : 40
      }}>
        <Card
          variant="borderless"
          style={{
            background: 'rgba(255, 255, 255, 0.95)',
            borderRadius: window.innerWidth <= 768 ? 12 : 16,
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)',
          }}
        >
          <Row align="middle" justify="space-between" gutter={[16, 16]}>
            <Col xs={24} sm={12} md={10}>
              <Space direction="vertical" size={4}>
                <Title level={window.innerWidth <= 768 ? 3 : 2} style={{ margin: 0 }}>
                  <FireOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
                  我的创作空间
                </Title>
                <Text type="secondary" style={{ fontSize: window.innerWidth <= 768 ? 12 : 14 }}>
                  开启你的小说创作之旅
                </Text>
              </Space>
            </Col>
            <Col xs={24} sm={12} md={14} style={{ display: 'flex', justifyContent: window.innerWidth <= 768 ? 'space-between' : 'flex-end', alignItems: 'center', gap: 16 }}>
              <Button
                type="primary"
                size={window.innerWidth <= 768 ? 'middle' : 'large'}
                icon={<RocketOutlined />}
                onClick={() => navigate('/wizard')}
                style={{
                  borderRadius: 8,
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  border: 'none',
                  boxShadow: '0 2px 8px rgba(102, 126, 234, 0.4)'
                }}
              >
                向导创建
              </Button>
              <Button
                type="default"
                size={window.innerWidth <= 768 ? 'middle' : 'large'}
                icon={<SettingOutlined />}
                onClick={() => navigate('/settings')}
                style={{
                  borderRadius: 8,
                  borderColor: '#d9d9d9',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
                  transition: 'all 0.3s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#667eea';
                  e.currentTarget.style.color = '#667eea';
                  e.currentTarget.style.boxShadow = '0 2px 12px rgba(102, 126, 234, 0.3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#d9d9d9';
                  e.currentTarget.style.color = 'rgba(0, 0, 0, 0.88)';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.08)';
                }}
              >
                API设置
              </Button>
              <UserMenu />
            </Col>
          </Row>

          {projects.length > 0 && (
            <Row gutter={[16, 16]} style={{ marginTop: window.innerWidth <= 768 ? 16 : 24 }}>
              <Col xs={24} sm={8}>
                <Card variant="borderless" style={{ background: '#f0f5ff', borderRadius: 12 }}>
                  <Statistic
                    title={<span style={{ fontSize: window.innerWidth <= 768 ? 12 : 14, color: '#595959' }}>总项目数</span>}
                    value={projects.length}
                    prefix={<BookOutlined style={{ color: '#1890ff' }} />}
                    suffix="个"
                    valueStyle={{ color: '#1890ff', fontSize: window.innerWidth <= 768 ? 20 : 28, fontWeight: 'bold' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card variant="borderless" style={{ background: '#f6ffed', borderRadius: 12 }}>
                  <Statistic
                    title={<span style={{ fontSize: window.innerWidth <= 768 ? 12 : 14, color: '#595959' }}>创作中</span>}
                    value={activeProjects}
                    prefix={<EditOutlined style={{ color: '#52c41a' }} />}
                    suffix="个"
                    valueStyle={{ color: '#52c41a', fontSize: window.innerWidth <= 768 ? 20 : 28, fontWeight: 'bold' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card variant="borderless" style={{ background: '#fff7e6', borderRadius: 12 }}>
                  <Statistic
                    title={<span style={{ fontSize: window.innerWidth <= 768 ? 12 : 14, color: '#595959' }}>总字数</span>}
                    value={totalWords}
                    prefix={<FileTextOutlined style={{ color: '#faad14' }} />}
                    suffix="字"
                    valueStyle={{ color: '#faad14', fontSize: window.innerWidth <= 768 ? 20 : 28, fontWeight: 'bold' }}
                  />
                </Card>
              </Col>
            </Row>
          )}
        </Card>
      </div>

      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <Spin spinning={loading}>
          {!Array.isArray(projects) || projects.length === 0 ? (
            <Card
              variant="borderless"
              style={{
                background: 'rgba(255, 255, 255, 0.95)',
                borderRadius: 16,
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)',
              }}
            >
              <Empty
                description={
                  <Space direction="vertical" size={16}>
                    <Text style={{ fontSize: 16, color: '#8c8c8c' }}>
                      还没有项目，开始创建你的第一个小说项目吧！
                    </Text>
                    <Button
                      type="primary"
                      size="large"
                      icon={<RocketOutlined />}
                      onClick={() => navigate('/wizard')}
                    >
                      向导创建
                    </Button>
                  </Space>
                }
                style={{ padding: '80px 0' }}
              />
            </Card>
          ) : (
            <Row gutter={[16, 16]}>
              {projects.map((project) => {
                const progress = getProgress(project.current_words, project.target_words || 0);
                const isWizardComplete = project.wizard_status === 'completed';
                
                return (
                  <Col {...gridConfig} key={project.id}>
                    <Badge.Ribbon
                      text={isWizardComplete ? getStatusTag(project.status) : <Tag color="orange" icon={<RocketOutlined />}>创建中</Tag>}
                      color="transparent"
                      style={{ top: 12, right: 12 }}
                    >
                      <Card
                        hoverable
                        variant="borderless"
                        onClick={() => handleEnterProject(project.id)}
                        style={cardStyles.project}
                        styles={{ body: { padding: 0, overflow: 'hidden' } }}
                        {...cardHoverHandlers}
                      >
                        <div style={{
                          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                          padding: window.innerWidth <= 768 ? '16px' : '24px',
                          position: 'relative'
                        }}>
                          <Space direction="vertical" size={8} style={{ width: '100%' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: window.innerWidth <= 768 ? 8 : 12 }}>
                              <BookOutlined style={{ fontSize: window.innerWidth <= 768 ? 20 : 28, color: '#fff' }} />
                              <Title level={window.innerWidth <= 768 ? 5 : 4} style={{ margin: 0, color: '#fff', flex: 1 }} ellipsis>
                                {project.title}
                              </Title>
                            </div>
                            {project.genre && (
                              <Tag color="rgba(255,255,255,0.3)" style={{ color: '#fff', border: 'none' }}>
                                {project.genre}
                              </Tag>
                            )}
                          </Space>
                        </div>

                        <div style={{ padding: window.innerWidth <= 768 ? '16px' : '20px' }}>
                          <Paragraph
                            ellipsis={{ rows: 2 }}
                            style={{
                              color: 'rgba(0,0,0,0.65)',
                              minHeight: 44,
                              marginBottom: 16
                            }}
                          >
                            {project.description || '暂无描述'}
                          </Paragraph>

                          {isWizardComplete ? (
                            <>
                              {project.target_words && project.target_words > 0 && (
                                <div style={{ marginBottom: 16 }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                                    <Text type="secondary" style={{ fontSize: 12 }}>完成进度</Text>
                                    <Text strong style={{ fontSize: 12 }}>{progress}%</Text>
                                  </div>
                                  <Progress
                                    percent={progress}
                                    strokeColor={getProgressColor(progress)}
                                    showInfo={false}
                                    size={{ height: 8 }}
                                  />
                                </div>
                              )}

                              <Row gutter={12}>
                                <Col span={12}>
                                  <div style={{
                                    textAlign: 'center',
                                    padding: '12px 0',
                                    background: '#f5f5f5',
                                    borderRadius: 8
                                  }}>
                                    <div style={{ fontSize: 20, fontWeight: 'bold', color: '#1890ff' }}>
                                      {(project.current_words / 1000).toFixed(1)}K
                                    </div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>已写字数</Text>
                                  </div>
                                </Col>
                                <Col span={12}>
                                  <div style={{
                                    textAlign: 'center',
                                    padding: '12px 0',
                                    background: '#f5f5f5',
                                    borderRadius: 8
                                  }}>
                                    <div style={{ fontSize: 20, fontWeight: 'bold', color: '#52c41a' }}>
                                      {project.target_words ? (project.target_words / 1000).toFixed(0) + 'K' : '--'}
                                    </div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>目标字数</Text>
                                  </div>
                                </Col>
                              </Row>
                            </>
                          ) : (
                            <div style={{
                              textAlign: 'center',
                              padding: '24px 0',
                              background: '#f5f5f5',
                              borderRadius: 8
                            }}>
                              <RocketOutlined style={{ fontSize: 32, color: '#faad14', marginBottom: 12 }} />
                              <div style={{ color: '#faad14', fontWeight: 'bold', marginBottom: 4 }}>
                                项目创建中
                              </div>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                点击继续创建向导
                              </Text>
                            </div>
                          )}

                          <div style={{ 
                            marginTop: 16, 
                            paddingTop: 16, 
                            borderTop: '1px solid #f0f0f0',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                          }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              <CalendarOutlined style={{ marginRight: 4 }} />
                              {formatDate(project.updated_at)}
                            </Text>
                            <Space size={8}>
                              <Tooltip title="删除">
                                <Button 
                                  type="text" 
                                  size="small"
                                  danger
                                  icon={<DeleteOutlined />}
                                  onClick={(e) => { 
                                    e.stopPropagation(); 
                                    handleDelete(project.id); 
                                  }}
                                />
                              </Tooltip>
                            </Space>
                          </div>
                        </div>
                      </Card>
                    </Badge.Ribbon>
                  </Col>
                );
              })}
            </Row>
          )}
        </Spin>
      </div>
    </div>
  );
}