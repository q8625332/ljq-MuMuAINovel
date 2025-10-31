import { useState, useEffect, useRef } from 'react';
import { List, Button, Modal, Form, Input, Select, message, Empty, Space, Badge, Tag, Card, Tooltip } from 'antd';
import { EditOutlined, FileTextOutlined, ThunderboltOutlined, LockOutlined, DownloadOutlined, SettingOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useChapterSync } from '../store/hooks';
import { projectApi } from '../services/api';
import type { Chapter, ChapterUpdate, ApiError } from '../types';
import { cardStyles } from '../components/CardStyles';

const { TextArea } = Input;

export default function Chapters() {
  const { currentProject, chapters, setCurrentChapter, setCurrentProject } = useStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [isContinuing, setIsContinuing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [editorForm] = Form.useForm();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const contentTextAreaRef = useRef<any>(null);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const {
    refreshChapters,
    updateChapter,
    generateChapterContentStream
  } = useChapterSync();

  useEffect(() => {
    if (currentProject?.id) {
      refreshChapters();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProject?.id]);

  if (!currentProject) return null;

  const canGenerateChapter = (chapter: Chapter): boolean => {
    if (chapter.chapter_number === 1) {
      return true;
    }
    
    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    );
    
    return previousChapters.every(c => c.content && c.content.trim() !== '');
  };

  const getGenerateDisabledReason = (chapter: Chapter): string => {
    if (chapter.chapter_number === 1) {
      return '';
    }
    
    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    );
    
    const incompleteChapters = previousChapters.filter(
      c => !c.content || c.content.trim() === ''
    );
    
    if (incompleteChapters.length > 0) {
      const numbers = incompleteChapters.map(c => c.chapter_number).join('、');
      return `需要先完成前置章节：第 ${numbers} 章`;
    }
    
    return '';
  };

  const handleOpenModal = (id: string) => {
    const chapter = chapters.find(c => c.id === id);
    if (chapter) {
      form.setFieldsValue(chapter);
      setEditingId(id);
      setIsModalOpen(true);
    }
  };

  const handleSubmit = async (values: ChapterUpdate) => {
    if (!editingId) return;
    
    try {
      await updateChapter(editingId, values);
      message.success('章节更新成功');
      setIsModalOpen(false);
      form.resetFields();
    } catch {
      message.error('操作失败');
    }
  };

  const handleOpenEditor = (id: string) => {
    const chapter = chapters.find(c => c.id === id);
    if (chapter) {
      setCurrentChapter(chapter);
      editorForm.setFieldsValue({
        title: chapter.title,
        content: chapter.content,
      });
      setEditingId(id);
      setIsEditorOpen(true);
    }
  };

  const handleEditorSubmit = async (values: ChapterUpdate) => {
    if (!editingId || !currentProject) return;
    
    try {
      await updateChapter(editingId, values);
      
      // 刷新项目信息以更新总字数统计
      const updatedProject = await projectApi.getProject(currentProject.id);
      setCurrentProject(updatedProject);
      
      message.success('章节保存成功');
      setIsEditorOpen(false);
    } catch {
      message.error('保存失败');
    }
  };

  const handleGenerate = async () => {
    if (!editingId) return;

    try {
      setIsContinuing(true);
      setIsGenerating(true);
      
      await generateChapterContentStream(editingId, (content) => {
        editorForm.setFieldsValue({ content });
        
        if (contentTextAreaRef.current) {
          const textArea = contentTextAreaRef.current.resizableTextArea?.textArea;
          if (textArea) {
            textArea.scrollTop = textArea.scrollHeight;
          }
        }
      });
      
      message.success('AI创作成功');
    } catch (error) {
      const apiError = error as ApiError;
      message.error('AI创作失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
    } finally {
      setIsContinuing(false);
      setIsGenerating(false);
    }
  };

  const showGenerateModal = (chapter: Chapter) => {
    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    ).sort((a, b) => a.chapter_number - b.chapter_number);

    const modal = Modal.confirm({
      title: 'AI创作章节内容',
      width: 700,
      centered: true,
      content: (
        <div style={{ marginTop: 16 }}>
          <p>AI将根据以下信息创作本章内容：</p>
          <ul>
            <li>章节大纲和要求</li>
            <li>项目的世界观设定</li>
            <li>相关角色信息</li>
            <li><strong>前面已完成章节的内容（确保剧情连贯）</strong></li>
          </ul>
          
          {previousChapters.length > 0 && (
            <div style={{
              marginTop: 16,
              padding: 12,
              background: '#f0f5ff',
              borderRadius: 4,
              border: '1px solid #adc6ff'
            }}>
              <div style={{ marginBottom: 8, fontWeight: 500, color: '#1890ff' }}>
                📚 将引用的前置章节（共{previousChapters.length}章）：
              </div>
              <div style={{ maxHeight: 150, overflowY: 'auto' }}>
                {previousChapters.map(ch => (
                  <div key={ch.id} style={{ padding: '4px 0', fontSize: 13 }}>
                    ✓ 第{ch.chapter_number}章：{ch.title} ({ch.word_count || 0}字)
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
                💡 AI会参考这些章节内容，确保情节连贯、角色状态一致
              </div>
            </div>
          )}
          
          <p style={{ color: '#ff4d4f', marginTop: 16, marginBottom: 0 }}>
            ⚠️ 注意：此操作将覆盖当前章节内容
          </p>
        </div>
      ),
      okText: '开始创作',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        modal.update({
          okButtonProps: { danger: true, loading: true },
          cancelButtonProps: { disabled: true },
          closable: false,
          maskClosable: false,
          keyboard: false,
        });
        
        try {
          await handleGenerate();
          modal.destroy();
        } catch (error) {
          modal.update({
            okButtonProps: { danger: true, loading: false },
            cancelButtonProps: { disabled: false },
            closable: true,
            maskClosable: true,
            keyboard: true,
          });
        }
      },
      onCancel: () => {
        if (isGenerating) {
          message.warning('AI正在创作中，请等待完成');
          return false;
        }
      },
    });
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      'draft': 'default',
      'writing': 'processing',
      'completed': 'success',
    };
    return colors[status] || 'default';
  };

  const getStatusText = (status: string) => {
    const texts: Record<string, string> = {
      'draft': '草稿',
      'writing': '创作中',
      'completed': '已完成',
    };
    return texts[status] || status;
  };

  const sortedChapters = [...chapters].sort((a, b) => a.chapter_number - b.chapter_number);

  const handleExport = () => {
    if (chapters.length === 0) {
      message.warning('当前项目没有章节，无法导出');
      return;
    }
    
    Modal.confirm({
      title: '导出项目章节',
      content: `确定要将《${currentProject.title}》的所有章节导出为TXT文件吗？`,
      centered: true,
      okText: '确定导出',
      cancelText: '取消',
      onOk: () => {
        try {
          projectApi.exportProject(currentProject.id);
          message.success('开始下载导出文件');
        } catch {
          message.error('导出失败，请重试');
        }
      },
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: '#fff',
        padding: isMobile ? '12px 0' : '16px 0',
        marginBottom: isMobile ? 12 : 16,
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        flexDirection: isMobile ? 'column' : 'row',
        gap: isMobile ? 12 : 0,
        justifyContent: 'space-between',
        alignItems: isMobile ? 'stretch' : 'center'
      }}>
        <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24 }}>章节管理</h2>
        <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ width: isMobile ? '100%' : 'auto' }}>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleExport}
            disabled={chapters.length === 0}
            block={isMobile}
            size={isMobile ? 'middle' : 'middle'}
          >
            导出为TXT
          </Button>
          {!isMobile && <Tag color="blue">章节由大纲管理，请在大纲页面添加/删除</Tag>}
        </Space>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {chapters.length === 0 ? (
        <Empty description="还没有章节，开始创作吧！" />
      ) : (
        <Card style={cardStyles.base}>
          <List
            dataSource={sortedChapters}
            renderItem={(item) => (
              <List.Item
                style={{
                  padding: '16px 0',
                  borderRadius: 8,
                  transition: 'background 0.3s ease',
                  flexDirection: isMobile ? 'column' : 'row',
                  alignItems: isMobile ? 'flex-start' : 'center'
                }}
                actions={isMobile ? undefined : [
                  <Button
                    type="primary"
                    icon={<EditOutlined />}
                    onClick={() => handleOpenEditor(item.id)}
                  >
                    编辑内容
                  </Button>,
                  <Button
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => handleOpenModal(item.id)}
                  >
                    修改信息
                  </Button>,
                ]}
              >
                <div style={{ width: '100%' }}>
                  <List.Item.Meta
                    avatar={!isMobile && <FileTextOutlined style={{ fontSize: 32, color: '#1890ff' }} />}
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 4 : 8, flexWrap: 'wrap', fontSize: isMobile ? 14 : 16 }}>
                        <span>第{item.chapter_number}章：{item.title}</span>
                        <Tag color={getStatusColor(item.status)}>{getStatusText(item.status)}</Tag>
                        <Badge count={`${item.word_count || 0}字`} style={{ backgroundColor: '#52c41a' }} />
                        {!canGenerateChapter(item) && (
                          <Tooltip title={getGenerateDisabledReason(item)}>
                            <Tag icon={<LockOutlined />} color="warning">
                              需前置章节
                            </Tag>
                          </Tooltip>
                        )}
                      </div>
                    }
                    description={
                      item.content ? (
                        <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.65)', lineHeight: 1.6, fontSize: isMobile ? 12 : 14 }}>
                          {item.content.substring(0, isMobile ? 80 : 150)}
                          {item.content.length > (isMobile ? 80 : 150) && '...'}
                        </div>
                      ) : (
                        <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: isMobile ? 12 : 14 }}>暂无内容</span>
                      )
                    }
                  />
                  
                  {isMobile && (
                    <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }} wrap>
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => handleOpenEditor(item.id)}
                        size="small"
                        title="编辑内容"
                      />
                      <Button
                        type="text"
                        icon={<SettingOutlined />}
                        onClick={() => handleOpenModal(item.id)}
                        size="small"
                        title="修改信息"
                      />
                    </Space>
                  )}
                </div>
              </List.Item>
            )}
          />
        </Card>
        )}
      </div>

      <Modal
        title={editingId ? '编辑章节信息' : '添加章节'}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        centered={!isMobile}
        width={isMobile ? 'calc(100% - 32px)' : 520}
        style={isMobile ? {
          top: 20,
          paddingBottom: 0,
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 16px'
        } : undefined}
        styles={{
          body: {
            maxHeight: isMobile ? 'calc(100vh - 150px)' : 'calc(80vh - 110px)',
            overflowY: 'auto'
          }
        }}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="章节标题"
            name="title"
            tooltip="章节标题由大纲管理，建议在大纲页面统一修改"
          >
            <Input placeholder="输入章节标题" disabled />
          </Form.Item>

          <Form.Item
            label="章节序号"
            name="chapter_number"
            tooltip="章节序号由大纲的顺序决定，无法修改。请在大纲页面使用上移/下移功能调整顺序"
          >
            <Input type="number" placeholder="章节排序序号" disabled />
          </Form.Item>

          <Form.Item label="状态" name="status">
            <Select placeholder="选择状态">
              <Select.Option value="draft">草稿</Select.Option>
              <Select.Option value="writing">创作中</Select.Option>
              <Select.Option value="completed">已完成</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Space style={{ float: 'right' }}>
              <Button onClick={() => setIsModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                更新
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑章节内容"
        open={isEditorOpen}
        onCancel={() => {
          if (isGenerating) {
            message.warning('AI正在创作中，请等待完成后再关闭');
            return;
          }
          setIsEditorOpen(false);
        }}
        closable={!isGenerating}
        maskClosable={!isGenerating}
        keyboard={!isGenerating}
        width={isMobile ? 'calc(100% - 32px)' : '85%'}
        centered={!isMobile}
        style={isMobile ? {
          top: 20,
          paddingBottom: 0,
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 16px'
        } : undefined}
        styles={{
          body: {
            maxHeight: isMobile ? 'calc(100vh - 150px)' : 'calc(85vh - 110px)',
            overflowY: 'auto',
            padding: isMobile ? '16px 12px' : '8px'
          }
        }}
        footer={null}
      >
        <Form form={editorForm} layout="vertical" onFinish={handleEditorSubmit}>
          <Form.Item
            label="章节标题"
            tooltip="章节标题由大纲统一管理，建议在大纲页面修改以保持一致性"
          >
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item
                name="title"
                noStyle
              >
                <Input size="large" disabled style={{ flex: 1 }} />
              </Form.Item>
              {editingId && (() => {
                const currentChapter = chapters.find(c => c.id === editingId);
                const canGenerate = currentChapter ? canGenerateChapter(currentChapter) : false;
                const disabledReason = currentChapter ? getGenerateDisabledReason(currentChapter) : '';
                
                return (
                  <Tooltip title={!canGenerate ? disabledReason : '根据大纲和前置章节内容创作'}>
                    <Button
                      type="primary"
                      icon={canGenerate ? <ThunderboltOutlined /> : <LockOutlined />}
                      onClick={() => currentChapter && showGenerateModal(currentChapter)}
                      loading={isContinuing}
                      disabled={!canGenerate}
                      danger={!canGenerate}
                      size="large"
                      style={{ fontWeight: 'bold' }}
                    >
                      {isMobile ? 'AI创作' : 'AI创作章节内容'}
                    </Button>
                  </Tooltip>
                );
              })()}
            </Space.Compact>
          </Form.Item>

          <Form.Item label="章节内容" name="content">
            <TextArea
              ref={contentTextAreaRef}
              rows={isMobile ? 12 : 20}
              placeholder="开始写作..."
              style={{ fontFamily: 'monospace', fontSize: isMobile ? 12 : 14 }}
              disabled={isGenerating}
            />
          </Form.Item>

          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' }}>
              <Space style={{ width: isMobile ? '100%' : 'auto' }}>
                <Button
                  onClick={() => {
                    if (isGenerating) {
                      message.warning('AI正在创作中，请等待完成后再关闭');
                      return;
                    }
                    setIsEditorOpen(false);
                  }}
                  block={isMobile}
                  disabled={isGenerating}
                >
                  取消
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  block={isMobile}
                  disabled={isGenerating}
                >
                  保存章节
                </Button>
              </Space>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}