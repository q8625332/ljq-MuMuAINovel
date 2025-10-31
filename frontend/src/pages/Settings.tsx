import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Form, Input, Button, Select, Slider, InputNumber, message, Space, Typography, Spin, Modal, Tooltip, Alert } from 'antd';
import { SettingOutlined, SaveOutlined, DeleteOutlined, ReloadOutlined, ArrowLeftOutlined, InfoCircleOutlined} from '@ant-design/icons';
import { settingsApi } from '../services/api';
import type { SettingsUpdate } from '../types';

const { Title, Paragraph } = Typography;
const { Option } = Select;

export default function SettingsPage() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [hasSettings, setHasSettings] = useState(false);
  const [isDefaultSettings, setIsDefaultSettings] = useState(false);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string; description: string }>>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [modelsFetched, setModelsFetched] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setInitialLoading(true);
    try {
      const settings = await settingsApi.getSettings();
      form.setFieldsValue(settings);
      
      // 判断是否为默认设置（id='0'表示来自.env的默认配置）
      if (settings.id === '0' || !settings.id) {
        setIsDefaultSettings(true);
        setHasSettings(false);
      } else {
        setIsDefaultSettings(false);
        setHasSettings(true);
      }
    } catch (error: any) {
      // 如果404表示还没有设置，使用默认值
      if (error?.response?.status === 404) {
        setHasSettings(false);
        setIsDefaultSettings(true);
        form.setFieldsValue({
          api_provider: 'openai',
          api_base_url: 'https://api.openai.com/v1',
          model_name: 'gpt-4',
          temperature: 0.7,
          max_tokens: 2000,
        });
      } else {
        message.error('加载设置失败');
      }
    } finally {
      setInitialLoading(false);
    }
  };

  const handleSave = async (values: SettingsUpdate) => {
    setLoading(true);
    try {
      await settingsApi.saveSettings(values);
      message.success('设置已保存');
      setHasSettings(true);
      setIsDefaultSettings(false);
    } catch (error) {
      message.error('保存设置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    Modal.confirm({
      title: '重置设置',
      content: '确定要重置为默认值吗？',
      okText: '确定',
      cancelText: '取消',
      onOk: () => {
        form.setFieldsValue({
          api_provider: 'openai',
          api_key: '',
          api_base_url: 'https://api.openai.com/v1',
          model_name: 'gpt-4',
          temperature: 0.7,
          max_tokens: 2000,
        });
        message.info('已重置为默认值，请点击保存');
      },
    });
  };

  const handleDelete = () => {
    Modal.confirm({
      title: '删除设置',
      content: '确定要删除所有设置吗？此操作不可恢复。',
      okText: '确定',
      cancelText: '取消',
      okType: 'danger',
      onOk: async () => {
        setLoading(true);
        try {
          await settingsApi.deleteSettings();
          message.success('设置已删除');
          setHasSettings(false);
          form.resetFields();
        } catch (error) {
          message.error('删除设置失败');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const apiProviders = [
    { value: 'openai', label: 'OpenAI', defaultUrl: 'https://api.openai.com/v1' },
    { value: 'azure', label: 'Azure OpenAI', defaultUrl: 'https://YOUR-RESOURCE.openai.azure.com' },
    { value: 'anthropic', label: 'Anthropic', defaultUrl: 'https://api.anthropic.com' },
    { value: 'custom', label: '自定义', defaultUrl: '' },
  ];

  const handleProviderChange = (value: string) => {
    const provider = apiProviders.find(p => p.value === value);
    if (provider && provider.defaultUrl) {
      form.setFieldValue('api_base_url', provider.defaultUrl);
    }
    // 清空模型列表，需要重新获取
    setModelOptions([]);
    setModelsFetched(false);
  };

  const handleFetchModels = async (silent: boolean = false) => {
    const apiKey = form.getFieldValue('api_key');
    const apiBaseUrl = form.getFieldValue('api_base_url');
    const provider = form.getFieldValue('api_provider');

    if (!apiKey || !apiBaseUrl) {
      if (!silent) {
        message.warning('请先填写 API 密钥和 API 地址');
      }
      return;
    }

    setFetchingModels(true);
    try {
      const response = await settingsApi.getAvailableModels({
        api_key: apiKey,
        api_base_url: apiBaseUrl,
        provider: provider || 'openai'
      });
      
      setModelOptions(response.models);
      setModelsFetched(true);
      if (!silent) {
        message.success(`成功获取 ${response.count || response.models.length} 个可用模型`);
      }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.detail || '获取模型列表失败';
      if (!silent) {
        message.error(errorMsg);
      }
      setModelOptions([]);
      setModelsFetched(true); // 即使失败也标记为已尝试，避免重复请求
    } finally {
      setFetchingModels(false);
    }
  };

  const handleModelSelectFocus = () => {
    // 如果还没有获取过模型列表，自动获取
    if (!modelsFetched && !fetchingModels) {
      handleFetchModels(true); // silent模式，不显示成功消息
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: window.innerWidth <= 768 ? '20px 16px' : '40px 24px'
    }}>
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
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
                  AI API 设置
                </Title>
              </Space>
            </div>

            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              配置你的AI API接口参数，这些设置将用于小说生成、角色创建等AI功能。
            </Paragraph>

            {/* 默认配置提示 */}
            {isDefaultSettings && (
              <Alert
                message="使用 .env 文件中的默认配置"
                description={
                  <div>
                    <p style={{ margin: '8px 0' }}>
                      当前显示的是从服务器 <code>.env</code> 文件读取的默认配置。
                    </p>
                    <p style={{ margin: '8px 0 0 0' }}>
                      点击"保存设置"后，配置将保存到数据库并同步更新到 <code>.env</code> 文件。
                    </p>
                  </div>
                }
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {/* 已保存配置提示 */}
            {hasSettings && !isDefaultSettings && (
              <Alert
                message="使用已保存的个人配置"
                type="success"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {/* 表单 */}
            <Spin spinning={initialLoading}>
              <Form
                form={form}
                layout="vertical"
                onFinish={handleSave}
                autoComplete="off"
              >
                <Form.Item
                  label={
                    <Space>
                      <span>API 提供商</span>
                      <Tooltip title="选择你的AI服务提供商">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="api_provider"
                  rules={[{ required: true, message: '请选择API提供商' }]}
                >
                  <Select size="large" onChange={handleProviderChange}>
                    {apiProviders.map(provider => (
                      <Option key={provider.value} value={provider.value}>
                        {provider.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item
                  label={
                    <Space>
                      <span>API 密钥</span>
                      <Tooltip title="你的API密钥，将加密存储">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="api_key"
                  rules={[{ required: true, message: '请输入API密钥' }]}
                >
                  <Input.Password
                    size="large"
                    placeholder="sk-..."
                    autoComplete="new-password"
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <Space>
                      <span>API 地址</span>
                      <Tooltip title="API的基础URL地址">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="api_base_url"
                  rules={[
                    { required: true, message: '请输入API地址' },
                    { type: 'url', message: '请输入有效的URL' }
                  ]}
                >
                  <Input
                    size="large"
                    placeholder="https://api.openai.com/v1"
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <Space>
                      <span>模型名称</span>
                      <Tooltip title="AI模型的名称，如 gpt-4, gpt-3.5-turbo">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="model_name"
                  rules={[{ required: true, message: '请输入或选择模型名称' }]}
                >
                  <Select
                    size="large"
                    showSearch
                    placeholder="输入模型名称或点击获取"
                    optionFilterProp="label"
                    loading={fetchingModels}
                    onFocus={handleModelSelectFocus}
                    filterOption={(input, option) =>
                      (option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                      (option?.description ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    dropdownRender={(menu) => (
                      <>
                        {menu}
                        {fetchingModels && (
                          <div style={{ padding: '8px 12px', color: '#8c8c8c', textAlign: 'center' }}>
                            <Spin size="small" /> 正在获取模型列表...
                          </div>
                        )}
                        {!fetchingModels && modelOptions.length === 0 && modelsFetched && (
                          <div style={{ padding: '8px 12px', color: '#ff4d4f', textAlign: 'center' }}>
                            未能获取到模型列表，请检查 API 配置
                          </div>
                        )}
                        {!fetchingModels && modelOptions.length === 0 && !modelsFetched && (
                          <div style={{ padding: '8px 12px', color: '#8c8c8c', textAlign: 'center' }}>
                            点击输入框自动获取模型列表
                          </div>
                        )}
                      </>
                    )}
                    notFoundContent={
                      fetchingModels ? (
                        <div style={{ padding: '8px 12px', textAlign: 'center' }}>
                          <Spin size="small" /> 加载中...
                        </div>
                      ) : (
                        <div style={{ padding: '8px 12px', color: '#8c8c8c', textAlign: 'center' }}>
                          未找到匹配的模型
                        </div>
                      )
                    }
                    suffixIcon={
                      <div
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!fetchingModels) {
                            setModelsFetched(false);
                            handleFetchModels(false);
                          }
                        }}
                        style={{
                          cursor: fetchingModels ? 'not-allowed' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          padding: '0 4px',
                          height: '100%',
                          marginRight: -8
                        }}
                        title="重新获取模型列表"
                      >
                        <Button
                          type="text"
                          size="small"
                          icon={<ReloadOutlined />}
                          loading={fetchingModels}
                          style={{ pointerEvents: 'none' }}
                        >
                          刷新
                        </Button>
                      </div>
                    }
                    options={modelOptions.map(model => ({
                      value: model.value,
                      label: model.label,
                      description: model.description
                    }))}
                    optionRender={(option) => (
                      <div>
                        <div style={{ fontWeight: 500 }}>{option.data.label}</div>
                        {option.data.description && (
                          <div style={{ fontSize: '12px', color: '#8c8c8c' }}>
                            {option.data.description}
                          </div>
                        )}
                      </div>
                    )}
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <Space>
                      <span>温度参数</span>
                      <Tooltip title="控制输出的随机性，值越高越随机（0.0-2.0）">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="temperature"
                >
                  <Slider
                    min={0}
                    max={2}
                    step={0.1}
                    marks={{
                      0: '0.0',
                      0.7: '0.7',
                      1: '1.0',
                      2: '2.0'
                    }}
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <Space>
                      <span>最大 Token 数</span>
                      <Tooltip title="单次请求的最大token数量">
                        <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                      </Tooltip>
                    </Space>
                  }
                  name="max_tokens"
                  rules={[
                    { required: true, message: '请输入最大token数' },
                    { type: 'number', min: 1, max: 32000, message: '请输入1-32000之间的数字' }
                  ]}
                >
                  <InputNumber
                    size="large"
                    style={{ width: '100%' }}
                    min={1}
                    max={32000}
                    placeholder="2000"
                  />
                </Form.Item>

                {/* 操作按钮 */}
                <Form.Item style={{ marginBottom: 0, marginTop: 32 }}>
                  <Space size="middle" style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space>
                      <Button
                        type="primary"
                        size="large"
                        icon={<SaveOutlined />}
                        htmlType="submit"
                        loading={loading}
                        style={{
                          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                          border: 'none'
                        }}
                      >
                        保存设置
                      </Button>
                      <Button
                        size="large"
                        icon={<ReloadOutlined />}
                        onClick={handleReset}
                      >
                        重置
                      </Button>
                    </Space>
                    {hasSettings && (
                      <Button
                        danger
                        size="large"
                        icon={<DeleteOutlined />}
                        onClick={handleDelete}
                        loading={loading}
                      >
                        删除设置
                      </Button>
                    )}
                  </Space>
                </Form.Item>
              </Form>
            </Spin>
          </Space>
        </Card>
      </div>
    </div>
  );
}