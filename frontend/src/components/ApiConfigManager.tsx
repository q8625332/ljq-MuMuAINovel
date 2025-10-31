import React, { useState, useEffect, useMemo } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  message,
  Popconfirm,
  Tag,
  Space,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
  ReloadOutlined,
} from '@ant-design/icons';
import { apiConfigApi, settingsApi } from '../services/api';
import type { ApiConfig, ApiConfigCreate, ApiConfigUpdate } from '../types';

const { Option } = Select;

// 扩展ApiConfig类型以支持系统配置标识
interface ExtendedApiConfig extends ApiConfig {
  is_system?: boolean;
}

const ApiConfigManager: React.FC = () => {
  const [configs, setConfigs] = useState<ApiConfig[]>([]);
  const [systemConfig, setSystemConfig] = useState<ExtendedApiConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ApiConfig | null>(null);
  const [form] = Form.useForm();
  
  // 模型列表相关状态
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string; description: string }>>([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  // 加载API配置列表（包括系统环境变量配置）
  const loadConfigs = async () => {
    setLoading(true);
    try {
      // 1. 加载用户创建的配置
      const data = await apiConfigApi.getApiConfigs();
      setConfigs(data);
      
      // 2. 尝试加载系统环境变量配置
      try {
        const settings = await settingsApi.getSettings();
        if (settings && settings.api_key) {
          const systemCfg: ExtendedApiConfig = {
            id: 'system-env-config',
            user_id: settings.user_id,
            name: '系统环境变量配置',
            api_provider: settings.api_provider,
            api_key: settings.api_key,
            api_base_url: settings.api_base_url,
            model_name: settings.model_name,
            temperature: settings.temperature,
            max_tokens: settings.max_tokens,
            is_default: false,
            is_system: true,
            created_at: settings.created_at,
            updated_at: settings.updated_at,
          };
          setSystemConfig(systemCfg);
        }
      } catch (error) {
        console.log('未找到系统环境变量配置');
        setSystemConfig(null);
      }
    } catch (error) {
      console.error('加载API配置失败:', error);
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfigs();
  }, []);

  // 获取模型列表
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
      const response = await apiConfigApi.refreshModels({
        api_key: apiKey,
        api_base_url: apiBaseUrl,
        api_provider: provider || 'openai'
      });
      
      // 转换后端返回的字符串数组为前端所需的格式
      const formattedModels = response.models.map(model => ({
        value: model,
        label: model,
        description: model
      }));
      
      setModelOptions(formattedModels);
      if (!silent) {
        message.success(`成功获取 ${response.count} 个可用模型`);
      }
    } catch (error: unknown) {
      const errorMsg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '获取模型列表失败';
      if (!silent) {
        message.error(errorMsg);
      }
      setModelOptions([]);
    } finally {
      setFetchingModels(false);
    }
  };

  // 合并系统配置和用户配置
  const allConfigs = useMemo(() => {
    const list: ExtendedApiConfig[] = [...configs];
    if (systemConfig) {
      list.unshift(systemConfig); // 系统配置放在最前面
    }
    return list;
  }, [configs, systemConfig]);

  // 打开新增/编辑弹窗
  const handleOpenModal = (config?: ApiConfig | ExtendedApiConfig) => {
    // 系统配置不允许编辑
    if (config && (config as ExtendedApiConfig).is_system) {
      message.warning('系统环境变量配置不支持编辑');
      return;
    }
    
    if (config) {
      setEditingConfig(config);
      form.setFieldsValue({
        name: config.name,
        api_provider: config.api_provider,
        api_key: config.api_key,
        api_base_url: config.api_base_url,
        model_name: config.model_name,
        temperature: config.temperature,
        max_tokens: config.max_tokens,
      });
      // 编辑时自动静默获取模型列表
      handleFetchModels(true);
    } else {
      setEditingConfig(null);
      form.resetFields();
      // 设置默认值
      form.setFieldsValue({
        temperature: 0.7,
        max_tokens: 2000,
      });
    }
    setModelOptions([]);
    setModalVisible(true);
  };

  // 关闭弹窗
  const handleCloseModal = () => {
    setModalVisible(false);
    setEditingConfig(null);
    form.resetFields();
  };

  // 保存配置
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingConfig) {
        // 更新
        await apiConfigApi.updateApiConfig(editingConfig.id, values as ApiConfigUpdate);
        message.success('更新成功');
      } else {
        // 新增
        await apiConfigApi.createApiConfig(values as ApiConfigCreate);
        message.success('创建成功');
      }
      
      handleCloseModal();
      loadConfigs();
    } catch (error) {
      console.error('保存失败:', error);
    }
  };

  // 删除配置
  const handleDelete = async (id: string) => {
    try {
      await apiConfigApi.deleteApiConfig(id);
      message.success('删除成功');
      loadConfigs();
    } catch (error) {
      console.error('删除失败:', error);
    }
  };

  // 设置为默认配置
  const handleSetDefault = async (id: string) => {
    try {
      await apiConfigApi.setDefaultApiConfig(id);
      message.success('设置默认配置成功');
      loadConfigs();
    } catch (error) {
      console.error('设置默认配置失败:', error);
    }
  };

  const columns = [
    {
      title: '配置名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (text: string, record: ExtendedApiConfig) => (
        <Space>
          <span>{text}</span>
          {record.is_system && (
            <Tag color="gold">系统内置</Tag>
          )}
          {record.is_default && (
            <Tag color="blue" icon={<StarFilled />}>
              默认
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'API提供商',
      dataIndex: 'api_provider',
      key: 'api_provider',
      width: 120,
      render: (text: string) => {
        const providerMap: Record<string, { color: string; label: string }> = {
          openai: { color: 'green', label: 'OpenAI' },
          anthropic: { color: 'purple', label: 'Anthropic' },
          gemini: { color: 'blue', label: 'Gemini' },
        };
        const provider = providerMap[text] || { color: 'default', label: text };
        return <Tag color={provider.color}>{provider.label}</Tag>;
      },
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      width: 150,
      ellipsis: true,
    },
    {
      title: 'Base URL',
      dataIndex: 'api_base_url',
      key: 'api_base_url',
      width: 200,
      ellipsis: true,
      render: (text: string) => (
        <Tooltip title={text}>
          <span>{text || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: 'Temperature',
      dataIndex: 'temperature',
      key: 'temperature',
      width: 100,
      align: 'center' as const,
    },
    {
      title: 'Max Tokens',
      dataIndex: 'max_tokens',
      key: 'max_tokens',
      width: 100,
      align: 'center' as const,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      fixed: 'right' as const,
      render: (_: unknown, record: ExtendedApiConfig) => {
        const isSystem = record.is_system;
        
        return (
          <Space size="small">
            {!record.is_default && !isSystem && (
              <Tooltip title="设为默认">
                <Button
                  type="link"
                  size="small"
                  icon={<StarOutlined />}
                  onClick={() => handleSetDefault(record.id)}
                />
              </Tooltip>
            )}
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleOpenModal(record)}
              disabled={isSystem}
            >
              编辑
            </Button>
            <Popconfirm
              title="确定要删除这个配置吗？"
              onConfirm={() => handleDelete(record.id)}
              okText="确定"
              cancelText="取消"
              disabled={isSystem}
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={isSystem}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => handleOpenModal()}
        >
          新增配置
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={allConfigs}
        loading={loading}
        rowKey="id"
        scroll={{ x: 1200 }}
        pagination={{
          pageSize: 10,
          showTotal: (total) => `共 ${total} 条`,
        }}
      />

      <Modal
        title={editingConfig ? '编辑API配置' : '新增API配置'}
        open={modalVisible}
        onOk={handleSave}
        onCancel={handleCloseModal}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          autoComplete="off"
        >
          <Form.Item
            label="配置名称"
            name="name"
            rules={[
              { required: true, message: '请输入配置名称' },
              { min: 1, max: 100, message: '名称长度为1-100个字符' },
            ]}
          >
            <Input placeholder="例如: GPT-4 生产环境" />
          </Form.Item>

          <Form.Item
            label="API提供商"
            name="api_provider"
            rules={[{ required: true, message: '请选择API提供商' }]}
          >
            <Select placeholder="请选择">
              <Option value="openai">OpenAI</Option>
              <Option value="anthropic">Anthropic</Option>
              <Option value="gemini">Gemini</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="API Key"
            name="api_key"
            rules={[{ required: true, message: '请输入API Key' }]}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>

          <Form.Item
            label="Base URL"
            name="api_base_url"
            rules={[{ required: true, message: '请输入Base URL' }]}
          >
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>

          <Form.Item
            label="模型名称"
            name="model_name"
            rules={[{ required: true, message: '请选择或输入模型名称' }]}
          >
            <Space.Compact style={{ width: '100%' }}>
              <Select
                placeholder="请选择或输入模型名称"
                showSearch
                allowClear
                loading={fetchingModels}
                options={modelOptions}
                notFoundContent={fetchingModels ? '加载中...' : '请先获取模型列表或直接输入'}
                style={{ width: '100%' }}
                onSelect={(value: string) => {
                  form.setFieldsValue({ model_name: value });
                }}
                onChange={(value: string) => {
                  form.setFieldsValue({ model_name: value });
                }}
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    {modelOptions.length === 0 && !fetchingModels && (
                      <div style={{ padding: '8px', textAlign: 'center', color: '#999' }}>
                        点击右侧刷新按钮获取模型列表
                      </div>
                    )}
                  </>
                )}
              />
              <Tooltip title="获取可用模型列表">
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => handleFetchModels(false)}
                  loading={fetchingModels}
                />
              </Tooltip>
            </Space.Compact>
          </Form.Item>

          <Form.Item
            label="Temperature"
            name="temperature"
            rules={[
              { required: true, message: '请输入Temperature' },
              { type: 'number', min: 0, max: 2, message: '取值范围: 0-2' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              max={2}
              step={0.1}
              placeholder="0.7"
            />
          </Form.Item>

          <Form.Item
            label="Max Tokens"
            name="max_tokens"
            rules={[
              { required: true, message: '请输入Max Tokens' },
              { type: 'number', min: 1, max: 100000, message: '取值范围: 1-100000' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              min={1}
              max={100000}
              step={100}
              placeholder="2000"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ApiConfigManager;