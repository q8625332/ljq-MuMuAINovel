import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Space, Typography, Alert, Divider, Upload, message, Modal, Descriptions, Statistic, Row, Col } from 'antd';
import { DownloadOutlined, UploadOutlined, InfoCircleOutlined, ExclamationCircleOutlined, CloudDownloadOutlined, DatabaseOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;
const { confirm } = Modal;

interface ExportInfo {
  user_id: number;
  data_summary: {
    projects: number;
    characters: number;
    chapters: number;
    outlines: number;
    relationships: number;
    organizations: number;
    organization_members: number;
    generation_history: number;
  };
  total_records: number;
}

const DataManagement: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [exportInfo, setExportInfo] = useState<ExportInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(false);

  // 获取导出信息
  const fetchExportInfo = async () => {
    setInfoLoading(true);
    try {
      const response = await axios.get('/api/export-info');
      setExportInfo(response.data);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '获取数据统计失败');
    } finally {
      setInfoLoading(false);
    }
  };

  useEffect(() => {
    fetchExportInfo();
  }, []);

  // 导出数据
  const handleExport = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/export-data', {
        responseType: 'blob', // 重要：指定响应类型为blob
      });

      // 从响应头获取文件名
      const contentDisposition = response.headers['content-disposition'];
      let filename = 'mumuai_backup.json';
      if (contentDisposition) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
        if (matches && matches[1]) {
          filename = matches[1].replace(/['"]/g, '');
        }
      }

      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      message.success('数据导出成功！');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '数据导出失败');
    } finally {
      setLoading(false);
    }
  };

  // 导入数据（追加模式）
  const handleImport = async (file: File, replace: boolean = false) => {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`/api/import-data?replace=${replace}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      message.success(`数据导入成功！(${response.data.mode})`);
      
      // 刷新统计信息
      await fetchExportInfo();
      
      // 提示用户刷新页面
      Modal.info({
        title: '导入成功',
        content: '数据已成功导入，建议刷新页面查看最新数据。',
        okText: '刷新页面',
        onOk: () => {
          window.location.reload();
        },
      });
    } catch (error: any) {
      message.error(error.response?.data?.detail || '数据导入失败');
    } finally {
      setLoading(false);
    }
  };

  // 确认导入（追加模式）
  const confirmImportAppend = (file: File) => {
    confirm({
      title: '确认导入数据（追加模式）',
      icon: <InfoCircleOutlined />,
      content: (
        <div>
          <Paragraph>
            即将以<Text strong>追加模式</Text>导入数据，这将：
          </Paragraph>
          <ul>
            <li>保留现有的所有数据</li>
            <li>将备份文件中的数据追加到数据库</li>
            <li>可能导致数据重复（如果重复导入同一文件）</li>
          </ul>
          <Alert
            message="注意"
            description="追加模式适合恢复部分数据或合并多个备份，但请注意避免重复导入。"
            type="info"
            showIcon
            style={{ marginTop: 12 }}
          />
        </div>
      ),
      okText: '确认导入',
      cancelText: '取消',
      onOk: () => handleImport(file, false),
    });
  };

  // 确认导入（替换模式）
  const confirmImportReplace = (file: File) => {
    confirm({
      title: '确认导入数据（替换模式）',
      icon: <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />,
      content: (
        <div>
          <Paragraph>
            即将以<Text strong type="danger">替换模式</Text>导入数据，这将：
          </Paragraph>
          <ul>
            <li style={{ color: '#ff4d4f' }}>清空现有的所有数据</li>
            <li>从备份文件完全恢复数据</li>
            <li>此操作不可撤销</li>
          </ul>
          <Alert
            message="警告"
            description="替换模式将永久删除现有数据！建议先导出当前数据作为备份。"
            type="error"
            showIcon
            style={{ marginTop: 12 }}
          />
        </div>
      ),
      okText: '确认清空并导入',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleImport(file, true),
    });
  };

  // Upload组件配置
  const uploadProps: UploadProps = {
    beforeUpload: (file) => {
      // 验证文件类型
      const isJSON = file.type === 'application/json' || file.name.endsWith('.json');
      if (!isJSON) {
        message.error('只能上传JSON格式的备份文件！');
        return false;
      }

      // 显示导入模式选择对话框
      const modal = Modal.confirm({
        title: '选择导入模式',
        icon: <InfoCircleOutlined />,
        content: (
          <div>
            <Paragraph>
              请选择导入模式：
            </Paragraph>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Card size="small" hoverable onClick={() => {
                modal.destroy();
                confirmImportAppend(file);
              }}>
                <Space>
                  <CloudDownloadOutlined style={{ fontSize: 24, color: '#1890ff' }} />
                  <div>
                    <Text strong>追加模式（推荐）</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      保留现有数据，追加新数据
                    </Text>
                  </div>
                </Space>
              </Card>
              
              <Card size="small" hoverable onClick={() => {
                modal.destroy();
                confirmImportReplace(file);
              }}>
                <Space>
                  <DatabaseOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
                  <div>
                    <Text strong type="danger">替换模式</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      清空现有数据，完全恢复备份
                    </Text>
                  </div>
                </Space>
              </Card>
            </Space>
          </div>
        ),
        footer: null,
        width: 500,
      });

      return false; // 阻止自动上传
    },
    showUploadList: false,
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/settings')}
          type="text"
          size="large"
          style={{ marginRight: 16 }}
        >
          返回
        </Button>
        <Title level={2} style={{ margin: 0 }}>
          <DatabaseOutlined /> 数据管理
        </Title>
      </div>
      <Paragraph type="secondary">
        导出或导入您的所有数据，用于备份、迁移或版本升级。
      </Paragraph>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={24}>
          <Card loading={infoLoading}>
            <Statistic 
              title="数据总量" 
              value={exportInfo?.total_records || 0} 
              suffix="条记录"
              prefix={<DatabaseOutlined />}
            />
            
            {exportInfo && (
              <Descriptions column={4} size="small" style={{ marginTop: 16 }}>
                <Descriptions.Item label="项目">{exportInfo.data_summary.projects}</Descriptions.Item>
                <Descriptions.Item label="角色">{exportInfo.data_summary.characters}</Descriptions.Item>
                <Descriptions.Item label="章节">{exportInfo.data_summary.chapters}</Descriptions.Item>
                <Descriptions.Item label="大纲">{exportInfo.data_summary.outlines}</Descriptions.Item>
                <Descriptions.Item label="关系">{exportInfo.data_summary.relationships}</Descriptions.Item>
                <Descriptions.Item label="组织">{exportInfo.data_summary.organizations}</Descriptions.Item>
                <Descriptions.Item label="成员">{exportInfo.data_summary.organization_members}</Descriptions.Item>
                <Descriptions.Item label="历史">{exportInfo.data_summary.generation_history}</Descriptions.Item>
              </Descriptions>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card 
            title={<><DownloadOutlined /> 导出数据</>}
            extra={<InfoCircleOutlined />}
          >
            <Paragraph>
              将您的所有数据导出为JSON格式的备份文件，包括：
            </Paragraph>
            <ul>
              <li>所有项目及其设定</li>
              <li>角色、章节、大纲</li>
              <li>角色关系、组织信息</li>
              <li>生成历史和个人设置</li>
            </ul>
            <Alert
              message="导出说明"
              description="导出的数据文件包含完整的数据结构和版本信息，可用于版本升级或迁移到其他设备。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Button 
              type="primary" 
              icon={<DownloadOutlined />}
              onClick={handleExport}
              loading={loading}
              size="large"
              block
            >
              导出所有数据
            </Button>
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card 
            title={<><UploadOutlined /> 导入数据</>}
            extra={<InfoCircleOutlined />}
          >
            <Paragraph>
              从备份文件恢复数据，支持两种导入模式：
            </Paragraph>
            <ul>
              <li><Text strong>追加模式：</Text>保留现有数据，追加新数据</li>
              <li><Text strong type="danger">替换模式：</Text>清空现有数据，完全恢复备份</li>
            </ul>
            <Alert
              message="导入提醒"
              description="导入前建议先导出当前数据作为备份。导入过程中请勿关闭页面。"
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Upload {...uploadProps}>
              <Button 
                icon={<UploadOutlined />}
                loading={loading}
                size="large"
                block
              >
                选择备份文件
              </Button>
            </Upload>
          </Card>
        </Col>
      </Row>

      <Divider />

      <Card title="使用说明" size="small">
        <Title level={5}>什么时候需要导出数据？</Title>
        <ul>
          <li>定期备份数据，防止数据丢失</li>
          <li>系统版本升级前，保存现有数据</li>
          <li>迁移到新设备或新服务器</li>
          <li>与他人分享您的创作数据</li>
        </ul>

        <Title level={5}>导入模式说明</Title>
        <Paragraph>
          <Text strong>追加模式（推荐）：</Text>
          <ul>
            <li>保留所有现有数据</li>
            <li>将备份文件的数据添加到数据库中</li>
            <li>适合恢复部分删除的数据或合并多个备份</li>
            <li>注意：重复导入同一文件会导致数据重复</li>
          </ul>
        </Paragraph>

        <Paragraph>
          <Text strong type="danger">替换模式（谨慎使用）：</Text>
          <ul>
            <li>删除所有现有数据（不可恢复）</li>
            <li>完全按照备份文件恢复数据</li>
            <li>适合版本升级后的数据恢复或完全重置</li>
            <li>强烈建议在使用前先导出当前数据</li>
          </ul>
        </Paragraph>

        <Alert
          message="数据安全提示"
          description={
            <div>
              <p>1. 建议定期导出数据并妥善保管备份文件</p>
              <p>2. 备份文件包含敏感信息，请注意保密</p>
              <p>3. 导入前请确认备份文件的来源和完整性</p>
              <p>4. 如遇到导入失败，请检查备份文件格式是否正确</p>
            </div>
          }
          type="info"
          showIcon
          style={{ marginTop: 16 }}
        />
      </Card>
    </div>
  );
};

export default DataManagement;