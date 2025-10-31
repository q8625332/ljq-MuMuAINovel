import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Steps, Form, Input, InputNumber, Select, Button, message, Card, Spin,
  Row, Col, Typography, Modal, Space, Divider, Popconfirm
} from 'antd';
import {
  RocketOutlined, GlobalOutlined, TeamOutlined, FileTextOutlined,
  LoadingOutlined, ArrowLeftOutlined, HomeOutlined, UserOutlined,
  EditOutlined, RedoOutlined
} from '@ant-design/icons';
import { wizardStreamApi, characterApi, projectApi } from '../services/api';
import type { WorldBuildingResponse, Character, WizardBasicInfo, ApiError, CharacterUpdate, GenerateOutlineRequest, ProjectWizardUpdate } from '../types';
import { characterGridConfig } from '../components/CardStyles';
import { CharacterCard } from '../components/CharacterCard';
import { SSELoadingOverlay } from '../components/SSELoadingOverlay';

const { Step } = Steps;
const { TextArea } = Input;
const { Title, Paragraph, Text } = Typography;

export default function ProjectWizardNew() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [characterForm] = Form.useForm();
  const [worldForm] = Form.useForm();
  const [current, setCurrent] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isResumingWizard, setIsResumingWizard] = useState(false);
  const [isEditingWorld, setIsEditingWorld] = useState(false);
  const [isRegeneratingWorld, setIsRegeneratingWorld] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  // SSE流式进度状态
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  
  // 步骤数据
  const [basicInfo, setBasicInfo] = useState<WizardBasicInfo>({
    title: '',
    description: '',
    theme: '',
    genre: ['玄幻'],
    chapter_count: 30,
    narrative_perspective: '第三人称',
    character_count: 3,
    target_words: 100000,
  });
  const [worldBuilding, setWorldBuilding] = useState<WorldBuildingResponse | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const [requiredCharacterCount, setRequiredCharacterCount] = useState(5);
  
  // 角色编辑
  const [isCharacterModalOpen, setIsCharacterModalOpen] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);
  const [modalType, setModalType] = useState<'character' | 'organization'>('character');
  
  // 异步任务
  const pollingIntervalRef = useRef<number | null>(null);
  const hasRestoredRef = useRef(false);

  // 自动保存进度（当步骤改变时）
  useEffect(() => {
    const saveProgress = async () => {
      if (projectId && current > 0 && current < 4 && !isResumingWizard) {
        try {
          await projectApi.updateProject(projectId, {
            wizard_step: current
          } as ProjectWizardUpdate);
        } catch (error) {
          console.error('保存进度失败:', error);
        }
      }
    };
    
    saveProgress();
  }, [current, projectId, isResumingWizard]);

  // 恢复向导逻辑
  useEffect(() => {
    const resumeWizard = async () => {
      const projectId = searchParams.get('projectId');
      const step = searchParams.get('step');
      
      // 防止重复执行
      if (projectId && step && !hasRestoredRef.current) {
        hasRestoredRef.current = true;
        setIsResumingWizard(true);
        try {
          // 加载项目数据
          const project = await projectApi.getProject(projectId);
          setProjectId(projectId);
          
          // 恢复基本信息
          const restoredBasicInfo = {
            title: project.title,
            description: project.description || '',
            theme: project.theme || '',
            genre: project.genre ? project.genre.split('、') : [],
            chapter_count: project.chapter_count || 30,
            narrative_perspective: project.narrative_perspective || '第三人称',
            character_count: project.character_count || 3,
            target_words: project.target_words || 100000,
          };
          setBasicInfo(restoredBasicInfo);
          
          // 恢复世界观
          if (project.world_time_period) {
            const restoredWorldBuilding = {
              project_id: projectId,
              time_period: project.world_time_period,
              location: project.world_location || '',
              atmosphere: project.world_atmosphere || '',
              rules: project.world_rules || '',
            };
            setWorldBuilding(restoredWorldBuilding);
          }
          
          // 恢复角色数据
          if (parseInt(step) >= 2) {
            const response = await characterApi.getCharacters(projectId);
            console.log('恢复向导 - API响应:', response);
            // 处理可能的分页格式或直接数组格式
            const chars = Array.isArray(response) ? response : ((response as unknown as { items: Character[] }).items || []);
            console.log('恢复向导 - 解析后的角色数组:', chars);
            setCharacters(chars);
            setRequiredCharacterCount(project.character_count || 5);
          }
          
          // 设置当前步骤
          const currentStep = parseInt(step);
          setCurrent(currentStep);
          
          message.info('已恢复上次的创建进度');
        } catch (error) {
          const apiError = error as ApiError;
          message.error('恢复向导失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
        } finally {
          setIsResumingWizard(false);
        }
      }
    };
    
    resumeWizard();
  }, [searchParams]);

  // 步骤定义
  const steps = [
    { title: '基本信息', icon: <RocketOutlined />, description: '书名和主题' },
    { title: '世界构建', icon: <GlobalOutlined />, description: 'AI生成世界观' },
    { title: '角色设定', icon: <TeamOutlined />, description: '生成和编辑角色' },
    { title: '大纲生成', icon: <FileTextOutlined />, description: '生成章节大纲' },
    { title: '完成创建', icon: <LoadingOutlined />, description: '创建项目' },
  ];

  // 第一步：基本信息 (使用SSE流式API)
  const handleBasicInfo = async (values: WizardBasicInfo) => {
    try {
      setLoading(true);
      setBasicInfo(values);
      setProgress(0);
      setProgressMessage('准备生成世界观...');

      // 使用SSE流式API生成世界构建并创建项目
      const result = await wizardStreamApi.generateWorldBuildingStream(
        {
          title: values.title,
          description: values.description,
          theme: values.theme,
          genre: Array.isArray(values.genre) ? values.genre.join('、') : values.genre,
          narrative_perspective: values.narrative_perspective,
          target_words: values.target_words,
          chapter_count: values.chapter_count,
          character_count: values.character_count,
        },
        {
          onProgress: (msg, prog) => {
            setProgress(prog);
            setProgressMessage(msg);
            console.log(`进度 ${prog}%: ${msg}`);
          },
          onResult: (data) => {
            console.log('世界观生成完成:', data);
            setProjectId(data.project_id);
            setWorldBuilding(data);
          },
          onError: (error) => {
            message.error('生成世界观失败：' + error);
          },
          onComplete: () => {
            message.success('世界观生成成功，项目已创建！');
            setCurrent(1);
            setLoading(false);
            setProgress(0);
            setProgressMessage('');
          }
        }
      );

      // 如果result中有数据也要处理
      if (result && result.project_id) {
        setProjectId(result.project_id);
        setWorldBuilding(result);
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('生成世界观失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      setLoading(false);
      setProgress(0);
      setProgressMessage('');
    }
  };

  // 第二步：确认世界构建，进入角色设定 (使用SSE流式API)
  const handleWorldBuildingNext = async (values: Partial<WorldBuildingResponse> & { character_count?: number }) => {
    try {
      setLoading(true);
      setRequiredCharacterCount(values.character_count || 5);
      setProgress(0);
      setProgressMessage('准备生成角色...');
      
      // 用于存储生成的角色数量
      let generatedCount = 0;
      
      // 使用SSE流式API生成角色
      const result = await wizardStreamApi.generateCharactersStream(
        {
          project_id: projectId,
          count: values.character_count || 5,
          world_context: {
            time_period: worldBuilding?.time_period || '',
            location: worldBuilding?.location || '',
            atmosphere: worldBuilding?.atmosphere || '',
            rules: worldBuilding?.rules || '',
          },
          theme: basicInfo.theme,
          genre: Array.isArray(basicInfo.genre) ? basicInfo.genre.join('、') : basicInfo.genre,
        },
        {
          onProgress: (msg, prog) => {
            setProgress(prog);
            setProgressMessage(msg);
            console.log(`进度 ${prog}%: ${msg}`);
          },
          onResult: (data) => {
            console.log('角色生成完成:', data);
            const generatedChars = data.characters || [];
            generatedCount = generatedChars.length;
            setCharacters(generatedChars);
          },
          onError: (error) => {
            message.error('生成角色失败：' + error);
          },
          onComplete: () => {
            message.success(`成功生成${generatedCount}个角色！`);
            setCurrent(2);
            setLoading(false);
            setProgress(0);
            setProgressMessage('');
          }
        }
      );

      // 如果result中有数据也要处理
      if (result && result.characters) {
        setCharacters(result.characters);
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('生成角色失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      setLoading(false);
      setProgress(0);
      setProgressMessage('');
    }
  };

  // 打开角色编辑对话框
  const handleEditCharacter = (character?: Character) => {
    if (character) {
      setEditingCharacter(character);
      characterForm.setFieldsValue(character);
      setModalType(character.is_organization ? 'organization' : 'character');
    } else {
      setEditingCharacter(null);
      characterForm.resetFields();
    }
    setIsCharacterModalOpen(true);
  };

  // 保存角色（仅用于编辑）
  const handleSaveCharacter = async (values: CharacterUpdate) => {
    try {
      if (editingCharacter) {
        // 更新现有角色
        await characterApi.updateCharacter(editingCharacter.id, values);
        const updatedChars = characters.map(c =>
          c.id === editingCharacter.id ? { ...c, ...values } : c
        );
        setCharacters(updatedChars);
        message.success('角色更新成功');
        setIsCharacterModalOpen(false);
        characterForm.resetFields();
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('保存角色失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
    }
  };

  // 删除角色
  const handleDeleteCharacter = async (id: string) => {
    try {
      await characterApi.deleteCharacter(id);
      setCharacters(characters.filter(c => c.id !== id));
      message.success('角色删除成功');
    } catch (error) {
      const apiError = error as ApiError;
      message.error('删除角色失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
    }
  };

  // 第三步：确认角色，进入大纲生成
  const handleCharactersConfirm = async () => {
    if (characters.length !== requiredCharacterCount) {
      message.error(`请保持角色数量为${requiredCharacterCount}个`);
      return;
    }
    
    try {
      setLoading(true);
      // 更新向导步骤
      await projectApi.updateProject(projectId, {
        wizard_step: 3
      } as ProjectWizardUpdate);
      setCurrent(3);
    } catch (error) {
      const apiError = error as ApiError;
      message.error('更新进度失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  // 第四步：生成大纲 (使用SSE流式API)
  const handleGenerateOutline = async (values: Partial<GenerateOutlineRequest>) => {
    try {
      setLoading(true);
      setProgress(0);
      setProgressMessage('准备生成大纲...');
      
      // 使用SSE流式API生成大纲
      await wizardStreamApi.generateCompleteOutlineStream(
        {
          project_id: projectId,
          chapter_count: values.chapter_count || 20,
          narrative_perspective: values.narrative_perspective || '第三人称',
          target_words: values.target_words,
        },
        {
          onProgress: (msg, prog) => {
            setProgress(prog);
            setProgressMessage(msg);
            console.log(`进度 ${prog}%: ${msg}`);
          },
          onResult: (data) => {
            console.log('大纲生成完成:', data);
          },
          onError: (error) => {
            message.error('生成大纲失败：' + error);
          },
          onComplete: () => {
            message.success('大纲生成成功！');
            setCurrent(4);
            setLoading(false);
            setProgress(0);
            setProgressMessage('');
          }
        }
      );
    } catch (error) {
      const apiError = error as ApiError;
      message.error('生成大纲失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      setLoading(false);
      setProgress(0);
      setProgressMessage('');
    }
  };

  // 更新世界观 (使用SSE流式API)
  const handleUpdateWorldBuilding = async (values: Partial<WorldBuildingResponse>) => {
    try {
      setLoading(true);
      setProgress(0);
      setProgressMessage('准备更新世界观...');
      
      const result = await wizardStreamApi.updateWorldBuildingStream(
        projectId,
        values,
        {
          onProgress: (msg, prog) => {
            setProgress(prog);
            setProgressMessage(msg);
          },
          onResult: (data) => {
            setWorldBuilding(data);
          },
          onError: (error) => {
            message.error('更新世界观失败：' + error);
          },
          onComplete: () => {
            setIsEditingWorld(false);
            message.success('世界观更新成功！');
            setLoading(false);
            setProgress(0);
            setProgressMessage('');
          }
        }
      );
      
      if (result) {
        setWorldBuilding(result);
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('更新世界观失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      setLoading(false);
      setProgress(0);
      setProgressMessage('');
    }
  };

  // 重新生成世界观 (使用SSE流式API)
  const handleRegenerateWorldBuilding = async () => {
    try {
      setIsRegeneratingWorld(true);
      setProgress(0);
      setProgressMessage('准备重新生成世界观...');
      
      const result = await wizardStreamApi.regenerateWorldBuildingStream(
        projectId,
        {},
        {
          onProgress: (msg, prog) => {
            setProgress(prog);
            setProgressMessage(msg);
          },
          onResult: (data) => {
            setWorldBuilding(data);
          },
          onError: (error) => {
            message.error('重新生成世界观失败：' + error);
          },
          onComplete: () => {
            message.success('世界观重新生成成功！');
            setIsRegeneratingWorld(false);
            setProgress(0);
            setProgressMessage('');
          }
        }
      );
      
      if (result) {
        setWorldBuilding(result);
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('重新生成世界观失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      setIsRegeneratingWorld(false);
      setProgress(0);
      setProgressMessage('');
    }
  };

  // 上一步
  const handlePrev = async () => {
    // 如果在第一步之后返回，需要确认是否清理数据
    if (current === 1 && projectId) {
      Modal.confirm({
        title: '确认返回',
        content: '返回上一步将清除已创建的项目和世界观数据，是否继续？',
        okText: '确认',
        cancelText: '取消',
        centered: true,
        ...(isMobile && {
          style: { top: 'auto' }
        }),
        onOk: async () => {
          try {
            setLoading(true);
            setProgress(0);
            setProgressMessage('准备清理数据...');
            
            await wizardStreamApi.cleanupWizardDataStream(
              projectId,
              {
                onProgress: (msg, prog) => {
                  setProgress(prog);
                  setProgressMessage(msg);
                },
                onResult: (data) => {
                  console.log('清理完成:', data);
                },
                onError: (error) => {
                  message.error('清理数据失败：' + error);
                },
                onComplete: () => {
                  setProjectId('');
                  setWorldBuilding(null);
                  setCurrent(0);
                  message.success('已清理数据');
                  setLoading(false);
                  setProgress(0);
                  setProgressMessage('');
                }
              }
            );
          } catch (error) {
            const apiError = error as ApiError;
            message.error('清理数据失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
            setLoading(false);
            setProgress(0);
            setProgressMessage('');
          }
        },
      });
    } else if (current === 2 && projectId) {
      // 从角色设定返回到世界构建
      Modal.confirm({
        title: '确认返回',
        content: '返回上一步将清除已生成的角色数据，是否继续？',
        okText: '确认',
        cancelText: '取消',
        centered: true,
        ...(isMobile && {
          style: { top: 'auto' }
        }),
        onOk: async () => {
          try {
            setLoading(true);
            // 只删除角色，保留项目和世界观
            const safeCharacters = Array.isArray(characters) ? characters : [];
            for (const char of safeCharacters) {
              await characterApi.deleteCharacter(char.id);
            }
            setCharacters([]);
            setCurrent(1);
            message.success('已清理角色数据');
          } catch (error) {
            const apiError = error as ApiError;
            message.error('清理角色数据失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
          } finally {
            setLoading(false);
          }
        },
      });
    } else if (current === 3 && projectId) {
      // 从大纲生成返回到角色设定，需要加载角色数据
      try {
        setLoading(true);
        const response = await characterApi.getCharacters(projectId);
        console.log('返回上一步 - API响应:', response);
        // 处理可能的分页格式或直接数组格式
        const chars = Array.isArray(response) ? response : ((response as unknown as { items: Character[] }).items || []);
        console.log('返回上一步 - 解析后的角色数组:', chars);
        setCharacters(chars);
        setCurrent(2);
        message.success(`已加载${chars.length}个角色`);
      } catch (error) {
        const apiError = error as ApiError;
        console.error('加载角色数据失败:', error);
        message.error('加载角色数据失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
      } finally {
        setLoading(false);
      }
    } else {
      setCurrent(current - 1);
    }
  };

  // 清理定时器
  useEffect(() => {
    const intervalId = pollingIntervalRef.current;
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, []);

  // 渲染第一步：基本信息
  const renderBasicInfo = () => (
    <Card>
      <Form form={form} layout="vertical" onFinish={handleBasicInfo} initialValues={basicInfo}>
        <Form.Item label="书名" name="title" rules={[{ required: true, message: '请输入书名' }]}>
          <Input placeholder="输入你的小说标题" size="large" />
        </Form.Item>

        <Form.Item label="小说简介" name="description" rules={[{ required: true, message: '请输入小说简介' }]}>
          <TextArea rows={3} placeholder="用一段话介绍你的小说..." showCount maxLength={300} />
        </Form.Item>

        <Form.Item label="主题" name="theme" rules={[{ required: true, message: '请输入主题' }]}>
          <TextArea rows={4} placeholder="描述你的小说主题..." showCount maxLength={500} />
        </Form.Item>

        <Form.Item label="类型" name="genre" rules={[{ required: true, message: '请输入小说类型' }]}>
          <Select
            mode="tags"
            placeholder="输入类型标签，按回车添加（如：玄幻、都市、修仙）"
            size="large"
            tokenSeparators={[',']}
            maxTagCount={5}
          >
            <Select.Option value="玄幻">玄幻</Select.Option>
            <Select.Option value="都市">都市</Select.Option>
            <Select.Option value="历史">历史</Select.Option>
            <Select.Option value="科幻">科幻</Select.Option>
            <Select.Option value="武侠">武侠</Select.Option>
            <Select.Option value="仙侠">仙侠</Select.Option>
            <Select.Option value="奇幻">奇幻</Select.Option>
            <Select.Option value="悬疑">悬疑</Select.Option>
            <Select.Option value="言情">言情</Select.Option>
            <Select.Option value="修仙">修仙</Select.Option>
            <Select.Option value="爽文">爽文</Select.Option>
            <Select.Option value="轻小说">轻小说</Select.Option>
          </Select>
        </Form.Item>

        <Form.Item label="叙事视角" name="narrative_perspective" rules={[{ required: true, message: '请选择叙事视角' }]}>
          <Select size="large" placeholder="选择小说的叙事视角">
            <Select.Option value="第一人称">第一人称</Select.Option>
            <Select.Option value="第三人称">第三人称</Select.Option>
            <Select.Option value="全知视角">全知视角</Select.Option>
          </Select>
        </Form.Item>

        <Form.Item label="目标字数" name="target_words" rules={[{ required: true, message: '请输入目标字数' }]}>
          <InputNumber min={10000} style={{ width: '100%' }} size="large" addonAfter="字" placeholder="整部小说的目标字数" />
        </Form.Item>

        <Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>
            {loading ? '生成中...' : '下一步：生成世界观'}
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );

  // 渲染第二步：世界构建
  const renderWorldBuilding = () => (
    <Card>
      <Spin spinning={loading || isRegeneratingWorld}>
        {worldBuilding && (
          <div style={{ marginBottom: 24 }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: isMobile ? 'flex-start' : 'center',
              marginBottom: isMobile ? 20 : 24,
              flexDirection: isMobile ? 'column' : 'row',
              gap: isMobile ? 16 : 0
            }}>
              <Title level={isMobile ? 5 : 4} style={{ margin: 0 }}>AI生成的世界观</Title>
              <Space wrap size={isMobile ? 12 : 8}>
                <Button
                  icon={<EditOutlined />}
                  onClick={() => {
                    setIsEditingWorld(true);
                    worldForm.setFieldsValue({
                      time_period: worldBuilding.time_period,
                      location: worldBuilding.location,
                      atmosphere: worldBuilding.atmosphere,
                      rules: worldBuilding.rules,
                    });
                  }}
                  size={isMobile ? 'middle' : 'middle'}
                  style={isMobile ? { minWidth: 100 } : undefined}
                >
                  编辑
                </Button>
                <Popconfirm
                  title="重新生成世界观"
                  description="确定要重新生成世界观吗？当前内容将被覆盖。"
                  onConfirm={handleRegenerateWorldBuilding}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button
                    icon={<RedoOutlined />}
                    loading={isRegeneratingWorld}
                    size={isMobile ? 'middle' : 'middle'}
                    style={isMobile ? { minWidth: 100 } : undefined}
                  >
                    重新生成
                  </Button>
                </Popconfirm>
              </Space>
            </div>
            
            {!isEditingWorld ? (
              <>
                <Paragraph><Text strong>时间背景：</Text><br />{worldBuilding.time_period}</Paragraph>
                <Paragraph><Text strong>地理位置：</Text><br />{worldBuilding.location}</Paragraph>
                <Paragraph><Text strong>氛围基调：</Text><br />{worldBuilding.atmosphere}</Paragraph>
                <Paragraph><Text strong>世界规则：</Text><br />{worldBuilding.rules}</Paragraph>
              </>
            ) : (
              <Form form={worldForm} layout="vertical" onFinish={handleUpdateWorldBuilding}>
                <Form.Item label="时间背景" name="time_period" rules={[{ required: true, message: '请输入时间背景' }]}>
                  <TextArea rows={3} placeholder="描述故事发生的时间背景..." />
                </Form.Item>
                <Form.Item label="地理位置" name="location" rules={[{ required: true, message: '请输入地理位置' }]}>
                  <TextArea rows={3} placeholder="描述故事发生的地理位置..." />
                </Form.Item>
                <Form.Item label="氛围基调" name="atmosphere" rules={[{ required: true, message: '请输入氛围基调' }]}>
                  <TextArea rows={3} placeholder="描述故事的氛围基调..." />
                </Form.Item>
                <Form.Item label="世界规则" name="rules" rules={[{ required: true, message: '请输入世界规则' }]}>
                  <TextArea rows={3} placeholder="描述世界的特殊规则..." />
                </Form.Item>
                <Form.Item>
                  <Space size={isMobile ? 12 : 8} style={{ width: isMobile ? '100%' : 'auto' }}>
                    <Button
                      onClick={() => setIsEditingWorld(false)}
                      size={isMobile ? 'middle' : 'middle'}
                      style={isMobile ? { flex: 1, minWidth: 100 } : undefined}
                    >
                      取消
                    </Button>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      size={isMobile ? 'middle' : 'middle'}
                      style={isMobile ? { flex: 1, minWidth: 100 } : undefined}
                    >
                      保存
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
            )}
          </div>
        )}

        <Form layout="vertical" onFinish={handleWorldBuildingNext} initialValues={{ character_count: 5 }}>
          <Form.Item
            label="角色数量"
            name="character_count"
            rules={[{ required: true, message: '请输入角色数量' }]}
          >
            <InputNumber min={5} max={20} style={{ width: '100%' }} size="large"
              addonAfter="个" placeholder="生成的角色和组织数量" />
          </Form.Item>

          <Row gutter={isMobile ? [16, 16] : 16} style={{ marginTop: isMobile ? 24 : 0 }}>
            <Col xs={24} sm={12}>
              <Button
                size="large"
                block
                onClick={handlePrev}
                style={{ height: isMobile ? 44 : 40 }}
              >
                上一步
              </Button>
            </Col>
            <Col xs={24} sm={12}>
              <Button
                type="primary"
                size="large"
                block
                htmlType="submit"
                loading={loading}
                disabled={isEditingWorld}
                style={{ height: isMobile ? 44 : 40 }}
              >
                {loading ? '生成中...' : '下一步：生成角色'}
              </Button>
            </Col>
          </Row>
        </Form>
      </Spin>
    </Card>
  );


  // 渲染第三步：角色设定
  const renderCharacters = () => {
    // 确保 characters 是数组
    const safeCharacters = Array.isArray(characters) ? characters : [];
    console.log('renderCharacters - characters:', characters);
    console.log('renderCharacters - safeCharacters:', safeCharacters);
    const characterList = safeCharacters.filter(c => !c.is_organization);
    const organizationList = safeCharacters.filter(c => c.is_organization);
    console.log('characterList:', characterList);
    console.log('organizationList:', organizationList);

    return (
      <Card>
        <div style={{ marginBottom: 16 }}>
          <Title level={isMobile ? 5 : 4} style={{ margin: 0, fontSize: isMobile ? 16 : undefined }}>
            角色与组织列表 (当前: {safeCharacters.length}个，目标: {requiredCharacterCount}个)
          </Title>
          <Paragraph type="secondary" style={{ margin: '8px 0 0 0', fontSize: isMobile ? 12 : 14 }}>
            所有角色均由AI生成，您可以点击卡片上的编辑按钮进行调整
          </Paragraph>
        </div>

        <Row gutter={characterGridConfig.gutter}>
          {characterList.length > 0 && (
            <>
              <Col span={24}>
                <Divider orientation="left">
                  <Title level={5} style={{ margin: 0 }}>
                    <UserOutlined style={{ marginRight: 8 }} />
                    角色 ({characterList.length})
                  </Title>
                </Divider>
              </Col>
              {characterList.map((character) => (
                <Col {...characterGridConfig} key={character.id} style={{ padding: '8px' }}>
                  <CharacterCard
                    character={character}
                    onEdit={handleEditCharacter}
                    onDelete={handleDeleteCharacter}
                  />
                </Col>
              ))}
            </>
          )}

          {organizationList.length > 0 && (
            <>
              <Col span={24}>
                <Divider orientation="left">
                  <Title level={5} style={{ margin: 0 }}>
                    <TeamOutlined style={{ marginRight: 8 }} />
                    组织 ({organizationList.length})
                  </Title>
                </Divider>
              </Col>
              {organizationList.map((org) => (
                <Col {...characterGridConfig} key={org.id} style={{ padding: '8px' }}>
                  <CharacterCard
                    character={org}
                    onEdit={handleEditCharacter}
                    onDelete={handleDeleteCharacter}
                  />
                </Col>
              ))}
            </>
          )}
        </Row>

      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col span={24}>
          <Button
            type="primary"
            size="large"
            block
            onClick={handleCharactersConfirm}
            disabled={safeCharacters.length !== requiredCharacterCount}
          >
            下一步：生成大纲
          </Button>
        </Col>
      </Row>

      {/* 角色编辑对话框 */}
      <Modal
        title={modalType === 'organization' ? '编辑组织' : '编辑角色'}
        open={isCharacterModalOpen}
        onCancel={() => setIsCharacterModalOpen(false)}
        footer={null}
        width={isMobile ? 'calc(100% - 32px)' : 600}
        centered
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
        <Form form={characterForm} layout="vertical" onFinish={handleSaveCharacter}>
          <Row gutter={16}>
            <Col span={modalType === 'character' ? 12 : 24}>
              <Form.Item
                label={modalType === 'organization' ? '组织名称' : '角色名称'}
                name="name"
                rules={[{ required: true, message: `请输入${modalType === 'organization' ? '组织' : '角色'}名称` }]}
              >
                <Input placeholder={`输入${modalType === 'organization' ? '组织' : '角色'}名称`} />
              </Form.Item>
            </Col>
            
            {modalType === 'character' && (
              <Col span={12}>
                <Form.Item label="角色定位" name="role_type" initialValue="supporting">
                  <Select>
                    <Select.Option value="protagonist">主角</Select.Option>
                    <Select.Option value="supporting">配角</Select.Option>
                    <Select.Option value="antagonist">反派</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            )}
          </Row>

          {/* 角色特有字段 */}
          {modalType === 'character' && (
            <>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="年龄" name="age">
                    <Input placeholder="如：25、30岁" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="性别" name="gender">
                    <Select placeholder="选择性别">
                      <Select.Option value="男">男</Select.Option>
                      <Select.Option value="女">女</Select.Option>
                      <Select.Option value="其他">其他</Select.Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="性格特点" name="personality">
                <TextArea rows={2} placeholder="描述角色的性格特点..." />
              </Form.Item>

              <Form.Item label="外貌描写" name="appearance">
                <TextArea rows={2} placeholder="描述角色的外貌特征..." />
              </Form.Item>

              <Form.Item label="人际关系" name="relationships">
                <TextArea rows={2} placeholder="描述角色与其他角色的关系..." />
              </Form.Item>
            </>
          )}

          {/* 组织特有字段 */}
          {modalType === 'organization' && (
            <>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    label="组织类型"
                    name="organization_type"
                    rules={[{ required: true, message: '请输入组织类型' }]}
                  >
                    <Input placeholder="如：帮派、公司、门派、学院" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="主要成员" name="organization_members">
                    <Input placeholder="如：张三、李四、王五" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Form.Item
                label="组织目的"
                name="organization_purpose"
                rules={[{ required: true, message: '请输入组织目的' }]}
              >
                <TextArea rows={2} placeholder="描述组织的宗旨和目标..." />
              </Form.Item>
            </>
          )}

          <Form.Item label={modalType === 'organization' ? '组织背景' : '角色背景'} name="background">
            <TextArea rows={3} placeholder={`描述${modalType === 'organization' ? '组织' : '角色'}的背景故事...`} />
          </Form.Item>

          {/* 隐藏字段 */}
          <Form.Item name="is_organization" hidden>
            <Input />
          </Form.Item>

          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setIsCharacterModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit">保存</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
    );
  };

  // 渲染第四步：大纲生成
  const renderOutlineGeneration = () => (
    <Card>
      <div style={{ marginBottom: 24 }}>
        <Title level={isMobile ? 5 : 4}>生成开局大纲</Title>
        <Paragraph>
          <Text strong>叙事视角：</Text>{basicInfo.narrative_perspective}
          <Text strong style={{ marginLeft: 24 }}>目标字数：</Text>{basicInfo.target_words?.toLocaleString()} 字
        </Paragraph>
        <Paragraph type="secondary">
          向导将为您生成前8章的开局大纲，建立故事框架和主要冲突。后续您可以在大纲管理页面继续扩展故事。
        </Paragraph>
      </div>

      <Form layout="vertical" onFinish={() => handleGenerateOutline({
        chapter_count: 8,  // 固定8章
        narrative_perspective: basicInfo.narrative_perspective,
        target_words: basicInfo.target_words
      })}>
        <Row gutter={isMobile ? [16, 16] : 16} style={{ marginTop: isMobile ? 24 : 0 }}>
          <Col xs={24} sm={12}>
            <Button
              size="large"
              block
              onClick={handlePrev}
              style={{ height: isMobile ? 44 : 40 }}
            >
              上一步
            </Button>
          </Col>
          <Col xs={24} sm={12}>
            <Button
              type="primary"
              size="large"
              block
              htmlType="submit"
              loading={loading}
              style={{ height: isMobile ? 44 : 40 }}
            >
              {loading ? '生成开局大纲（8章）' : '生成开局大纲（8章）'}
            </Button>
          </Col>
        </Row>
      </Form>
    </Card>
  );

  // 渲染第五步：完成
  const renderComplete = () => (
    <Card>
      <div style={{
        textAlign: 'center',
        padding: isMobile ? '32px 16px' : '40px 0'
      }}>
        <div style={{
          fontSize: isMobile ? 56 : 72,
          color: '#52c41a',
          marginBottom: isMobile ? 16 : 24
        }}>
          ✓
        </div>
        <Title
          level={isMobile ? 3 : 2}
          style={{
            color: '#52c41a',
            marginBottom: isMobile ? 8 : 16
          }}
        >
          项目创建完成！
        </Title>
        <Paragraph style={{
          fontSize: isMobile ? 14 : 16,
          marginTop: isMobile ? 8 : 16,
          marginBottom: isMobile ? 24 : 32,
          paddingLeft: isMobile ? 8 : 0,
          paddingRight: isMobile ? 8 : 0
        }}>
          《{basicInfo.title}》已成功创建，包含{characters.length}个角色和8章开局大纲
        </Paragraph>
        
        <Space
          size={isMobile ? 12 : 16}
          direction={isMobile ? 'vertical' : 'horizontal'}
          style={{ width: isMobile ? '100%' : 'auto' }}
        >
          <Button
            size="large"
            icon={<HomeOutlined />}
            onClick={() => navigate('/')}
            block={isMobile}
            style={{
              minWidth: 120,
              height: isMobile ? 44 : 40
            }}
          >
            返回首页
          </Button>
          <Button
            type="primary"
            size="large"
            icon={<RocketOutlined />}
            onClick={() => navigate(`/project/${projectId}`)}
            block={isMobile}
            style={{
              minWidth: 120,
              height: isMobile ? 44 : 40
            }}
          >
            进入项目
          </Button>
        </Space>
      </div>
    </Card>
  );

  return (
    <div style={{
      minHeight: '100vh',
      height: '100vh',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      background: '#f5f7fa'
    }}>
      {/* 固定顶部渐变背景区域 */}
      <div style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: isMobile ? '16px 12px' : '24px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        flexShrink: 0,
        zIndex: 10
      }}>
        <div style={{
          maxWidth: 1200,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'relative'
        }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/')}
            size={isMobile ? 'middle' : 'large'}
            style={{
              background: 'rgba(255,255,255,0.2)',
              borderColor: 'rgba(255,255,255,0.3)',
              color: '#fff',
              fontSize: isMobile ? '14px' : '16px',
              height: isMobile ? '36px' : '40px',
              padding: isMobile ? '0 12px' : '0 16px'
            }}
          >
            {isMobile ? '主页' : '返回首页'}
          </Button>
          
          <Title level={isMobile ? 4 : 2} style={{
            margin: 0,
            color: '#fff',
            textShadow: '0 2px 4px rgba(0,0,0,0.1)',
            position: 'absolute',
            left: '50%',
            transform: 'translateX(-50%)',
            whiteSpace: 'nowrap'
          }}>
            {isResumingWizard ? '继续创建项目' : '项目创建向导'}
          </Title>
          
          <div style={{ width: isMobile ? '60px' : '120px' }}></div>
        </div>
      </div>

      {!isResumingWizard && (
        /* 固定 Steps 区域 */
        <div style={{
          background: '#fff',
          padding: isMobile ? '8px' : '24px',
          flexShrink: 0,
          borderBottom: '1px solid #f0f0f0'
        }}>
          <div style={{
            maxWidth: 1200,
            margin: '0 auto',
            display: isMobile ? 'flex' : 'block',
            justifyContent: isMobile ? 'center' : 'normal'
          }}>
            <Steps
              current={current}
              size="small"
              direction="horizontal"
              responsive={false}
              labelPlacement="vertical"
              style={isMobile ? {
                gap: '8px',
                maxWidth: 'fit-content'
              } : undefined}
              className={isMobile ? 'mobile-steps' : undefined}
            >
              {steps.map((item, index) => (
                <Step
                  key={item.title}
                  title={isMobile ? undefined : item.title}
                  description={isMobile ? undefined : item.description}
                  icon={item.icon}
                  style={isMobile ? {
                    flex: '0 0 auto',
                    paddingLeft: index === 0 ? 0 : '8px',
                    minWidth: 'auto'
                  } : undefined}
                />
              ))}
            </Steps>
            {isMobile && (
              <style>{`
                .mobile-steps {
                  display: flex !important;
                  justify-content: space-between !important;
                  align-items: center !important;
                  width: 100% !important;
                }
                .mobile-steps .ant-steps-item {
                  padding: 0 !important;
                  flex: 0 0 auto !important;
                  margin: 0 !important;
                  display: flex !important;
                  align-items: center !important;
                }
                .mobile-steps .ant-steps-item-container {
                  padding: 0 !important;
                  display: flex !important;
                  align-items: center !important;
                  order: 1 !important;
                }
                .mobile-steps .ant-steps-item-tail {
                  flex: 1 !important;
                  margin: 0 16px !important;
                  padding: 0 !important;
                  position: relative !important;
                  top: auto !important;
                  left: auto !important;
                  min-width: 20px !important;
                  order: 2 !important;
                }
                .mobile-steps .ant-steps-item:last-child .ant-steps-item-tail {
                  display: none !important;
                }
                .mobile-steps .ant-steps-item-icon {
                  margin: 0 !important;
                }
                .mobile-steps .ant-steps-item-content {
                  display: none !important;
                }
              `}</style>
            )}
          </div>
        </div>
      )}

      {/* 可滚动内容区域 */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: isMobile ? '16px 12px' : '24px',
        maxWidth: 1200,
        margin: '0 auto',
        width: '100%'
      }}>
        {isResumingWizard ? (
          <Card style={{
            textAlign: 'center',
            marginTop: 32,
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
          }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>正在恢复上次的创建进度...</div>
          </Card>
        ) : (
          <div style={{
            background: '#fff',
            padding: isMobile ? 16 : 24,
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
          }}>
            {current === 0 && renderBasicInfo()}
            {current === 1 && renderWorldBuilding()}
            {current === 2 && renderCharacters()}
            {current === 3 && renderOutlineGeneration()}
            {current === 4 && renderComplete()}
          </div>
        )}
      </div>

      {/* SSE加载覆盖层 */}
      <SSELoadingOverlay
        loading={loading}
        progress={progress}
        message={progressMessage}
      />
    </div>
  );
}
    