import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Button, Form, Input, InputNumber, Select, Space, Table,
  DatePicker, Tag, Divider, Row, Col, Spin, message,
} from 'antd';
import { ArrowLeftOutlined, PlusOutlined, DeleteOutlined, SearchOutlined, DownloadOutlined, PrinterOutlined } from '@ant-design/icons';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import dayjs from 'dayjs';
import * as XLSX from 'xlsx-js-style';
import PageHeader from '../../components/PageHeader';
import api from '../../config/api';
import { getErrorMessage, formatDateForAPI, parseDateForPicker } from '../../utils/helpers';
import { useReactToPrint } from 'react-to-print';
import { MaterialInwardPrint } from '../../components/PrintTemplates';

const MaterialInwardForm = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = !id || id === 'new';

  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editMode, setEditMode] = useState(location.state?.edit || false);
  const [inwardStatus, setInwardStatus] = useState(null);
  const [fullData, setFullData] = useState({});

  const printRef = useRef();
  const handlePrint = useReactToPrint({
    content: () => printRef.current,
    documentTitle: `Material_Inward_${form.getFieldValue('inward_number') || 'Draft'}`,
  });

  // Lookups
  const [warehouses, setWarehouses] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [itemMaster, setItemMaster] = useState([]);
  const [uoms, setUoms] = useState([]);
  const [poList, setPoList] = useState([]);
  const [fetchingPoList, setFetchingPoList] = useState(false);
  const [poLoading, setPoLoading] = useState(false);

  // Items table state
  const [items, setItems] = useState([]);

  useEffect(() => {
    fetchLookups();
    if (!isNew) {
      fetchInward();
    } else {
      form.setFieldsValue({ received_date: dayjs() });
      setItems([{ key: Date.now(), item_id: null, item_name_manual: '', ordered_qty: 0, received_qty: 0, uom_id: null, uom_manual: '', remarks: '' }]);
    }
  }, [id, isNew]);

  const fetchLookups = async () => {
    fetchActivePOs();
    fetchWarehouses();
    fetchVendors();
    fetchItemMaster();
    fetchUOMs();
  };

  const fetchActivePOs = async () => {
    setFetchingPoList(true);
    try {
      const res = await api.get('/procurement/purchase-orders', {
        params: { page_size: 500, status: 'approved,accepted,partially_received' }
      });
      const data = res.data;
      const list = data.items || data.data || (Array.isArray(data) ? data : []);
      setPoList(list.map((po) => ({
        label: `${po.po_number}${po.supplier_acknowledgement === 'accepted' ? ' ✓' : ''}`,
        value: po.po_number,
        po_id: po.id,
      })));
    } catch { /* silent */ }
    finally { setFetchingPoList(false); }
  };

  const fetchWarehouses = async () => {
    try {
      const res = await api.get('/masters/warehouses', { params: { page_size: 500 } });
      const data = res.data;
      const list = data.items || data.data || (Array.isArray(data) ? data : []);
      setWarehouses(list.map((w) => ({ label: w.name, value: w.id })));
    } catch { /* silent */ }
  };

  const fetchVendors = async () => {
    try {
      const res = await api.get('/masters/vendors', { params: { page_size: 500 } });
      const data = res.data;
      const list = data.items || data.data || (Array.isArray(data) ? data : []);
      setVendors(list.map((v) => ({ label: `${v.vendor_code} - ${v.name}`, value: v.id })));
    } catch { /* silent */ }
  };

  const fetchItemMaster = async () => {
    try {
      const res = await api.get('/masters/items', { params: { page_size: 1000 } });
      const data = res.data;
      const list = data.items || data.data || (Array.isArray(data) ? data : []);
      setItemMaster(list.map((i) => ({
        label: `${i.item_code} - ${i.name}`,
        value: i.id,
        uom_id: i.primary_uom_id,
      })));
    } catch { /* silent */ }
  };

  const fetchUOMs = async () => {
    try {
      const res = await api.get('/masters/uom', { params: { page_size: 200 } });
      const data = res.data;
      const list = data.items || data.data || (Array.isArray(data) ? data : []);
      setUoms(list.map((u) => ({ label: `${u.name} (${u.abbreviation || ''})`, value: u.id })));
    } catch { /* silent */ }
  };

  const fetchInward = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/warehouse/inwards/${id}`);
      const data = res.data;
      setInwardStatus(data.status);
      setFullData(data);
      form.setFieldsValue({
        ...data,
        received_date: parseDateForPicker(data.received_date),
      });
      setItems((data.items || []).map((it, idx) => ({ ...it, key: it.id || idx })));
    } catch (err) {
      message.error(getErrorMessage(err));
      navigate('/warehouse/material-inward');
    } finally {
      setLoading(false);
    }
  };

  const handleFetchPO = async (poNumberArg) => {
    const poNumber = poNumberArg || form.getFieldValue('po_number');
    if (!poNumber) {
      message.warning('Enter or select a PO number first');
      return;
    }
    setPoLoading(true);
    try {
      const res = await api.get(`/warehouse/inwards/fetch-po/${poNumber}`);
      const po = res.data;
      form.setFieldsValue({
        po_id: po.po_id,
        vendor_id: po.vendor_id,
      });
      const poItems = (po.items || []).map((pi, idx) => ({
        key: Date.now() + idx,
        item_id: pi.item_id,
        item_code: pi.item_code,
        item_name: pi.item_name,
        item_name_manual: '',
        ordered_qty: pi.ordered_qty,
        received_qty: pi.pending_qty,
        uom_id: pi.uom_id,
        uom_name: pi.uom_name,
        uom_manual: '',
        remarks: '',
      }));
      setItems(poItems);
      message.success(`PO ${poNumber} loaded with ${poItems.length} item(s)`);
    } catch (err) {
      message.error(getErrorMessage(err));
    } finally {
      setPoLoading(false);
    }
  };

  const handleAddItem = () => {
    setItems((prev) => [...prev, {
      key: Date.now(),
      item_id: null,
      item_name_manual: '',
      ordered_qty: 0,
      received_qty: 0,
      uom_id: null,
      uom_manual: '',
      remarks: '',
    }]);
  };

  const handleRemoveItem = (key) => {
    setItems((prev) => prev.filter((i) => i.key !== key));
  };

  const handleItemFieldChange = (key, field, value) => {
    if (field === 'item_id' && value) {
      const exists = items.some((i) => i.key !== key && String(i.item_id) === String(value));
      if (exists) {
        const master = itemMaster.find((m) => String(m.value) === String(value));
        let itemName = 'Item';
        if (master) {
          itemName = master.label.includes(' - ') ? master.label.split(' - ').slice(1).join(' - ') : master.label;
        }
        message.warning(`${itemName} already added. Just increase that qty.`);
        return;
      }
    }

    setItems((prev) => prev.map((i) => {
      if (i.key !== key) return i;
      const updated = { ...i, [field]: value };
      if (field === 'item_id') {
        if (value) {
          const master = itemMaster.find((m) => String(m.value) === String(value));
          if (master) {
            if (master.uom_id) updated.uom_id = master.uom_id;
            const parts = master.label.split(' - ');
            updated.item_code = parts[0];
            updated.item_name = parts.slice(1).join(' - ');
          }
        } else {
          updated.item_code = '';
          updated.item_name = '';
        }
      }
      if (field === 'uom_id') {
        if (value) {
          const uomObj = uoms.find((u) => String(u.value) === String(value));
          if (uomObj) {
            updated.uom_name = uomObj.label;
          }
        } else {
          updated.uom_name = '';
        }
      }
      return updated;
    }));
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (items.length === 0) {
        message.error('Add at least one item');
        return;
      }
      const validItems = items.filter((i) => i.item_id);
      if (validItems.length === 0) {
        message.error('Each item must have a linked item');
        return;
      }
      const payload = {
        po_id: values.po_id || null,
        po_number: values.po_number || null,
        vendor_id: values.vendor_id || null,
        vendor_name_manual: values.vendor_name_manual || null,
        warehouse_id: values.warehouse_id,
        received_date: formatDateForAPI(values.received_date) || formatDateForAPI(dayjs()),
        vehicle_number: values.vehicle_number || null,
        driver_name: values.driver_name || null,
        remarks: values.remarks || null,
        items: validItems.map((i) => ({
          item_id: i.item_id || null,
          item_name_manual: i.item_name_manual || null,
          ordered_qty: i.ordered_qty || 0,
          received_qty: i.received_qty || 0,
          uom_id: i.uom_id || null,
          uom_manual: i.uom_manual || null,
          remarks: i.remarks || null,
        })),
      };

      setSubmitting(true);
      if (isNew) {
        await api.post('/warehouse/inwards', payload);
        message.success('Material Inward created successfully');
        navigate('/warehouse/material-inward');
      } else {
        await api.put(`/warehouse/inwards/${id}`, payload);
        message.success('Material Inward updated successfully');
        setEditMode(false);
        fetchInward();
      }
    } catch (err) {
      if (err.errorFields) {
        message.error('Please fill all required fields');
        return;
      }
      message.error(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const downloadTemplate = () => {
    const wsData = [
      ['PO Number', 'Vendor ID / Code', 'Vendor Name (Manual)', 'Warehouse', 'Received Date', 'Vehicle Number', 'Driver Name', 'Header Remarks', 'Item ID / Code', 'Item Name (Manual)', 'Ordered Qty', 'Received Qty', 'UOM', 'Item Remarks'],
      ['PO-12345', 'V001', '', 'Main Warehouse', '01-Jan-2024', 'MH-12-AB-1234', 'John Doe', 'Header remarks here', 'ITEM-001', '', '100', '100', 'Nos', 'Item remarks here']
    ];
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    
    // Style headers
    const mandatoryCols = ['Warehouse', 'Received Date', 'Item ID / Code', 'Received Qty', 'UOM'];
    for (let c = 0; c < wsData[0].length; c++) {
      const cellRef = XLSX.utils.encode_cell({ c: c, r: 0 });
      if (!ws[cellRef]) continue;
      const isMandatory = mandatoryCols.includes(wsData[0][c]);
      ws[cellRef].s = {
        font: { bold: true, color: { rgb: "FFFFFF" } },
        fill: { fgColor: { rgb: isMandatory ? "EF4444" : "3B82F6" } }, // Red for mandatory, Blue for optional
        alignment: { horizontal: "center", vertical: "center" }
      };
    }

    // Auto-size columns slightly
    const colWidths = wsData[0].map(col => ({ wch: Math.max(15, col.length + 2) }));
    ws['!cols'] = colWidths;

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Material Inward");
    XLSX.writeFile(wb, "Material_Inward_Template.xlsx");
  };

  const itemColumns = [
    {
      title: 'Item',
      dataIndex: 'item_id',
      width: 240,
      render: (val, record) => {
        if (!isNew && !editMode) {
          return (
            <span>
              {record.item_code && record.item_name
                ? `${record.item_code} - ${record.item_name}`
                : itemMaster.find((m) => String(m.value) === String(val))?.label || record.item_name_manual || '-'}
            </span>
          );
        }

        const options = [...itemMaster];
        if (record.item_id && !options.some((o) => String(o.value) === String(record.item_id))) {
          const label = record.item_code && record.item_name
            ? `${record.item_code} - ${record.item_name}`
            : record.item_name || `Item ID: ${record.item_id}`;
          options.push({
            label: label,
            value: record.item_id,
            uom_id: record.uom_id,
          });
        }

        return (
          <Select
            value={val}
            placeholder="Select item"
            allowClear
            showSearch
            optionFilterProp="label"
            options={options}
            style={{ width: '100%' }}
            onChange={(v) => handleItemFieldChange(record.key, 'item_id', v)}
            disabled={editMode && !!record.id}
          />
        );
      },
    },

    {
      title: 'Ordered Qty',
      dataIndex: 'ordered_qty',
      width: 110,
      render: (val, record) => !(isNew || editMode) ? (val ?? 0) : (
        <InputNumber
          value={val}
          min={0}
          style={{ width: '100%' }}
          onChange={(v) => handleItemFieldChange(record.key, 'ordered_qty', v)}
        />
      ),
    },
    {
      title: 'Received Qty',
      dataIndex: 'received_qty',
      width: 110,
      render: (val, record) => !(isNew || editMode) ? (val ?? 0) : (
        <InputNumber
          value={val}
          min={0}
          style={{ width: '100%' }}
          onChange={(v) => handleItemFieldChange(record.key, 'received_qty', v)}
        />
      ),
    },
    {
      title: 'UOM',
      dataIndex: 'uom_id',
      width: 140,
      render: (val, record) => {
        if (!isNew && !editMode) {
          return (
            <span>
              {record.uom_name || uoms.find((u) => String(u.value) === String(val))?.label || record.uom_manual || '-'}
            </span>
          );
        }

        const options = [...uoms];
        if (record.uom_id && !options.some((o) => String(o.value) === String(record.uom_id))) {
          options.push({
            label: record.uom_name || `UOM ID: ${record.uom_id}`,
            value: record.uom_id,
          });
        }

        return (
          <Select
            value={val}
            placeholder="UOM"
            allowClear
            showSearch
            optionFilterProp="label"
            options={options}
            style={{ width: '100%' }}
            onChange={(v) => handleItemFieldChange(record.key, 'uom_id', v)}
            disabled={editMode && !!record.id}
          />
        );
      },
    },
    {
      title: 'Remarks',
      dataIndex: 'remarks',
      width: 150,
      render: (val, record) => !(isNew || editMode) ? (val || '-') : (
        <Input
          value={val}
          onChange={(e) => handleItemFieldChange(record.key, 'remarks', e.target.value)}
        />
      ),
    },
  ];

  if (isNew || editMode) {
    itemColumns.push({
      title: 'Action',
      width: 60,
      render: (_, record) =>
        (isNew || editMode) && items.length > 1 ? (
          <Button danger type="text" icon={<DeleteOutlined />} onClick={() => handleRemoveItem(record.key)} />
        ) : null,
    });
  }

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <PageHeader title={isNew ? 'New Material Inward' : `Material Inward: ${form.getFieldValue('inward_number') || ''}`} subtitle="Record incoming materials at the warehouse">
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/warehouse/material-inward')}>Back to Inwards</Button>
          {!isNew && (
            <Button icon={<PrinterOutlined />} onClick={handlePrint}>Print PDF</Button>
          )}
          <Button icon={<DownloadOutlined />} onClick={downloadTemplate}>Download Template</Button>
          {isNew && (
            <Button type="primary" onClick={handleSubmit} loading={submitting}>
              Create
            </Button>
          )}
          {!isNew && editMode && (
            <>
              <Button onClick={() => setEditMode(false)}>Cancel</Button>
              <Button type="primary" onClick={handleSubmit} loading={submitting}>
                Save Changes
              </Button>
            </>
          )}
        </Space>
      </PageHeader>
      <Card className={!(isNew || editMode) ? 'view-mode-form' : ''}>
        <style>{`
          .view-mode-form .ant-input-disabled,
          .view-mode-form .ant-select-disabled .ant-select-selector,
          .view-mode-form .ant-picker-disabled,
          .view-mode-form .ant-input-number-disabled {
            color: #0f172a !important;
            background-color: #f8fafc !important;
            border-color: #cbd5e1 !important;
            font-weight: 700 !important;
            -webkit-text-fill-color: #0f172a !important;
          }
          .view-mode-form .ant-select-disabled .ant-select-selection-item {
            color: #0f172a !important;
            font-weight: 700 !important;
            -webkit-text-fill-color: #0f172a !important;
          }
          .view-mode-form .ant-input-disabled::placeholder,
          .view-mode-form .ant-select-disabled .ant-select-selection-placeholder,
          .view-mode-form .ant-picker-disabled input::placeholder {
            -webkit-text-fill-color: #94a3b8 !important;
          }
        `}</style>
        <Form form={form} layout="vertical" disabled={!(isNew || editMode)}>
          <Divider orientation="left">PO Reference (Optional)</Divider>
          <Row gutter={16}>
            <Col span={10}>
              <Form.Item name="po_number" label="PO Number/delivery of document">
                <Input placeholder="Enter PO Number or delivery of document" />
              </Form.Item>
            </Col>
            <Col span={4} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
            </Col>
            <Col span={10}>
              <Form.Item name="po_id" hidden><Input /></Form.Item>
            </Col>
          </Row>

          <Divider orientation="left">Inward Details</Divider>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="warehouse_id" label="Warehouse" rules={[{ required: true, message: 'Select warehouse' }]}>
                <Select placeholder="Select warehouse" options={warehouses} showSearch optionFilterProp="label" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="vendor_id" label="Vendor">
                <Select placeholder="Select vendor" options={vendors} allowClear showSearch optionFilterProp="label" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="received_date" label="Received Date" rules={[{ required: true, message: 'Select date' }]}>
                <DatePicker style={{ width: '100%' }} format="DD-MMM-YYYY" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="vehicle_number" label="Vehicle Number">
                <Input placeholder="e.g. MH-12-AB-1234" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="driver_name" label="Driver Name">
                <Input placeholder="Driver name" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="vendor_name_manual" label="Vendor Name (Manual)">
                <Input placeholder="If vendor not in system" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="remarks" label="Remarks">
                <Input.TextArea rows={2} placeholder="Any remarks" />
              </Form.Item>
            </Col>
          </Row>
        </Form>

        <Divider orientation="left">Items</Divider>
        <Table
          dataSource={items}
          columns={itemColumns}
          rowKey="key"
          pagination={false}
          size="small"
          scroll={{ x: 900 }}
          locale={{ emptyText: 'No items added yet' }}
        />
        {(isNew || editMode) && (
          <div style={{ marginTop: 12 }}>
            <Button type="dashed" icon={<PlusOutlined />} onClick={handleAddItem}>
              Add Item
            </Button>
          </div>
        )}
      </Card>
      
      {!isNew && (
        <div style={{ display: 'none' }}>
          <MaterialInwardPrint ref={printRef} data={fullData} />
        </div>
      )}
    </div>
  );
};

export default MaterialInwardForm;
