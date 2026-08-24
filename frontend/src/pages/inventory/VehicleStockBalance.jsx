import React, { useState, useEffect, useMemo } from 'react';
import { Button, Card, Row, Col, Select, Input, Table, Tag, Typography, Space, message, Tooltip, Popover, List, Modal } from 'antd';
import { SearchOutlined, DownloadOutlined, FilePdfOutlined, BarcodeOutlined, SyncOutlined } from '@ant-design/icons';
import PageHeader from '../../components/PageHeader';
import BarcodeDisplay from '../../components/BarcodeDisplay';
import api from '../../config/api';
import { formatNumber, getErrorMessage, formatDateTime, exportVehicleStockToExcel, printVehicleStockToPDF } from '../../utils/helpers';

const { Text } = Typography;

const VehicleStockBalance = () => {
  const [filterVehicle, setFilterVehicle] = useState(undefined);
  const [filterItem, setFilterItem] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);

  // Barcode / QR display states
  const [barcodeDisplayOpen, setBarcodeDisplayOpen] = useState(false);
  const [barcodeDisplayVal, setBarcodeDisplayVal] = useState('');
  const [barcodeDisplayQRVal, setBarcodeDisplayQRVal] = useState('');
  const [barcodeDisplayLabel, setBarcodeDisplayLabel] = useState('');
  const [barcodeDisplaySub, setBarcodeDisplaySub] = useState('');

  // Fetch all stock data to group on frontend
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await api.get('/inventory/vehicle-stock-balance', {
          params: { page_size: 10000 },
        });
        setData(res.data?.items || res.data || []);
      } catch (err) {
        message.error(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [refreshKey]);

  // Derive vehicle options from fetched data
  const vehicleOptions = useMemo(() => {
    const unique = {};
    data.forEach(item => {
      if (item.vehicle_code && !unique[item.vehicle_code]) {
        unique[item.vehicle_code] = `${item.vehicle_code} (${item.vehicle_number || '-'})`;
      }
    });
    return Object.entries(unique).map(([val, label]) => ({ value: val, label }));
  }, [data]);

  // Group and filter data
  const filteredAndGroupedData = useMemo(() => {
    const term = filterItem.toLowerCase();
    
    // 1. Filter flat items first
    let filteredItems = data;
    if (filterVehicle) {
      filteredItems = filteredItems.filter(item => item.vehicle_code === filterVehicle);
    }
    if (term) {
      filteredItems = filteredItems.filter(item => 
         (item.item_code || '').toLowerCase().includes(term) ||
         (item.item_name || '').toLowerCase().includes(term) ||
         (item.vehicle_code || '').toLowerCase().includes(term) ||
         (item.vehicle_number || '').toLowerCase().includes(term)
      );
    }

    // 2. Group by vehicle
    const groupMap = {};
    filteredItems.forEach(item => {
       if (!groupMap[item.vehicle_code]) {
          groupMap[item.vehicle_code] = {
             vehicle_code: item.vehicle_code,
             vehicle_number: item.vehicle_number,
             items: [],
             total_items: 0,
             last_updated: null
          };
       }
       groupMap[item.vehicle_code].items.push(item);
       groupMap[item.vehicle_code].total_items += 1;
       
       if (item.last_updated) {
         const currentLast = groupMap[item.vehicle_code].last_updated;
         if (!currentLast || new Date(item.last_updated) > new Date(currentLast)) {
           groupMap[item.vehicle_code].last_updated = item.last_updated;
         }
       }
    });
    
    return Object.values(groupMap).sort((a, b) => a.vehicle_code.localeCompare(b.vehicle_code));
  }, [data, filterVehicle, filterItem]);

  const handleExportGlobalExcel = () => {
    if (filteredAndGroupedData.length === 0) return message.warning('No data to export');
    const flatItems = filteredAndGroupedData.flatMap(g => g.items);
    exportVehicleStockToExcel(flatItems);
    message.success('Vehicle Stock Balance exported to Excel successfully');
  };

  const handlePrintGlobalPDF = () => {
    if (filteredAndGroupedData.length === 0) return message.warning('No data to print');
    const flatItems = filteredAndGroupedData.flatMap(g => g.items);
    printVehicleStockToPDF(flatItems);
    message.success('Vehicle Stock Balance PDF report opened successfully');
  };

  const mainColumns = [
    {
      title: 'Vehicle Code',
      dataIndex: 'vehicle_code',
      key: 'vehicle_code',
      width: 140,
      sorter: (a, b) => a.vehicle_code.localeCompare(b.vehicle_code),
    },
    {
      title: 'Vehicle Number',
      dataIndex: 'vehicle_number',
      key: 'vehicle_number',
      width: 140,
      render: (v) => v || '-',
    },
    {
      title: 'Unique Items',
      dataIndex: 'total_items',
      key: 'total_items',
      width: 120,
      render: (v) => <Tag color="blue">{v} Items</Tag>,
    },
    {
      title: 'Last Updated',
      dataIndex: 'last_updated',
      key: 'last_updated',
      width: 160,
      render: (v) => formatDateTime(v),
    },
  ];

  const expandedRowRender = (record) => {
    const itemColumns = [
      {
        title: 'Item Code',
        dataIndex: 'item_code',
        key: 'item_code',
        width: 150,
        sorter: (a, b) => (a.item_code || '').localeCompare(b.item_code || ''),
      },
      {
        title: 'Item Name',
        dataIndex: 'item_name',
        key: 'item_name',
        width: 250,
      },
      {
        title: 'Quantity',
        dataIndex: 'qty',
        key: 'qty',
        width: 120,
        align: 'right',
        sorter: (a, b) => Number(a.qty || 0) - Number(b.qty || 0),
        render: (v) => <Text strong>{formatNumber(v || 0)}</Text>,
      },
      {
        title: 'UOM',
        dataIndex: 'uom_name',
        key: 'uom',
        width: 100,
        render: (v) => v || '-',
      },
      {
        title: 'Asset/Consumable Code',
        key: 'asset_codes',
        width: 160,
        render: (_, itemRecord) => {
          const isAsset = itemRecord.item_type === 'asset';
          const isConsumable = itemRecord.item_type === 'consumable';
          const list = (itemRecord.asset_codes && itemRecord.asset_codes.length > 0)
            ? itemRecord.asset_codes
            : ((itemRecord.consumable_codes && itemRecord.consumable_codes.length > 0)
              ? itemRecord.consumable_codes
              : (itemRecord.serial_numbers || []));

          if (!list || list.length === 0) return <Text type="secondary">-</Text>;

          const popoverTitle = isAsset ? "Asset Codes" : (isConsumable ? "Consumable Codes" : "Serial / Asset Codes");
          const popoverContent = (
            <div style={{ maxHeight: 200, overflowY: 'auto', minWidth: 200 }}>
              <List
                size="small"
                dataSource={list}
                renderItem={(code) => (
                  <List.Item 
                    style={{ padding: '4px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <Tag color={isAsset ? "cyan" : (isConsumable ? "orange" : "blue")}>{code}</Tag>
                    <Tooltip title="View Barcode / QR Code">
                      <Button 
                        type="text" 
                        size="small" 
                        icon={<BarcodeOutlined style={{ color: '#1890ff' }} />} 
                        onClick={(e) => {
                          e.stopPropagation(); // Prevent expanding/collapsing row when clicking button inside table
                          setBarcodeDisplayVal(code);
                          setBarcodeDisplayLabel(itemRecord.item_name || '');
                          setBarcodeDisplaySub(`${itemRecord.item_code || ''} | Vehicle: ${itemRecord.vehicle_code || '-'}`);
                          setBarcodeDisplayQRVal(`Code: ${code}\nVehicle Code: ${itemRecord.vehicle_code || '-'}\nVehicle Number: ${itemRecord.vehicle_number || '-'}\nItem Code: ${itemRecord.item_code || '-'}\nItem Name: ${itemRecord.item_name || '-'}`);
                          setBarcodeDisplayOpen(true);
                        }} 
                      />
                    </Tooltip>
                  </List.Item>
                )}
              />
            </div>
          );

          return (
            <div onClick={e => e.stopPropagation()}>
              <Popover
                content={popoverContent}
                title={popoverTitle}
                trigger="click"
                placement="bottom"
              >
                <Button type="link" size="small" style={{ padding: 0 }}>
                  View ({list.length})
                </Button>
              </Popover>
            </div>
          );
        },
      },
    ];

    return (
      <div style={{ padding: '16px 24px', backgroundColor: '#fafafa', border: '1px solid #f0f0f0', borderRadius: '4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Text strong style={{ fontSize: 16, color: '#0d9488' }}>
            Items in Vehicle: {record.vehicle_code}
          </Text>
          <Space>
            <Button 
              size="small" 
              icon={<DownloadOutlined />} 
              onClick={() => {
                 exportVehicleStockToExcel(record.items);
                 message.success(`Vehicle ${record.vehicle_code} Stock exported to Excel successfully`);
              }}
            >
              Export Excel
            </Button>
            <Button 
              size="small" 
              icon={<FilePdfOutlined />} 
              onClick={() => {
                 printVehicleStockToPDF(record.items);
                 message.success(`Vehicle ${record.vehicle_code} Stock PDF report opened successfully`);
              }}
            >
              Print PDF
            </Button>
          </Space>
        </div>
        <Table 
          columns={itemColumns}
          dataSource={record.items}
          pagination={false}
          rowKey="id"
          size="small"
        />
      </div>
    );
  };

  return (
    <div style={{ padding: '24px' }}>
      <PageHeader title="Vehicle Stock Balance" subtitle="View and track materials currently stored in vehicles">
        <Space>
          <Button type="primary" icon={<DownloadOutlined />} onClick={handleExportGlobalExcel} disabled={loading}>
            Export to Excel
          </Button>
          <Button type="primary" style={{ backgroundColor: '#0d9488', borderColor: '#0d9488' }} icon={<FilePdfOutlined />} onClick={handlePrintGlobalPDF} disabled={loading}>
            Print / Export PDF
          </Button>
        </Space>
      </PageHeader>

      <Card
        bordered={false}
        style={{ marginBottom: 16, borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Row justify="space-between" align="middle">
          <Col>
            <Space size="middle" wrap>
              <Select
                placeholder="Filter by Vehicle"
                allowClear
                showSearch
                optionFilterProp="label"
                style={{ width: 220 }}
                value={filterVehicle}
                onChange={(v) => setFilterVehicle(v)}
                options={vehicleOptions}
              />
              <Input
                placeholder="Search items or vehicles..."
                allowClear
                prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
                style={{ width: 260 }}
                value={filterItem}
                onChange={(e) => setFilterItem(e.target.value)}
              />
            </Space>
          </Col>
          <Col>
            <Button 
              icon={<SyncOutlined />} 
              onClick={() => setRefreshKey(k => k + 1)}
              loading={loading}
            >
              Refresh Data
            </Button>
          </Col>
        </Row>
      </Card>

      <Table
        columns={mainColumns}
        dataSource={filteredAndGroupedData}
        rowKey="vehicle_code"
        loading={loading}
        expandable={{ expandedRowRender, expandRowByClick: true }}
        pagination={{
          defaultPageSize: 20,
          showSizeChanger: true,
          showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} vehicles`,
        }}
        scroll={{ x: 800 }}
      />

      {/* Barcode / QR Code Viewer Modal */}
      <Modal
        title="Barcode / QR Code Viewer"
        open={barcodeDisplayOpen}
        onCancel={() => setBarcodeDisplayOpen(false)}
        footer={[
          <Button key="close" onClick={() => setBarcodeDisplayOpen(false)}>Close</Button>
        ]}
        width={360}
        centered
        destroyOnClose
      >
        <div style={{ display: 'flex', justifyContent: 'center', padding: '20px 0' }}>
          <BarcodeDisplay
            value={barcodeDisplayVal}
            qrValue={barcodeDisplayQRVal}
            type="CODE128"
            label={barcodeDisplayLabel}
            subtitle={barcodeDisplaySub}
            height={80}
            qrSize={140}
          />
        </div>
      </Modal>
    </div>
  );
};

export default VehicleStockBalance;
