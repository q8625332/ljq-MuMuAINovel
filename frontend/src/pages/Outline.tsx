import { useState, useEffect } from 'react';
import { Button, List, Modal, Form, Input, message, Empty, Space, Popconfirm, Card, Select, Radio, Tag } from 'antd';
import { EditOutlined, DeleteOutlined, ThunderboltOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useOutlineSync } from '../store/hooks';
import { cardStyles } from '../components/CardStyles';

const { TextArea } = Input;

export default function Outline() {
  const { currentProject, outlines } = useStore();
  const [isGenerating, setIsGenerating] = useState(false);
  const [editForm] = Form.useForm();
  const [generateForm] = Form.useForm();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 使用同步 hooks（移除createOutline）
  const {
    refreshOutlines,
    updateOutline,
    deleteOutline,
    reorderOutlines,
    generateOutlines
  } = useOutlineSync();

  // 初始加载大纲列表
  useEffect(() => {
    if (currentProject?.id) {
      refreshOutlines();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProject?.id]); // 只依赖 ID，不依赖函数

  // 移除事件监听，避免无限循环
  // Hook 内部已经更新了 store，不需要再次刷新

  if (!currentProject) return null;

  // 确保大纲按 order_index 排序
  const sortedOutlines = [...outlines].sort((a, b) => a.order_index - b.order_index);

  const handleOpenEditModal = (id: string) => {
    const outline = outlines.find(o => o.id === id);
    if (outline) {
      editForm.setFieldsValue(outline);
      Modal.confirm({
        title: '编辑大纲',
        width: 600,
        centered: true,
        content: (
          <Form
            form={editForm}
            layout="vertical"
            style={{ marginTop: 16 }}
          >
            <Form.Item
              label="标题"
              name="title"
              rules={[{ required: true, message: '请输入标题' }]}
            >
              <Input placeholder="输入大纲标题" />
            </Form.Item>

            <Form.Item
              label="内容"
              name="content"
              rules={[{ required: true, message: '请输入内容' }]}
            >
              <TextArea rows={6} placeholder="输入大纲内容..." />
            </Form.Item>
          </Form>
        ),
        okText: '更新',
        cancelText: '取消',
        onOk: async () => {
          const values = await editForm.validateFields();
          try {
            await updateOutline(id, values);
            message.success('大纲更新成功');
          } catch {
            message.error('更新失败');
          }
        },
      });
    }
  };

  const handleDeleteOutline = async (id: string) => {
    try {
      await deleteOutline(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleMoveUp = async (index: number) => {
    if (index === 0) return;

    const items = Array.from(sortedOutlines);
    [items[index - 1], items[index]] = [items[index], items[index - 1]];

    const newOrders = items.map((item, idx) => ({
      id: item.id,
      order_index: idx + 1
    }));

    try {
      await reorderOutlines(newOrders);
      message.success('上移成功');
    } catch (error) {
      message.error('调整失败');
      console.error('重排序失败:', error);
    }
  };

  const handleMoveDown = async (index: number) => {
    if (index === sortedOutlines.length - 1) return;

    const items = Array.from(sortedOutlines);
    [items[index], items[index + 1]] = [items[index + 1], items[index]];

    const newOrders = items.map((item, idx) => ({
      id: item.id,
      order_index: idx + 1
    }));

    try {
      await reorderOutlines(newOrders);
      message.success('下移成功');
    } catch (error) {
      message.error('调整失败');
      console.error('重排序失败:', error);
    }
  };

  interface GenerateFormValues {
    theme?: string;
    chapter_count?: number;
    narrative_perspective?: string;
    requirements?: string;
    provider?: string;
    model?: string;
    mode?: 'auto' | 'new' | 'continue';
    story_direction?: string;
    plot_stage?: 'development' | 'climax' | 'ending';
    keep_existing?: boolean;
  }

  const handleGenerate = async (values: GenerateFormValues) => {
    try {
      setIsGenerating(true);
      // 如果是全新生成模式，keep_existing应该为false
      const isNewMode = values.mode === 'new';
      const result = await generateOutlines({
        project_id: currentProject.id,
        genre: currentProject.genre || '通用',
        theme: values.theme || currentProject.theme || '',
        chapter_count: values.chapter_count || 5,
        narrative_perspective: values.narrative_perspective || currentProject.narrative_perspective || '第三人称',
        target_words: currentProject.target_words || 100000,
        requirements: values.requirements,
        // 续写参数
        mode: values.mode || 'auto',
        story_direction: values.story_direction,
        plot_stage: values.plot_stage || 'development',
        keep_existing: !isNewMode,  // 全新生成模式下不保留旧大纲
      });
      message.success(`成功生成 ${result.length} 条大纲`);
      Modal.destroyAll();
      // 刷新大纲列表，确保显示最新数据
      await refreshOutlines();
    } catch (error) {
      console.error('AI生成失败:', error);
      message.error('AI生成失败');
    } finally {
      setIsGenerating(false);
    }
  };

  const showGenerateModal = () => {
    const hasOutlines = outlines.length > 0;
    const initialMode = hasOutlines ? 'continue' : 'new';
    
    Modal.confirm({
      title: hasOutlines ? (
        <Space>
          <span>AI生成/续写大纲</span>
          <Tag color="blue">当前已有 {outlines.length} 章</Tag>
        </Space>
      ) : 'AI生成大纲',
      width: 700,
      centered: true,
      content: (
        <Form
          form={generateForm}
          layout="vertical"
          style={{ marginTop: 16 }}
          initialValues={{
            mode: initialMode,
            chapter_count: 5,
            narrative_perspective: currentProject.narrative_perspective || '第三人称',
            plot_stage: 'development',
            keep_existing: true,
            theme: currentProject.theme || '',
          }}
        >
          {hasOutlines && (
            <Form.Item
              label="生成模式"
              name="mode"
              tooltip="自动判断：根据是否有大纲自动选择；全新生成：删除旧大纲重新生成；续写模式：基于已有大纲继续创作"
            >
              <Radio.Group buttonStyle="solid">
                <Radio.Button value="auto">自动判断</Radio.Button>
                <Radio.Button value="new">全新生成</Radio.Button>
                <Radio.Button value="continue">续写模式</Radio.Button>
              </Radio.Group>
            </Form.Item>
          )}

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.mode !== currentValues.mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('mode');
              const isContinue = mode === 'continue' || (mode === 'auto' && hasOutlines);
              
              // 续写模式不显示主题输入，使用项目原有主题
              if (isContinue) {
                return null;
              }
              
              // 全新生成模式需要输入主题
              return (
                <Form.Item
                  label="故事主题"
                  name="theme"
                  rules={[{ required: true, message: '请输入故事主题' }]}
                >
                  <TextArea rows={3} placeholder="描述你的故事主题、核心设定和主要情节..." />
                </Form.Item>
              );
            }}
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.mode !== currentValues.mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('mode');
              const isContinue = mode === 'continue' || (mode === 'auto' && hasOutlines);
              
              return (
                <>
                  {isContinue && (
                    <>
                      <Form.Item
                        label="故事发展方向"
                        name="story_direction"
                        tooltip="告诉AI你希望故事接下来如何发展"
                      >
                        <TextArea
                          rows={3}
                          placeholder="例如：主角遇到新的挑战、引入新角色、揭示关键秘密等..."
                        />
                      </Form.Item>

                      <Form.Item
                        label="情节阶段"
                        name="plot_stage"
                        tooltip="帮助AI理解当前故事所处的阶段"
                      >
                        <Select>
                          <Select.Option value="development">发展阶段 - 继续展开情节</Select.Option>
                          <Select.Option value="climax">高潮阶段 - 矛盾激化</Select.Option>
                          <Select.Option value="ending">结局阶段 - 收束伏笔</Select.Option>
                        </Select>
                      </Form.Item>
                    </>
                  )}

                  <Form.Item
                    label={isContinue ? "续写章节数" : "章节数量"}
                    name="chapter_count"
                    rules={[{ required: true, message: '请输入章节数量' }]}
                  >
                    <Input
                      type="number"
                      min={1}
                      max={50}
                      placeholder={isContinue ? "建议5-10章" : "如：30"}
                    />
                  </Form.Item>

                  <Form.Item
                    label="叙事视角"
                    name="narrative_perspective"
                    rules={[{ required: true, message: '请选择叙事视角' }]}
                  >
                    <Select>
                      <Select.Option value="第一人称">第一人称</Select.Option>
                      <Select.Option value="第三人称">第三人称</Select.Option>
                      <Select.Option value="全知视角">全知视角</Select.Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label="其他要求" name="requirements">
                    <TextArea rows={2} placeholder="其他特殊要求（可选）" />
                  </Form.Item>
                </>
              );
            }}
          </Form.Item>
        </Form>
      ),
      okText: hasOutlines ? '开始续写' : '开始生成',
      cancelText: '取消',
      onOk: async () => {
        const values = await generateForm.validateFields();
        await handleGenerate(values);
      },
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 固定头部 */}
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
        <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24 }}>故事大纲</h2>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={showGenerateModal}
          loading={isGenerating}
          block={isMobile}
        >
          {isMobile ? 'AI生成/续写' : 'AI生成/续写大纲'}
        </Button>
      </div>

      {/* 可滚动内容区域 */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {outlines.length === 0 ? (
        <Empty description="还没有大纲，开始创建吧！" />
      ) : (
        <Card style={cardStyles.base}>
          <List
            dataSource={sortedOutlines}
            renderItem={(item, index) => (
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
                    type="text"
                    icon={<ArrowUpOutlined />}
                    onClick={() => handleMoveUp(index)}
                    disabled={index === 0}
                    title="上移"
                  >
                    上移
                  </Button>,
                  <Button
                    type="text"
                    icon={<ArrowDownOutlined />}
                    onClick={() => handleMoveDown(index)}
                    disabled={index === sortedOutlines.length - 1}
                    title="下移"
                  >
                    下移
                  </Button>,
                  <Button
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => handleOpenEditModal(item.id)}
                  >
                    编辑
                  </Button>,
                  <Popconfirm
                    title="确定删除这条大纲吗？"
                    onConfirm={() => handleDeleteOutline(item.id)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button type="text" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <div style={{ width: '100%' }}>
                  <List.Item.Meta
                    title={
                      <span style={{ fontSize: isMobile ? 14 : 16 }}>
                        <span style={{ color: '#1890ff', marginRight: 8, fontWeight: 'bold' }}>
                          第{item.order_index || '?'}章
                        </span>
                        {item.title}
                      </span>
                    }
                    description={
                      <div style={{ fontSize: isMobile ? 12 : 14 }}>
                        {item.content}
                      </div>
                    }
                  />
                  
                  {/* 移动端：按钮显示在内容下方 */}
                  {isMobile && (
                    <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }} wrap>
                      <Button
                        type="text"
                        icon={<ArrowUpOutlined />}
                        onClick={() => handleMoveUp(index)}
                        disabled={index === 0}
                        size="small"
                      />
                      <Button
                        type="text"
                        icon={<ArrowDownOutlined />}
                        onClick={() => handleMoveDown(index)}
                        disabled={index === sortedOutlines.length - 1}
                        size="small"
                      />
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => handleOpenEditModal(item.id)}
                        size="small"
                      />
                      <Popconfirm
                        title="确定删除这条大纲吗？"
                        onConfirm={() => handleDeleteOutline(item.id)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="text" danger icon={<DeleteOutlined />} size="small" />
                      </Popconfirm>
                    </Space>
                  )}
                </div>
              </List.Item>
            )}
          />
        </Card>
        )}
      </div>
    </div>
  );
}