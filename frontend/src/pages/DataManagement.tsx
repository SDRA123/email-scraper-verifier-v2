import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  Tooltip,
  Typography,
  Paper,
  Stack,
  Alert,
  Snackbar,
  CircularProgress,
  Link as MuiLink,
  Divider
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRowSelectionModel,
  GridToolbarContainer,
  GridToolbarExport,
  GridToolbarFilterButton,
  GridToolbarColumnsButton,
  GridLogicOperator,
  GridFilterModel,
} from '@mui/x-data-grid';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import {
  Edit as EditIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Close as CloseIcon,
  Mail as MailIcon,
  LinkedIn as LinkedInIcon,
  Instagram as InstagramIcon,
  Facebook as FacebookIcon,
  Link as LinkIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Send as SendIcon,
  Add as AddIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { EmailData } from '../types';

const API_URL = 'http://localhost:8000';

interface CustomFilterToolbarProps {
  onAddFilter: () => void;
  filterCount: number;
}

function CustomToolbar({ onAddFilter, filterCount }: CustomFilterToolbarProps) {
  return (
    <GridToolbarContainer>
      <GridToolbarColumnsButton />
      <GridToolbarExport />
    </GridToolbarContainer>
  );
}

const DataManagement: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<EmailData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRows, setSelectedRows] = useState<GridRowSelectionModel>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartId, setDragStartId] = useState<string | number | null>(null);
  const [filterLogicOperator, setFilterLogicOperator] = useState<GridLogicOperator>(GridLogicOperator.And);
  const [filterModel, setFilterModel] = useState<GridFilterModel>({
    items: [],
    logicOperator: GridLogicOperator.And,
  });
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<EmailData | null>(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' | 'info' });
  const [saveLoading, setSaveLoading] = useState(false);

  const showSnackbar = (message: string, severity: 'success' | 'error' | 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  // Custom filter function
  const applyCustomFilters = useCallback((dataItems: EmailData[]) => {
    if (filterModel.items.length === 0) return dataItems;

    return dataItems.filter((row) => {
      const results = filterModel.items.map((filter) => {
        const fieldValue = row[filter.field as keyof EmailData];
        const filterValue = filter.value;

        // Handle different operators
        switch (filter.operator) {
          case 'contains':
            return String(fieldValue || '').toLowerCase().includes(String(filterValue || '').toLowerCase());
          case 'equals':
            return String(fieldValue || '').toLowerCase() === String(filterValue || '').toLowerCase();
          case 'startsWith':
            return String(fieldValue || '').toLowerCase().startsWith(String(filterValue || '').toLowerCase());
          case 'endsWith':
            return String(fieldValue || '').toLowerCase().endsWith(String(filterValue || '').toLowerCase());
          case 'isEmpty':
            return !fieldValue || String(fieldValue).trim() === '';
          case 'isNotEmpty':
            return fieldValue && String(fieldValue).trim() !== '';
          case 'after':
            if (!fieldValue || !filterValue) return false;
            try {
              return new Date(String(fieldValue)) > new Date(String(filterValue));
            } catch {
              return false;
            }
          case 'before':
            if (!fieldValue || !filterValue) return false;
            try {
              return new Date(String(fieldValue)) < new Date(String(filterValue));
            } catch {
              return false;
            }
          case 'on':
            if (!fieldValue || !filterValue) return false;
            try {
              const fieldDate = new Date(String(fieldValue)).toDateString();
              const filterDate = new Date(String(filterValue)).toDateString();
              return fieldDate === filterDate;
            } catch {
              return false;
            }
          case '>':
            return Number(fieldValue) > Number(filterValue);
          case '>=':
            return Number(fieldValue) >= Number(filterValue);
          case '<':
            return Number(fieldValue) < Number(filterValue);
          case '<=':
            return Number(fieldValue) <= Number(filterValue);
          case '=':
            return Number(fieldValue) === Number(filterValue);
          default:
            return true;
        }
      });

      // Apply logic operator (AND or OR)
      if (filterLogicOperator === GridLogicOperator.And) {
        return results.every((result) => result);
      } else {
        return results.some((result) => result);
      }
    });
  }, [filterModel, filterLogicOperator]);

  const filteredData = useMemo(() => applyCustomFilters(data), [data, applyCustomFilters]);

  const fetchData = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_URL}/api/email/data`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      // Add row IDs for DataGrid
      const dataWithIds = response.data.map((item: EmailData, index: number) => ({
        ...item,
        row_id: item.id || `row_${index}`
      }));

      setData(dataWithIds);
    } catch (error) {
      console.error('Error fetching data:', error);
      showSnackbar('Error loading data', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, []);

  const handleEdit = (record: EmailData) => {
    setEditingRecord({ ...record });
    setEditDialogOpen(true);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this record?')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      await axios.delete(`${API_URL}/api/email/delete/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      showSnackbar('Record deleted successfully', 'success');
      fetchData();
    } catch (error) {
      showSnackbar('Error deleting record', 'error');
    }
  };

  const handleSave = async () => {
    if (!editingRecord || !editingRecord.id) return;

    setSaveLoading(true);
    try {
      const token = localStorage.getItem('token');
      await axios.put(
        `${API_URL}/api/email/update/${editingRecord.id}`,
        editingRecord,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showSnackbar('Record updated successfully', 'success');
      setEditDialogOpen(false);
      fetchData();
    } catch (error) {
      showSnackbar('Error updating record', 'error');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleBulkMarkAsSent = async () => {
    if (selectedRows.length === 0) {
      showSnackbar('Please select records to mark as sent', 'info');
      return;
    }

    try {
      // Get the actual database IDs from selected rows
      const selectedRecords = data.filter(row => row.id != null && selectedRows.includes(row.id));
      const actualIds = selectedRecords.map(record => record.id).filter((id): id is number => id != null);
      
      if (actualIds.length === 0) {
        showSnackbar('No valid records selected for update', 'error');
        return;
      }

      const token = localStorage.getItem('token');
      const response = await axios.post(
        `${API_URL}/api/email/bulk-update`,
        {
          ids: actualIds,
          updates: {
            email_sent: true,
            email_sent_date: new Date().toISOString(),
          },
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (response.data && response.data.count > 0) {
        showSnackbar(`Marked ${response.data.count} records as sent`, 'success');
        setSelectedRows([]);
        fetchData();
      } else {
        showSnackbar('No records were updated. Please check your selection.', 'info');
      }
    } catch (error: any) {
      console.error('Error updating records:', error);
      const errorMessage = error.response?.data?.detail || 'Error updating records. Please try again.';
      showSnackbar(errorMessage, 'error');
    }
  };

  const handleBulkDelete = async () => {
    if (selectedRows.length === 0) {
      showSnackbar('Please select records to delete', 'info');
      return;
    }

    if (!window.confirm(`Are you sure you want to delete ${selectedRows.length} records?`)) {
      return;
    }

    try {
      // Get the actual database IDs from selected rows
      const selectedRecords = data.filter(row => row.id != null && selectedRows.includes(row.id));
      const actualIds = selectedRecords.map(record => record.id).filter((id): id is number => id != null);
      
      if (actualIds.length === 0) {
        showSnackbar('No valid records selected for deletion', 'error');
        return;
      }

      const token = localStorage.getItem('token');
      await axios.post(
        `${API_URL}/api/email/bulk-delete`,
        { ids: actualIds },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showSnackbar(`Deleted ${actualIds.length} records`, 'success');
      setSelectedRows([]);
      fetchData();
    } catch (error: any) {
      console.error('Error deleting records:', error);
      const errorMessage = error.response?.data?.detail || 'Error deleting records. Please try again.';
      showSnackbar(errorMessage, 'error');
    }
  };

  const handleExportSelected = () => {
    if (selectedRows.length === 0) {
      showSnackbar('Please select records to export', 'info');
      return;
    }

    try {
      // Get selected records
      const selectedRecords = data.filter(row => row.id && selectedRows.includes(row.id));

      // Convert to CSV format with all columns
      const headers = [
        'Primary Email', 'Email 2', 'Email 3', 'Email 2 Verified', 'Email 3 Verified',
        'Email 2 Quality', 'Email 3 Quality', 'Name', 'Website', 'Company', 'Phone',
        'Job Title', 'LinkedIn', 'Instagram', 'Facebook', 'Contact Form', 'Verified',
        'Verification Quality', 'Verification Status', 'Verification Notes', 'Is Blog',
        'Blog Score', 'Blog Notes', 'Source', 'Notes', 'Email Sent', 'Email Sent Date',
        'Created At'
      ];

      const csvRows = [headers.join(',')];

      selectedRecords.forEach(record => {
        const row = [
          record.email || '',
          record.email_2 || '',
          record.email_3 || '',
          record.email_2_verified || false,
          record.email_3_verified || false,
          record.email_2_quality || '',
          record.email_3_quality || '',
          record.name || '',
          record.website || '',
          record.company || '',
          record.phone || '',
          record.job_title || '',
          record.linkedin || '',
          record.instagram || '',
          record.facebook || '',
          record.contact_form || '',
          record.verified || false,
          record.verification_quality || '',
          record.verification_status || '',
          `"${(record.verification_notes || '').replace(/"/g, '""')}"`,
          record.is_blog || false,
          record.blog_score || '',
          `"${(record.blog_notes || '').replace(/"/g, '""')}"`,
          record.source || '',
          `"${(record.notes || '').replace(/"/g, '""')}"`,
          record.email_sent || false,
          record.email_sent_date || '',
          record.created_at || ''
        ];
        csvRows.push(row.join(','));
      });

      // Create blob and download
      const csvContent = csvRows.join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);

      link.setAttribute('href', url);
      link.setAttribute('download', `email_data_export_${new Date().toISOString().slice(0, 10)}.csv`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      showSnackbar(`Exported ${selectedRows.length} records`, 'success');
    } catch (error) {
      showSnackbar('Error exporting records', 'error');
    }
  };

  // Row selection handlers
  const handleRowClick = (params: any) => {
    if (isDragging) return; // Don't toggle on drag
    
    const clickedId = params.id;
    setSelectedRows((prev) => {
      if (prev.includes(clickedId)) {
        return prev.filter((id) => id !== clickedId);
      } else {
        return [...prev, clickedId];
      }
    });
  };

  const handleRowMouseDown = (rowId: any) => {
    setIsDragging(true);
    setDragStartId(rowId);
  };

  const handleRowMouseEnter = (rowId: any) => {
    if (isDragging && dragStartId !== null) {
      const startIndex = data.findIndex(row => row.id === dragStartId || row.id === Number(dragStartId));
      const currentIndex = data.findIndex(row => row.id === rowId || row.id === Number(rowId));
      
      if (startIndex !== -1 && currentIndex !== -1) {
        const minIndex = Math.min(startIndex, currentIndex);
        const maxIndex = Math.max(startIndex, currentIndex);
        const rangeIds = data.slice(minIndex, maxIndex + 1)
          .map(row => row.id)
          .filter((id): id is number => id !== undefined);
        
        setSelectedRows(rangeIds);
      }
    }
  };

  const handleRowMouseUp = () => {
    setIsDragging(false);
    setDragStartId(null);
  };

  // Handler to add a new filter
  const handleAddFilter = () => {
    setFilterModel((prev) => ({
      ...prev,
      items: [
        ...prev.items,
        {
          id: Date.now(), // Unique ID for the filter
          field: 'email', // Default field
          operator: 'contains', // Default operator
          value: '', // Empty value - user will fill this
        },
      ],
    }));
  };

  // Add mouse event listeners for drag selection
  React.useEffect(() => {
    const handleGlobalMouseUp = () => {
      setIsDragging(false);
      setDragStartId(null);
    };
    
    const handleRowEvents = (e: Event) => {
      const mouseEvent = e as unknown as MouseEvent;
      const target = mouseEvent.target as HTMLElement;
      const row = target.closest('.MuiDataGrid-row');
      
      if (row) {
        const rowId = row.getAttribute('data-id');
        
        if (e.type === 'mousedown' && rowId) {
          // Check if clicking on action buttons
          const isActionButton = target.closest('.MuiIconButton-root');
          if (!isActionButton) {
            handleRowMouseDown(Number(rowId));
          }
        } else if (e.type === 'mouseenter' && rowId) {
          handleRowMouseEnter(Number(rowId));
        }
      }
    };
    
    const dataGrid = document.querySelector('.MuiDataGrid-root');
    if (dataGrid) {
      dataGrid.addEventListener('mousedown', handleRowEvents as EventListener);
      dataGrid.addEventListener('mouseenter', handleRowEvents as EventListener, true);
    }
    
    window.addEventListener('mouseup', handleGlobalMouseUp);
    
    return () => {
      if (dataGrid) {
        dataGrid.removeEventListener('mousedown', handleRowEvents as EventListener);
        dataGrid.removeEventListener('mouseenter', handleRowEvents as EventListener, true);
      }
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [isDragging, dragStartId, data]);

  const columns: GridColDef[] = [
    {
      field: 'index',
      headerName: '#',
      width: 70,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const index = data.findIndex(row => row.id === params.row.id);
        return (
          <Typography variant="body2" fontWeight={500}>
            {index + 1}
          </Typography>
        );
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Tooltip title="Edit">
            <IconButton 
              size="small" 
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(params.row as EmailData);
              }}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton 
              size="small" 
              color="error" 
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(params.row.id);
              }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
    {
      field: 'website',
      headerName: 'Website',
      minWidth: 160,
      flex: 0.8,
      renderCell: (params) => params.value ? (
        <MuiLink href={params.value} target="_blank" rel="noopener" fontSize="0.85rem">
          {params.value}
        </MuiLink>
      ) : '—',
    },
    {
      field: 'email_sent',
      headerName: 'Sent',
      width: 80,
      renderCell: (params) => (
        params.value ? (
          <Tooltip title={`Sent on ${new Date(params.row.email_sent_date).toLocaleDateString()}`}>
            <CheckCircleIcon color="success" fontSize="small" />
          </Tooltip>
        ) : (
          <CancelIcon color="disabled" fontSize="small" />
        )
      ),
    },
    {
      field: 'email',
      headerName: 'Email 1',
      minWidth: 180,
      flex: 0.9,
      renderCell: (params) => (
        <Box>
          <Typography variant="body2">{params.value}</Typography>
          {params.row.verified && (
            <Chip label="Verified" size="small" color="success" sx={{ height: 16, fontSize: '0.65rem' }} />
          )}
        </Box>
      ),
    },
    {
      field: 'verification_quality',
      headerName: 'Score 1',
      minWidth: 80,
      renderCell: (params) => {
        const quality = params.value as number | null | undefined;
        if (quality === undefined || quality === null) {
          return <Chip label="—" size="small" color="default" />;
        }

        let color: 'success' | 'warning' | 'error' = 'error';
        if (quality >= 85) {
          color = 'success';
        } else if (quality >= 60) {
          color = 'warning';
        }

        return <Chip label={quality} size="small" color={color} />;
      },
    },
    {
      field: 'verification_status',
      headerName: 'Status 1',
      minWidth: 120,
      flex: 0.6,
      valueGetter: (params) => params.row.verification_status || params.row.status,
      renderCell: (params) => {
        const label = params.value || (params.row.verification_quality && params.row.verification_quality >= 85 ? 'Verified' : 'Pending');
        const quality = params.row.verification_quality;
        const color = quality !== undefined && quality !== null && quality >= 85 ? 'success' : 'default';
        return <Chip label={label} size="small" color={color} />;
      },
    },
    {
      field: 'verification_notes',
      headerName: 'Reason 1',
      minWidth: 150,
      flex: 0.8,
      renderCell: (params) => {
        if (!params.value) {
          return '—';
        }
        return (
          <Tooltip title={params.value} placement="top-start">
            <Typography variant="body2" noWrap>
              {params.value}
            </Typography>
          </Tooltip>
        );
      },
    },
    {
      field: 'email_2',
      headerName: 'Email 2',
      minWidth: 180,
      flex: 0.9,
      renderCell: (params) => params.value ? (
        <Box>
          <Typography variant="body2" fontSize="0.85rem">{params.value}</Typography>
          {params.row.email_2_verified && (
            <Chip label="Verified" size="small" color="success" sx={{ height: 16, fontSize: '0.6rem' }} />
          )}
        </Box>
      ) : '—',
    },
    {
      field: 'email_2_quality',
      headerName: 'Score 2',
      minWidth: 80,
      renderCell: (params) => {
        const quality = params.value as number | null | undefined;
        if (quality === undefined || quality === null) {
          return '—';
        }

        let color: 'success' | 'warning' | 'error' = 'error';
        if (quality >= 85) {
          color = 'success';
        } else if (quality >= 60) {
          color = 'warning';
        }

        return <Chip label={quality} size="small" color={color} />;
      },
    },
    {
      field: 'email_2_status',
      headerName: 'Status 2',
      minWidth: 120,
      flex: 0.6,
      renderCell: (params) => {
        if (!params.value) return '—';
        const quality = params.row.email_2_quality;
        const color = quality !== undefined && quality !== null && quality >= 85 ? 'success' : 'default';
        return <Chip label={params.value} size="small" color={color} />;
      },
    },
    {
      field: 'email_2_notes',
      headerName: 'Reason 2',
      minWidth: 150,
      flex: 0.8,
      renderCell: (params) => {
        if (!params.value) {
          return '—';
        }
        return (
          <Tooltip title={params.value} placement="top-start">
            <Typography variant="body2" noWrap>
              {params.value}
            </Typography>
          </Tooltip>
        );
      },
    },
    {
      field: 'email_3',
      headerName: 'Email 3',
      minWidth: 180,
      flex: 0.9,
      renderCell: (params) => params.value ? (
        <Box>
          <Typography variant="body2" fontSize="0.85rem">{params.value}</Typography>
          {params.row.email_3_verified && (
            <Chip label="Verified" size="small" color="success" sx={{ height: 16, fontSize: '0.6rem' }} />
          )}
        </Box>
      ) : '—',
    },
    {
      field: 'email_3_quality',
      headerName: 'Score 3',
      minWidth: 80,
      renderCell: (params) => {
        const quality = params.value as number | null | undefined;
        if (quality === undefined || quality === null) {
          return '—';
        }

        let color: 'success' | 'warning' | 'error' = 'error';
        if (quality >= 85) {
          color = 'success';
        } else if (quality >= 60) {
          color = 'warning';
        }

        return <Chip label={quality} size="small" color={color} />;
      },
    },
    {
      field: 'email_3_status',
      headerName: 'Status 3',
      minWidth: 120,
      flex: 0.6,
      renderCell: (params) => {
        if (!params.value) return '—';
        const quality = params.row.email_3_quality;
        const color = quality !== undefined && quality !== null && quality >= 85 ? 'success' : 'default';
        return <Chip label={params.value} size="small" color={color} />;
      },
    },
    {
      field: 'email_3_notes',
      headerName: 'Reason 3',
      minWidth: 150,
      flex: 0.8,
      renderCell: (params) => {
        if (!params.value) {
          return '—';
        }
        return (
          <Tooltip title={params.value} placement="top-start">
            <Typography variant="body2" noWrap>
              {params.value}
            </Typography>
          </Tooltip>
        );
      },
    },
    {
      field: 'phone',
      headerName: 'Phone',
      minWidth: 140,
      flex: 0.7,
      renderCell: (params) => params.value || '—',
    },
    {
      field: 'is_blog',
      headerName: 'Blog',
      minWidth: 90,
      flex: 0.4,
      type: 'singleSelect',
      valueOptions: [
        { value: true, label: 'Yes' },
        { value: false, label: 'No' },
        { value: null, label: 'Unknown' }
      ],
      sortable: true,
      filterable: true,
      valueGetter: (params) => {
        const val = params.row.is_blog;
        if (val === true) return true;
        if (val === false) return false;
        return null;
      },
      renderCell: (params) => {
        const isBlog = params.value;
        if (isBlog === true) {
          return <Chip label="Yes" size="small" color="primary" />;
        } else if (isBlog === false) {
          return <Chip label="No" size="small" color="default" />;
        }
        return <Chip label="—" size="small" color="default" />;
      },
    },
    {
      field: 'blog_score',
      headerName: 'Blog Score',
      minWidth: 100,
      flex: 0.5,
      type: 'number',
      sortable: true,
      filterable: true,
      renderCell: (params) => {
        const score = params.value as number | null | undefined;
        if (score === undefined || score === null) {
          return '—';
        }

        let color: 'success' | 'warning' | 'error' = 'error';
        if (score >= 8) {
          color = 'success';
        } else if (score >= 4) {
          color = 'warning';
        }

        return <Chip label={score} size="small" color={color} />;
      },
    },
    {
      field: 'links',
      headerName: 'Links',
      minWidth: 160,
      flex: 0.8,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const row = params.row;
        return (
          <Stack direction="row" spacing={0.5}>
            {row.linkedin && (
              <Tooltip title={row.linkedin}>
                <IconButton
                  size="small"
                  onClick={() => window.open(row.linkedin, '_blank')}
                  sx={{ color: '#0077b5' }}
                >
                  <LinkedInIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {row.facebook && (
              <Tooltip title={row.facebook}>
                <IconButton
                  size="small"
                  onClick={() => window.open(row.facebook, '_blank')}
                  sx={{ color: '#1877f2' }}
                >
                  <FacebookIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {row.instagram && (
              <Tooltip title={row.instagram}>
                <IconButton
                  size="small"
                  onClick={() => window.open(row.instagram, '_blank')}
                  sx={{ color: '#e4405f' }}
                >
                  <InstagramIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {row.contact_form && (
              <Tooltip title={row.contact_form}>
                <IconButton
                  size="small"
                  onClick={() => window.open(row.contact_form, '_blank')}
                  sx={{ color: '#666' }}
                >
                  <LinkIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {!row.linkedin && !row.facebook && !row.instagram && !row.contact_form && (
              <Typography variant="body2" color="text.secondary">
                —
              </Typography>
            )}
          </Stack>
        );
      },
    },
    {
      field: 'name',
      headerName: 'Name',
      minWidth: 120,
      flex: 0.6,
      renderCell: (params) => params.value || '—',
    },
    {
      field: 'job_title',
      headerName: 'Job Title',
      minWidth: 120,
      flex: 0.6,
      renderCell: (params) => params.value || '—',
    },
    {
      field: 'created_at',
      headerName: 'Created At',
      type: 'date',
      filterable: true,
      sortable: true,
      valueGetter: (params) => params.value ? new Date(params.value) : null,
      valueFormatter: (params) => params.value ? new Date(params.value).toLocaleDateString() : '',
    },
    {
      field: 'source',
      headerName: 'Source',
      minWidth: 120,
      flex: 0.5,
      valueGetter: (params) => params.value || 'upload',
      renderCell: (params) => (
        <Chip label={params.value || 'unknown'} size="small" variant="outlined" />
      ),
    },
    {
      field: 'notes',
      headerName: 'Notes',
      minWidth: 150,
      flex: 0.7,
      renderCell: (params) => params.value || '—',
    },
  ];

  // Columns are now manually ordered in the desired sequence

  return (
    <Box sx={{ p: 3 }}>
      <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
          <Box>
            <Typography variant="h4" gutterBottom>
              Data Management
            </Typography>
            <Typography variant="h6" color="primary">
              Total Records: {data.length}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            onClick={() => navigate('/dashboard')}
          >
            Back to Dashboard
          </Button>
        </Stack>

        <Typography variant="body2" color="textSecondary" gutterBottom>
          Manage your email database with full CRUD capabilities. Select multiple records for bulk actions.
        </Typography>

        {selectedRows.length > 0 && (
          <Alert severity="info" sx={{ mt: 2 }}>
            {selectedRows.length} record(s) selected
          </Alert>
        )}
      </Paper>

      <Paper elevation={2} sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            startIcon={<SendIcon />}
            onClick={handleBulkMarkAsSent}
            disabled={selectedRows.length === 0}
          >
            Mark as Sent ({selectedRows.length})
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={handleBulkDelete}
            disabled={selectedRows.length === 0}
          >
            Delete Selected ({selectedRows.length})
          </Button>
          <Button
            variant="outlined"
            startIcon={<MailIcon />}
            onClick={handleExportSelected}
            disabled={selectedRows.length === 0}
          >
            Export Selected ({selectedRows.length})
          </Button>
        </Stack>
      </Paper>

      {/* Custom Multi-Filter Interface */}
      <Paper elevation={2} sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" sx={{ mb: 2 }}>
          <Typography variant="body2" fontWeight="bold">
            Filters:
          </Typography>
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={handleAddFilter}
            variant="outlined"
          >
            Add Filter
          </Button>
          {filterModel.items.length > 1 && (
            <>
              <Divider orientation="vertical" flexItem />
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <Select
                  value={filterLogicOperator}
                  onChange={(e) => {
                    const newOperator = e.target.value as GridLogicOperator;
                    setFilterLogicOperator(newOperator);
                    setFilterModel((prev) => ({
                      ...prev,
                      logicOperator: newOperator,
                    }));
                  }}
                  variant="outlined"
                >
                  <MenuItem value={GridLogicOperator.And}>
                    <Typography variant="body2">AND (All match)</Typography>
                  </MenuItem>
                  <MenuItem value={GridLogicOperator.Or}>
                    <Typography variant="body2">OR (Any match)</Typography>
                  </MenuItem>
                </Select>
              </FormControl>
              <Chip 
                label={`${filterModel.items.length} filters`} 
                size="small" 
                color="primary" 
                variant="outlined"
              />
            </>
          )}
        </Stack>

        {/* Display active filters */}
        {filterModel.items.map((item, index) => (
          <Box key={item.id || index} sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <FormControl size="small" sx={{ minWidth: 150 }}>
                <InputLabel>Column</InputLabel>
                <Select
                  value={item.field}
                  onChange={(e) => {
                    const newItems = [...filterModel.items];
                    newItems[index] = { ...newItems[index], field: e.target.value };
                    setFilterModel((prev) => ({ ...prev, items: newItems }));
                  }}
                  label="Column"
                >
                  <MenuItem value="email">Email 1</MenuItem>
                  <MenuItem value="email_2">Email 2</MenuItem>
                  <MenuItem value="email_3">Email 3</MenuItem>
                  <MenuItem value="verification_quality">Email 1 Score</MenuItem>
                  <MenuItem value="email_2_quality">Email 2 Score</MenuItem>
                  <MenuItem value="email_3_quality">Email 3 Score</MenuItem>
                  <MenuItem value="verification_status">Email 1 Status</MenuItem>
                  <MenuItem value="email_2_status">Email 2 Status</MenuItem>
                  <MenuItem value="email_3_status">Email 3 Status</MenuItem>
                  <MenuItem value="verification_notes">Email 1 Reason</MenuItem>
                  <MenuItem value="email_2_notes">Email 2 Reason</MenuItem>
                  <MenuItem value="email_3_notes">Email 3 Reason</MenuItem>
                  <MenuItem value="website">Website</MenuItem>
                  <MenuItem value="phone">Phone</MenuItem>
                  <MenuItem value="name">Name</MenuItem>
                  <MenuItem value="phone">Phone</MenuItem>
                  <MenuItem value="job_title">Job Title</MenuItem>
                  <MenuItem value="is_blog">Blog</MenuItem>
                  <MenuItem value="blog_score">Blog Score</MenuItem>
                  <MenuItem value="linkedin">LinkedIn</MenuItem>
                  <MenuItem value="facebook">Facebook</MenuItem>
                  <MenuItem value="instagram">Instagram</MenuItem>
                  <MenuItem value="contact_form">Contact Form</MenuItem>
                  <MenuItem value="source">Source</MenuItem>
                  <MenuItem value="notes">Notes</MenuItem>
                  <MenuItem value="created_at">Created At</MenuItem>
                  <MenuItem value="email_sent">Email Sent</MenuItem>
                  <MenuItem value="email_sent_date">Email Sent Date</MenuItem>
                </Select>
              </FormControl>
              
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Operator</InputLabel>
                <Select
                  value={item.operator}
                  onChange={(e) => {
                    const newItems = [...filterModel.items];
                    newItems[index] = { ...newItems[index], operator: e.target.value };
                    setFilterModel((prev) => ({ ...prev, items: newItems }));
                  }}
                  label="Operator"
                >
                  <MenuItem value="contains">contains</MenuItem>
                  <MenuItem value="equals">equals</MenuItem>
                  <MenuItem value="startsWith">starts with</MenuItem>
                  <MenuItem value="endsWith">ends with</MenuItem>
                  <MenuItem value="isEmpty">is empty</MenuItem>
                  <MenuItem value="isNotEmpty">is not empty</MenuItem>
                  {(item.field === 'created_at' || item.field === 'email_sent_date') ? (
                    <>
                      <MenuItem value="after">after</MenuItem>
                      <MenuItem value="before">before</MenuItem>
                      <MenuItem value="on">on (equals)</MenuItem>
                    </>
                  ) : (
                    <>
                      <MenuItem value=">">{'>'}</MenuItem>
                      <MenuItem value=">=">{'≥'}</MenuItem>
                      <MenuItem value="<">{'<'}</MenuItem>
                      <MenuItem value="<=">{'≤'}</MenuItem>
                      <MenuItem value="=">{'='}</MenuItem>
                    </>
                  )}
                </Select>
              </FormControl>
              
              <TextField
                size="small"
                label="Value"
                type={(item.field === 'created_at' || item.field === 'email_sent_date') ? 'date' : 'text'}
                value={item.value || ''}
                onChange={(e) => {
                  const newItems = [...filterModel.items];
                  newItems[index] = { ...newItems[index], value: e.target.value };
                  setFilterModel((prev) => ({ ...prev, items: newItems }));
                }}
                sx={{ minWidth: 200 }}
                disabled={item.operator === 'isEmpty' || item.operator === 'isNotEmpty'}
                InputLabelProps={(item.field === 'created_at' || item.field === 'email_sent_date') ? { shrink: true } : undefined}
              />
              
              <IconButton
                size="small"
                color="error"
                onClick={() => {
                  const newItems = filterModel.items.filter((_, i) => i !== index);
                  setFilterModel((prev) => ({ ...prev, items: newItems }));
                }}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Box>
        ))}

        {filterModel.items.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No filters applied. Click "Add Filter" to create custom filters.
          </Typography>
        )}
      </Paper>

      {/* Old Filter Logic Operator Control - Hidden */}
      {false && filterModel.items.length > 1 && (
        <Paper elevation={2} sx={{ p: 2, mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Combine filters with:
            </Typography>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <Select
                value={filterLogicOperator}
                onChange={(e) => {
                  const newOperator = e.target.value as GridLogicOperator;
                  setFilterLogicOperator(newOperator);
                  setFilterModel((prev) => ({
                    ...prev,
                    logicOperator: newOperator,
                  }));
                }}
                variant="outlined"
              >
                <MenuItem value={GridLogicOperator.And}>
                  <Box>
                    <Typography variant="body2" fontWeight="bold">AND</Typography>
                    <Typography variant="caption" color="text.secondary">All conditions must match</Typography>
                  </Box>
                </MenuItem>
                <MenuItem value={GridLogicOperator.Or}>
                  <Box>
                    <Typography variant="body2" fontWeight="bold">OR</Typography>
                    <Typography variant="caption" color="text.secondary">Any condition can match</Typography>
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>
            <Chip 
              label={`${filterModel.items.length} filters active`} 
              size="small" 
              color="primary" 
              variant="outlined"
            />
          </Box>
        </Paper>
      )}

      <Paper elevation={2} sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={filteredData}
          columns={columns}
          loading={loading}
          getRowId={(row) => row.id || row.row_id}
          hideFooter={true}
          onRowClick={handleRowClick}
          slots={{
            toolbar: () => (
              <CustomToolbar 
                onAddFilter={handleAddFilter} 
                filterCount={filterModel.items.length}
              />
            ),
          }}
          sx={{
            height: '100%',
            width: '100%',
            '& .MuiDataGrid-cell': {
              fontSize: '0.875rem',
            },
            '& .MuiDataGrid-row': {
              cursor: 'pointer',
              userSelect: 'none',
              '&:hover': {
                backgroundColor: 'action.hover',
              },
            },
            '& .MuiDataGrid-virtualScroller': {
              overflowY: 'auto !important',
            },
            '& .row-selected': {
              backgroundColor: 'rgba(25, 118, 210, 0.12) !important',
              '&:hover': {
                backgroundColor: 'rgba(25, 118, 210, 0.24) !important',
              },
            },
            '& .MuiDataGrid-filterForm': {
              gap: 1,
            },
            '& .MuiDataGrid-filterFormLogicOperatorInput': {
              mr: 2,
            },
          }}
          getRowClassName={(params) => 
            selectedRows.includes(params.id) ? 'row-selected' : ''
          }
          autoHeight={false}
          rowHeight={52}
          columnHeaderHeight={56}
          disableVirtualization={false}
        />
      </Paper>

      {/* Edit Dialog */}
      <Dialog
        open={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Edit Record
          <IconButton
            onClick={() => setEditDialogOpen(false)}
            sx={{ position: 'absolute', right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {editingRecord && (
            <Stack spacing={2} sx={{ mt: 2 }}>
              {/* Emails */}
              <Typography variant="subtitle2" color="primary">Email Addresses</Typography>
              <TextField
                fullWidth
                label="Primary Email"
                value={editingRecord.email || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, email: e.target.value })}
              />
              <TextField
                fullWidth
                label="Email 2"
                value={editingRecord.email_2 || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, email_2: e.target.value })}
              />
              <TextField
                fullWidth
                label="Email 3"
                value={editingRecord.email_3 || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, email_3: e.target.value })}
              />

              {/* Basic Info */}
              <Typography variant="subtitle2" color="primary" sx={{ mt: 2 }}>Basic Information</Typography>
              <TextField
                fullWidth
                label="Name"
                value={editingRecord.name || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, name: e.target.value })}
              />
              <TextField
                fullWidth
                label="Company"
                value={editingRecord.company || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, company: e.target.value })}
              />
              <TextField
                fullWidth
                label="Website"
                value={editingRecord.website || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, website: e.target.value })}
              />
              <TextField
                fullWidth
                label="Phone"
                value={editingRecord.phone || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, phone: e.target.value })}
              />
              <TextField
                fullWidth
                label="Job Title"
                value={editingRecord.job_title || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, job_title: e.target.value })}
              />

              {/* Social Links */}
              <Typography variant="subtitle2" color="primary" sx={{ mt: 2 }}>Social Media</Typography>
              <TextField
                fullWidth
                label="LinkedIn"
                value={editingRecord.linkedin || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, linkedin: e.target.value })}
              />
              <TextField
                fullWidth
                label="Instagram"
                value={editingRecord.instagram || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, instagram: e.target.value })}
              />
              <TextField
                fullWidth
                label="Facebook"
                value={editingRecord.facebook || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, facebook: e.target.value })}
              />
              <TextField
                fullWidth
                label="Contact Form"
                value={editingRecord.contact_form || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, contact_form: e.target.value })}
              />

              {/* Notes */}
              <Typography variant="subtitle2" color="primary" sx={{ mt: 2 }}>Additional Information</Typography>
              <TextField
                fullWidth
                multiline
                rows={3}
                label="Notes"
                value={editingRecord.notes || ''}
                onChange={(e) => setEditingRecord({ ...editingRecord, notes: e.target.value })}
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleSave}
            variant="contained"
            startIcon={saveLoading ? <CircularProgress size={20} /> : <SaveIcon />}
            disabled={saveLoading}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar({ ...snackbar, open: false })}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default DataManagement;
