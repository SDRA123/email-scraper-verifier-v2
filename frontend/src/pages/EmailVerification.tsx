import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Button,
  TextField,
  Grid,
  Alert,
  LinearProgress,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  Checkbox,
  Tabs,
  Tab,
  Divider,
  IconButton,
  Tooltip,
  Stack,
  CircularProgress,
  Snackbar,
} from '@mui/material';
import {
  Upload,
  Download,
  Refresh,
  Search,
  PlayArrow,
  CloudUpload,
  Verified,
  Timeline,
  Email,
  Web,
  Stop,
  Info,
  Delete,
  Storage,
  Edit as EditIcon,
  Save as SaveIcon,
  Close as CloseIcon,
  Delete as DeleteIcon,
  LinkedIn as LinkedInIcon,
  Instagram as InstagramIcon,
  Facebook as FacebookIcon,
  Link as LinkIcon,
} from '@mui/icons-material';
import { 
  DataGrid, 
  GridColDef,
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
import AddIcon from '@mui/icons-material/Add';
import apiService from '../services/apiService';
import { EmailData, VerificationResult } from '../types';

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

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const EmailVerification: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [checkingBlogs, setCheckingBlogs] = useState(false);
  const [currentDataId, setCurrentDataId] = useState<number | null>(null);
  const [emailData, setEmailData] = useState<EmailData[]>([]);
  const [verificationResults, setVerificationResults] = useState<VerificationResult[]>([]);
  const [scrapeDomain, setScrapeDomain] = useState('');
  const [singleEmail, setSingleEmail] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  
  // Pipeline related states
  const [pipelineDialog, setPipelineDialog] = useState(false);
  const [processingOptions, setProcessingOptions] = useState({
    blog_check: false,
    email_scrape: false,
    email_verify: false,
  });
  const [autoProcessAfterUpload, setAutoProcessAfterUpload] = useState(false);

  // Selection and filtering
  const [selectedRows, setSelectedRows] = useState<any[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartId, setDragStartId] = useState<string | number | null>(null);
  const [filterLogicOperator, setFilterLogicOperator] = useState<GridLogicOperator>(GridLogicOperator.And);
  const [filterModel, setFilterModel] = useState<GridFilterModel>({
    items: [],
    logicOperator: GridLogicOperator.And,
  });
  const [processingFilters, setProcessingFilters] = useState({
    onlyWithBlog: false,
    onlyUnverified: false,
    skipProcessed: true
  });
  const [activeProcesses, setActiveProcesses] = useState<any[]>([]);
  const [filters, setFilters] = useState({ status: 'all', search: '', sortBy: 'quality', sortOrder: 'desc' as 'asc' | 'desc' });
  const [loadingEmails, setLoadingEmails] = useState(false);
  const [startingPipeline, setStartingPipeline] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<EmailData | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' | 'info' });
  const isFetchingProcessesRef = useRef(false);
  const activeProcessesSnapshotRef = useRef<string>('[]');
  const latestEmailRequestRef = useRef(0);

  const showSnackbar = (message: string, severity: 'success' | 'error' | 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  // Custom filter function
  const applyCustomFilters = useCallback((data: EmailData[]) => {
    if (filterModel.items.length === 0) return data;

    return data.filter((row) => {
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

  const gridRows = useMemo(
    () => {
      const filteredData = applyCustomFilters(emailData);
      return filteredData.map((row, index) => ({
        ...row,
        id: row.row_id || `${row.email || 'row'}-${row.website || 'site'}-${index}`,
      }));
    },
    [emailData, applyCustomFilters]
  );

  const verificationTotals = useMemo(() => {
    return emailData.reduce(
      (acc, row) => {
        const quality = row.verification_quality;
        if (quality === undefined || quality === null) {
          if (row.verified) {
            acc.verified += 1;
          } else {
            acc.pending += 1;
          }
        } else if (quality >= 85) {
          acc.verified += 1;
        } else {
          acc.invalid += 1;
        }
        return acc;
      },
      { verified: 0, invalid: 0, pending: 0 }
    );
  }, [emailData]);

  const loadEmailData = useCallback(async (dataId: number) => {
    const requestId = Date.now();
    latestEmailRequestRef.current = requestId;
    setLoadingEmails(true);

    try {
      const response = await apiService.getEmailData(dataId, {
        status: filters.status !== 'all' ? filters.status : undefined,
        search: filters.search.trim() || undefined,
        sortBy: filters.sortBy,
        sortOrder: filters.sortOrder,
      });

      const normalized = response.data.map((row, index) => {
        const quality = row.verification_quality ?? null;
        const derivedVerified = quality !== null ? quality >= 85 : row.verified;
        return {
          ...row,
          verified: derivedVerified,
          row_id: row.row_id || `${row.email || 'row'}-${row.website || 'website'}-${index}`,
        };
      });

      if (latestEmailRequestRef.current !== requestId) {
        return;
      }

      setEmailData(normalized);
    } catch (error) {
      if (latestEmailRequestRef.current === requestId) {
        console.error('Failed to load email data:', error);
      }
    } finally {
      if (latestEmailRequestRef.current === requestId) {
        setLoadingEmails(false);
      }
    }
  }, [filters]);

  const fetchActiveProcesses = useCallback(async () => {
    if (isFetchingProcessesRef.current) {
      return;
    }

    isFetchingProcessesRef.current = true;

    try {
      const response = await apiService.get('/pipeline/processes');
      const processes = Array.isArray(response.data) ? response.data : [];
      const serialized = JSON.stringify(processes);

      if (activeProcessesSnapshotRef.current !== serialized) {
        activeProcessesSnapshotRef.current = serialized;
        setActiveProcesses(processes);
      }
    } catch (error) {
      console.error('Error fetching processes:', error);
    } finally {
      isFetchingProcessesRef.current = false;
    }
  }, []);

  const monitorProcess = useCallback(async (processId: string) => {
    const checkStatus = async () => {
      try {
        const response = await apiService.getPipelineStatus(processId);
        const status = response.data;
        
        if (status.status === 'completed') {
          setMessage({
            type: 'success',
            text: `Process completed successfully! ${status.message || ''}`,
          });
          
          // Refresh email data if we have a current upload
          if (currentDataId) {
            await loadEmailData(currentDataId);
          }
          
          // Refresh active processes
          await fetchActiveProcesses();
          
          return true; // Stop monitoring
        } else if (status.status === 'failed' || status.status === 'error') {
          setMessage({
            type: 'error',
            text: `Process failed: ${status.message || 'Unknown error'}`,
          });
          
          await fetchActiveProcesses();
          return true; // Stop monitoring
        }
        
        return false; // Continue monitoring
      } catch (error) {
        console.error('Error checking process status:', error);
        return true; // Stop monitoring on error
      }
    };
    
    // Check immediately
    const shouldStop = await checkStatus();
    if (shouldStop) return;
    
    // Then check every 2 seconds
    const interval = setInterval(async () => {
      const shouldStop = await checkStatus();
      if (shouldStop) {
        clearInterval(interval);
      }
    }, 2000);
    
    // Cleanup after 5 minutes
    setTimeout(() => {
      clearInterval(interval);
    }, 300000);
  }, [currentDataId, loadEmailData, fetchActiveProcesses]);

  const handleEdit = (record: EmailData) => {
    setEditingRecord({ ...record });
    setEditDialogOpen(true);
  };

  const handleDeleteSingleRow = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this record?')) {
      return;
    }

    try {
      await apiService.delete(`/email/delete/${id}`);
      showSnackbar('Record deleted successfully', 'success');
      if (currentDataId) {
        await loadEmailData(currentDataId);
      }
    } catch (error) {
      showSnackbar('Error deleting record', 'error');
    }
  };

  const handleSaveEdit = async () => {
    if (!editingRecord || !editingRecord.id) return;

    setSaveLoading(true);
    try {
      await apiService.put(`/email/update/${editingRecord.id}`, editingRecord);
      showSnackbar('Record updated successfully', 'success');
      setEditDialogOpen(false);
      if (currentDataId) {
        await loadEmailData(currentDataId);
      }
    } catch (error) {
      showSnackbar('Error updating record', 'error');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleVerifySelected = async () => {
    if (selectedRows.length === 0) {
      showSnackbar('Please select records to verify', 'info');
      return;
    }

    setVerifying(true);
    try {
      const selectedData = emailData.filter(row => selectedRows.includes(row.id));
      const emailsToVerify = selectedData
        .map(row => row.email)
        .filter(Boolean);

      if (emailsToVerify.length === 0) {
        showSnackbar('No emails found in selected records', 'info');
        setVerifying(false);
        return;
      }

      // Use pipeline endpoint with email filter
      const payload = { 
        data_id: currentDataId,
        steps: ['email_verify'],  // Only run email verification step
        filter_emails: emailsToVerify  // Filter to selected emails
      };

      const response = await apiService.post('/pipeline/start', payload);

      if (response.data && response.data.process_id) {
        showSnackbar(`Verification started for ${emailsToVerify.length} emails`, 'success');
        monitorProcess(response.data.process_id);
      } else {
        showSnackbar(`Verified ${emailsToVerify.length} emails`, 'success');
        if (currentDataId) {
          await loadEmailData(currentDataId);
        }
      }
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Verification failed', 'error');
    } finally {
      setVerifying(false);
    }
  };

  const handleCheckBlogsSelected = async () => {
    if (selectedRows.length === 0) {
      showSnackbar('Please select records to check', 'info');
      return;
    }

    setCheckingBlogs(true);
    try {
      const selectedData = emailData.filter(row => selectedRows.includes(row.id));
      const websitesToCheck = selectedData
        .map(row => row.website)
        .filter(Boolean);

      if (websitesToCheck.length === 0) {
        showSnackbar('No websites found in selected records', 'info');
        setCheckingBlogs(false);
        return;
      }

      // Use pipeline endpoint with website filter
      const payload = { 
        data_id: currentDataId,
        steps: ['blog_check'],  // Only run blog check step
        filter_websites: websitesToCheck  // Filter to selected websites
      };

      const response = await apiService.post('/pipeline/start', payload);

      if (response.data && response.data.process_id) {
        showSnackbar(`Blog check started for ${websitesToCheck.length} websites`, 'success');
        monitorProcess(response.data.process_id);
      } else {
        showSnackbar(`Checked ${websitesToCheck.length} websites`, 'success');
        if (currentDataId) {
          await loadEmailData(currentDataId);
        }
      }
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Blog check failed', 'error');
    } finally {
      setCheckingBlogs(false);
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
      await apiService.post('/email/bulk-delete', { ids: selectedRows });
      showSnackbar(`Deleted ${selectedRows.length} records`, 'success');
      setSelectedRows([]);
      if (currentDataId) {
        await loadEmailData(currentDataId);
      }
    } catch (error) {
      showSnackbar('Error deleting records', 'error');
    }
  };

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const uploadId = urlParams.get('upload_id');
    if (uploadId) {
      const parsedId = Number.parseInt(uploadId, 10);
      if (!Number.isNaN(parsedId)) {
        setCurrentDataId(parsedId);
      }
    }
  }, []);

  useEffect(() => {
    fetchActiveProcesses();
    const interval = setInterval(fetchActiveProcesses, 5000);
    return () => clearInterval(interval);
  }, [fetchActiveProcesses]);

  // WebSocket connection for real-time updates

  const connectWebSocket = (processId: string) => {
    const wsUrl = process.env.REACT_APP_API_URL?.replace('http://', 'ws://').replace('/api', '') || 'ws://localhost:8000';
    const websocket = new WebSocket(`${wsUrl}/ws/${processId}`);
    
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message:', data);
      // Update UI based on process status if needed
    };

    websocket.onclose = () => {
      console.log('WebSocket connection closed');
    };
  };

  useEffect(() => {
    if (currentDataId) {
      loadEmailData(currentDataId);
    }
  }, [currentDataId, loadEmailData]);

  useEffect(() => {
    setVerificationResults([]);
  }, [currentDataId]);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleFileUpload = async () => {
    if (!selectedFile) return;

    console.log('Starting file upload...', {
      fileName: selectedFile.name,
      autoProcess: autoProcessAfterUpload,
      processingOptions
    });

    setUploading(true);
    setMessage(null);

    try {
      let response;
      if (autoProcessAfterUpload) {
        // Use upload-and-process endpoint
        const selectedSteps = Object.entries(processingOptions)
          .filter(([_, enabled]) => enabled)
          .map(([step, _]) => step);

        response = await apiService.uploadAndProcess(selectedFile, selectedSteps);

        setMessage({
          type: 'success',
          text: `File uploaded and processing started! Process ID: ${response.data.process_id}`,
        });

        // Connect to WebSocket for real-time updates
        if (response.data.process_id) {
          connectWebSocket(response.data.process_id);
        }
      } else {
        // Regular upload
        response = await apiService.uploadExcelFile(selectedFile);
        setMessage({
          type: 'success',
          text: `File uploaded successfully! Processed ${response.data.processed_count} emails.`,
        });
      }

      setCurrentDataId(response.data.data_id);
      await loadEmailData(response.data.data_id);
      await fetchActiveProcesses();
    } catch (error: any) {
      console.error('File upload error:', error);
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Upload failed',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleVerifyEmails = async () => {
    if (!currentDataId) return;

    setVerifying(true);
    setMessage(null);

    try {
      // Use pipeline endpoint - verify all emails in upload
      const payload: any = { 
        data_id: currentDataId,
        steps: ['email_verify']  // Only run email verification step
      };

      // If filters are applied, we could add them here in the future
      // For now, verify all emails when no selection

      const response = await apiService.post('/pipeline/start', payload);

      if (response.data && response.data.process_id) {
        const pipelineData = response.data;
        setMessage({
          type: 'info',
          text: `Email verification started. Processing ${pipelineData.total_items} items. Process ID: ${pipelineData.process_id}`,
        });

        // Start monitoring this process
        monitorProcess(pipelineData.process_id);
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Verification failed',
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleCheckBlogs = async () => {
    if (!currentDataId) return;

    setCheckingBlogs(true);
    setMessage(null);

    try {
      // Use pipeline endpoint - check all websites in upload
      const payload: any = { 
        data_id: currentDataId,
        steps: ['blog_check']  // Only run blog check step
      };

      const response = await apiService.post('/pipeline/start', payload);

      if (response.data && response.data.process_id) {
        setMessage({
          type: 'info',
          text: `Blog checking started. Processing ${response.data.total_items} items. Process ID: ${response.data.process_id}`,
        });

        // Start monitoring this process
        monitorProcess(response.data.process_id);
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Blog checking failed',
      });
    } finally {
      setCheckingBlogs(false);
    }
  };

  const handleVerifySingleEmail = async () => {
    if (!singleEmail.trim()) return;

    setVerifying(true);
    setMessage(null);

    try {
      const response = await apiService.post('/email/verify-single', { email: singleEmail });
      const quality = response.data.quality ?? '—';
      const statusLabel = response.data.status || 'n/a';
      const isValid = response.data.is_valid;
      setMessage({
        type: isValid ? 'success' : 'error',
        text: `${isValid ? 'Deliverable' : 'Undeliverable'} (score ${quality}) — ${statusLabel}${response.data.notes ? ` (${response.data.notes})` : ''}.`,
      });
      if (currentDataId) {
        await loadEmailData(currentDataId);
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Verification failed',
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleScrapeEmails = async () => {
    if (!scrapeDomain.trim()) return;

    setScraping(true);
    setMessage(null);

    try {
      const response = await apiService.scrapeEmails(scrapeDomain);
      setEmailData(response.data);
      setMessage({
        type: 'success',
        text: `Scraped ${response.data.length} emails from ${scrapeDomain}`,
      });
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Scraping failed',
      });
    } finally {
      setScraping(false);
    }
  };


const startPipeline = async () => {
  if (!currentDataId) return;

  let selectedSteps = Object.entries(processingOptions)
    .filter(([_, enabled]) => enabled)
    .map(([step, _]) => step);

  // Smart optimization: If all three steps are selected, remove email_verify
  // since email_scrape already includes verification
  if (selectedSteps.includes('blog_check') && 
      selectedSteps.includes('email_scrape') && 
      selectedSteps.includes('email_verify')) {
    selectedSteps = selectedSteps.filter(step => step !== 'email_verify');
    
    setMessage({
      type: 'info',
      text: '⚡ Pipeline optimized: Email verification is included in scraping, skipping separate verification step',
    });
  }

  if (selectedSteps.length === 0) {
    setMessage({
      type: 'error',
      text: 'Please select at least one processing step',
    });
    return;
  }

  setStartingPipeline(true);
  try {
    const response = await apiService.post('/pipeline/start', {
      data_id: currentDataId,
      steps: selectedSteps,
    });

    setMessage({
      type: 'success',
      text: `Pipeline started! Process ID: ${response.data.process_id}`,
    });

    // Connect to WebSocket for real-time updates
    connectWebSocket(response.data.process_id);
    
    setPipelineDialog(false);
    setProcessingOptions({ blog_check: false, email_scrape: false, email_verify: false });
    await fetchActiveProcesses();
  } catch (error: any) {
    setMessage({
      type: 'error',
      text: error.response?.data?.detail || 'Failed to start pipeline',
    });
  } finally {
    setStartingPipeline(false);
  }
};


  const stopProcess = async (processId: string) => {
    try {
      await apiService.post(`/pipeline/stop/${processId}`);
      setMessage({
        type: 'info',
        text: `Process ${processId.substring(0, 8)} stopped`,
      });
      await fetchActiveProcesses();
    } catch (error) {
      setMessage({
        type: 'error',
        text: 'Failed to stop process',
      });
    }
  };

  const handleDeleteCurrentUpload = async () => {
    if (!currentDataId) return;

    const confirmed = window.confirm('Delete this upload and all associated emails? This action cannot be undone.');
    if (!confirmed) {
      return;
    }

    setDeleteLoading(true);
    try {
      await apiService.deleteUpload(currentDataId);
      setMessage({ type: 'success', text: 'Upload deleted successfully.' });
      setEmailData([]);
      setCurrentDataId(null);
      setFilters({ status: 'all', search: '', sortBy: 'quality', sortOrder: 'desc' });
      await fetchActiveProcesses();
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to delete upload. Please try again.' });
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDownloadExcel = async () => {
    if (!currentDataId) return;

    try {
      const { blob, filename } = await apiService.downloadExcel(currentDataId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = filename || `email_data_${currentDataId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      setMessage({
        type: 'error',
        text: 'Download failed',
      });
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
      const startIndex = gridRows.findIndex(row => row.id === dragStartId);
      const currentIndex = gridRows.findIndex(row => row.id === rowId);
      
      if (startIndex !== -1 && currentIndex !== -1) {
        const minIndex = Math.min(startIndex, currentIndex);
        const maxIndex = Math.max(startIndex, currentIndex);
        const rangeIds = gridRows.slice(minIndex, maxIndex + 1).map(row => row.id);
        
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
            handleRowMouseDown(rowId);
          }
        } else if (e.type === 'mouseenter' && rowId) {
          handleRowMouseEnter(rowId);
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
  }, [isDragging, dragStartId, gridRows]);

  const columns: GridColDef[] = [
    {
      field: 'index',
      headerName: '#',
      width: 70,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const index = gridRows.findIndex(row => row.id === params.row.id);
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
                handleDeleteSingleRow(params.row.id);
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
      sortable: true,
      filterable: true,
    },
    { 
      field: 'email', 
      headerName: 'Email 1', 
      minWidth: 180, 
      flex: 0.9,
      sortable: true,
      filterable: true,
    },
    {
      field: 'verification_quality',
      headerName: 'Score 1',
      minWidth: 80,
      type: 'number',
      sortable: true,
      filterable: true,
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
      sortable: true,
      filterable: true,
      type: 'singleSelect',
      valueOptions: ['Verified', 'Pending', 'Invalid', 'Risky'],
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
      sortable: false,
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
      sortable: true,
      filterable: true,
    },
    {
      field: 'email_2_quality',
      headerName: 'Score 2',
      minWidth: 80,
      type: 'number',
      sortable: true,
      filterable: true,
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
      type: 'singleSelect',
      valueOptions: ['Verified', 'Pending', 'Invalid', 'Risky'],
      sortable: true,
      filterable: true,
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
      sortable: false,
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
      sortable: true,
      filterable: true,
    },
    {
      field: 'email_3_quality',
      headerName: 'Score 3',
      minWidth: 80,
      type: 'number',
      sortable: true,
      filterable: true,
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
      type: 'singleSelect',
      valueOptions: ['Verified', 'Pending', 'Invalid', 'Risky'],
      sortable: true,
      filterable: true,
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
      sortable: false,
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
      sortable: true,
      filterable: true,
      renderCell: (params) => params.value || '—',
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
      type: 'singleSelect',
      valueOptions: ['upload', 'scrape', 'manual', 'import'],
      sortable: true,
      filterable: true,
      valueGetter: (params) => params.value || 'upload',
    },
  ];

  // Ensure all required columns are included and ordered properly
  const columnOrder = [
    'index', 'actions', 'website', 'email', 'verification_quality', 'verification_status', 'verification_notes',
    'email_2', 'email_2_quality', 'email_2_status', 'email_2_notes',
    'email_3', 'email_3_quality', 'email_3_status', 'email_3_notes',
    'phone', 'links', 'is_blog', 'blog_score', 'created_at', 'source'
  ];
  columns.sort((a, b) => {
    const aIndex = columnOrder.indexOf(a.field);
    const bIndex = columnOrder.indexOf(b.field);
    // If field is not in columnOrder, put it at the end
    if (aIndex === -1) return 1;
    if (bIndex === -1) return -1;
    return aIndex - bIndex;
  });
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        Email Verification and Scraping
      </Typography>

      {message && (
        <Alert severity={message.type} sx={{ mb: 3 }} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      {/* Active Processes Banner */}
      {activeProcesses.length > 0 && (
        <Card sx={{ mb: 3, bgcolor: '#f5f5f5' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Timeline sx={{ mr: 1 }} />
              Active Processes ({activeProcesses.length})
            </Typography>
            <Grid container spacing={2}>
              {activeProcesses.map((process) => (
                <Grid item xs={12} md={6} key={process.process_id}>
                  <Card variant="outlined">
                    <CardContent sx={{ py: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Box>
                          <Typography variant="subtitle2">
                            {process.process_id.substring(0, 12)}...
                          </Typography>
                          <Typography variant="body2" color="textSecondary">
                            {process.current_step} - {process.processed_items || 0}/{process.total_items || 0}
                          </Typography>
                          <LinearProgress 
                            variant="determinate" 
                            value={process.progress || 0} 
                            sx={{ mt: 1, width: 200 }}
                          />
                        </Box>
                        <Box>
                          <Chip 
                            label={process.status} 
                            color={process.status === 'running' ? 'primary' : 'default'}
                            size="small"
                          />
                          {process.status === 'running' && (
                            <IconButton 
                              size="small" 
                              onClick={() => stopProcess(process.process_id)}
                              color="error"
                            >
                              <Stop />
                            </IconButton>
                          )}
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)}>
          <Tab label="File Upload" icon={<Upload />} />
          <Tab label="Single Email" icon={<Email />} />
          <Tab label="Web Scraping" icon={<Web />} />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        {/* File Upload Panel */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Upload Excel File
                </Typography>
                
                <Box sx={{ mb: 3 }}>
                  <input
                    accept=".xlsx,.xls,.csv,.tsv,.txt"
                    style={{ display: 'none' }}
                    id="file-upload"
                    type="file"
                    onChange={handleFileSelect}
                  />
                  <label htmlFor="file-upload">
                    <Button 
                      variant="outlined" 
                      component="span" 
                      startIcon={<CloudUpload />}
                      size="large"
                      sx={{ mr: 2 }}
                    >
                      Select File
                    </Button>
                  </label>
                  
                  {selectedFile && (
                    <Box sx={{ 
                      mt: 2, 
                      p: 2, 
                      bgcolor: 'background.paper', 
                      borderRadius: 1,
                      border: 1,
                      borderColor: 'divider'
                    }}>
                      <Typography variant="body2">
                        <strong>Selected:</strong> {selectedFile.name}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        Size: {(selectedFile.size / 1024).toFixed(1)} KB
                      </Typography>
                    </Box>
                  )}
                </Box>

                <Divider sx={{ mb: 2 }} />

                <FormControlLabel
                  control={
                    <Checkbox
                      checked={autoProcessAfterUpload}
                      onChange={(e) => setAutoProcessAfterUpload(e.target.checked)}
                    />
                  }
                  label="Auto-process after upload"
                />

                {autoProcessAfterUpload && (
                  <Box sx={{ ml: 4, mt: 2 }}>
                    <Typography variant="body2" gutterBottom>
                      Select processing steps:
                    </Typography>
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={processingOptions.blog_check}
                          onChange={(e) => setProcessingOptions(prev => ({
                            ...prev, blog_check: e.target.checked
                          }))}
                        />
                      }
                      label="Blog Detection"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={processingOptions.email_scrape}
                          onChange={(event) => {
                            const checked = event.target.checked;
                            setProcessingOptions((prev) => ({
                              ...prev,
                              email_scrape: checked,
                              email_verify: checked ? true : prev.email_verify,
                            }));
                          }}
                        />
                      }
                      label="Email Scraping"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={processingOptions.email_verify}
                          onChange={(event) => {
                            const checked = event.target.checked;
                            setProcessingOptions((prev) => ({
                              ...prev,
                              email_verify: checked,
                              email_scrape: checked ? prev.email_scrape : false,
                            }));
                          }}
                        />
                      }
                      label="Email Verification"
                    />
                  </Box>
                )}

                <Box sx={{ mt: 3 }}>
                  <Button
                    variant="contained"
                    onClick={handleFileUpload}
                    disabled={!selectedFile || uploading}
                    startIcon={uploading ? <CircularProgress size={20} color="inherit" /> : <Upload />}
                    size="large"
                  >
                    {uploading ? 'Uploading...' : 'Upload File'}
                  </Button>
                </Box>

                {uploading && <LinearProgress sx={{ mt: 2 }} />}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <Info sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Upload Guidelines
                </Typography>
                <Typography variant="body2" paragraph>
                  Your file should contain columns for:
                </Typography>
                <ul>
                  <li>Email addresses</li>
                  <li>Names (optional)</li>
                  <li>Company names (optional)</li>
                  <li>Websites (optional)</li>
                </ul>
                <Typography variant="body2" color="textSecondary">
                  Supported formats: .xlsx, .xls, .csv, .tsv, .txt
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        {/* Single Email Verification Panel */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Verify Single Email
            </Typography>
            
            <Box display="flex" gap={2} alignItems="center" sx={{ mb: 3 }}>
              <TextField
                fullWidth
                label="Email Address"
                value={singleEmail}
                onChange={(e) => setSingleEmail(e.target.value)}
                placeholder="example@domain.com"
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleVerifySingleEmail();
                  }
                }}
              />
              <Button
                variant="contained"
                onClick={handleVerifySingleEmail}
                disabled={!singleEmail.trim() || verifying}
                startIcon={<Verified />}
              >
                {verifying ? 'Verifying...' : 'Verify'}
              </Button>
            </Box>

            {verifying && <LinearProgress />}
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        {/* Web Scraping Panel */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Scrape Emails from Website
            </Typography>
            
            <Box display="flex" gap={2} alignItems="center" sx={{ mb: 3 }}>
              <TextField
                fullWidth
                label="Domain or URL"
                value={scrapeDomain}
                onChange={(e) => setScrapeDomain(e.target.value)}
                placeholder="example.com or https://example.com"
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleScrapeEmails();
                  }
                }}
              />
              <Button
                variant="contained"
                onClick={handleScrapeEmails}
                disabled={!scrapeDomain.trim() || scraping}
                startIcon={<Search />}
              >
                {scraping ? 'Scraping...' : 'Scrape'}
              </Button>
            </Box>

            {scraping && <LinearProgress />}

            <Alert severity="info">
              This will extract and verify emails from the website's pages.
              The process may take a few minutes depending on the site size.
            </Alert>
          </CardContent>
        </Card>
      </TabPanel>

      {/* Actions Section */}
      {currentDataId && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Processing Actions
            </Typography>

            {/* Selection Info */}
            {selectedRows.length > 0 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                {selectedRows.length} record(s) selected
              </Alert>
            )}

            {/* Processing Filters */}
            <Paper sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
              <Typography variant="subtitle2" gutterBottom>
                Processing Filters
              </Typography>
              <Stack spacing={1}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={processingFilters.onlyWithBlog}
                      onChange={(e) => setProcessingFilters({
                        ...processingFilters,
                        onlyWithBlog: e.target.checked
                      })}
                    />
                  }
                  label="Only process entries with blog present"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={processingFilters.onlyUnverified}
                      onChange={(e) => setProcessingFilters({
                        ...processingFilters,
                        onlyUnverified: e.target.checked
                      })}
                    />
                  }
                  label="Only process unverified emails"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={processingFilters.skipProcessed}
                      onChange={(e) => setProcessingFilters({
                        ...processingFilters,
                        skipProcessed: e.target.checked
                      })}
                    />
                  }
                  label="Skip already processed entries"
                />
              </Stack>
            </Paper>

            {/* Action Buttons */}
            <Box>
              <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
                Processing Actions
              </Typography>
              <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 2 }}>
                <Button
                  variant="contained"
                  onClick={() => selectedRows.length > 0 ? handleCheckBlogsSelected() : handleCheckBlogs()}
                  disabled={checkingBlogs || !currentDataId}
                  startIcon={checkingBlogs ? <CircularProgress size={20} /> : <Web />}
                >
                  {checkingBlogs ? 'Checking...' :
                   selectedRows.length > 0 ? `Check Blogs (${selectedRows.length})` : 'Check All Blogs'}
                </Button>

                <Button
                  variant="outlined"
                  onClick={() => selectedRows.length > 0 ? handleVerifySelected() : handleVerifyEmails()}
                  disabled={verifying}
                  startIcon={verifying ? <CircularProgress size={20} /> : <Verified />}
                  color="success"
                >
                  {verifying ? 'Verifying...' :
                   selectedRows.length > 0 ? `Verify (${selectedRows.length})` : 'Verify All'}
                </Button>

                <Button
                  variant="contained"
                  onClick={() => setPipelineDialog(true)}
                  startIcon={<PlayArrow />}
                  color="primary"
                >
                  Start Pipeline
                </Button>

                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<Delete />}
                  onClick={handleBulkDelete}
                  disabled={selectedRows.length === 0}
                >
                  Delete Selected ({selectedRows.length})
                </Button>
              </Stack>

              <Typography variant="subtitle2" gutterBottom sx={{ mb: 2, mt: 2 }}>
                Data Actions
              </Typography>
              <Stack direction="row" spacing={2} flexWrap="wrap">
                <Button
                  variant="outlined"
                  onClick={handleDownloadExcel}
                  startIcon={<Download />}
                  disabled={!currentDataId}
                >
                  Download Excel
                </Button>

                <Button
                  variant="outlined"
                  onClick={() => window.location.href = '/data-management'}
                  startIcon={<Storage />}
                >
                  Manage Data
                </Button>

                <Button
                  variant="outlined"
                  onClick={() => currentDataId && loadEmailData(currentDataId)}
                  startIcon={<Refresh />}
                  disabled={loadingEmails || !currentDataId}
                >
                  Refresh
                </Button>

                <Button
                  variant="outlined"
                  color="error"
                  onClick={handleDeleteCurrentUpload}
                  startIcon={<Delete />}
                  disabled={!currentDataId}
                >
                  Delete Upload
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Email Data Grid */}
      {(currentDataId || emailData.length > 0) && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Email Data ({emailData.length} records)
            </Typography>

            <Stack direction="row" spacing={2} mb={2} alignItems="center">
              <TextField
                label="Search"
                size="small"
                value={filters.search}
                onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
                sx={{ minWidth: 300 }}
                disabled={!currentDataId}
                placeholder="Search emails, websites, companies..."
              />
              <Button
                variant="text"
                onClick={() => setFilters({ status: 'all', search: '', sortBy: 'quality', sortOrder: 'desc' })}
                disabled={!currentDataId}
              >
                Clear Search
              </Button>
            </Stack>

            <Stack direction="row" spacing={1.5} mb={2} flexWrap="wrap">
              <Chip label={`${verificationTotals.verified} verified`} color="success" size="small" />
              <Chip label={`${verificationTotals.invalid} invalid`} color={verificationTotals.invalid ? 'error' : 'default'} size="small" />
              <Chip label={`${verificationTotals.pending} pending`} color={verificationTotals.pending ? 'warning' : 'default'} size="small" />
            </Stack>

            {loadingEmails && <LinearProgress sx={{ mb: 2 }} />}

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
                        {item.field === 'created_at' ? (
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
                      type={item.field === 'created_at' ? 'date' : 'text'}
                      value={item.value || ''}
                      onChange={(e) => {
                        const newItems = [...filterModel.items];
                        newItems[index] = { ...newItems[index], value: e.target.value };
                        setFilterModel((prev) => ({ ...prev, items: newItems }));
                      }}
                      sx={{ minWidth: 200 }}
                      disabled={item.operator === 'isEmpty' || item.operator === 'isNotEmpty'}
                      InputLabelProps={item.field === 'created_at' ? { shrink: true } : undefined}
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

            {/* Filter Logic Operator Control - Old version, keeping for reference but hidden */}
            {false && filterModel.items.length > 1 && (
              <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
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
            )}

            <Box 
              sx={{ width: '100%' }}
              onMouseUp={handleRowMouseUp}
            >
            <DataGrid
              rows={gridRows}
              columns={columns}

              /* Pagination */
              pagination
              paginationModel={paginationModel}
              onPaginationModelChange={setPaginationModel}
              pageSizeOptions={[10, 25, 50, 100]}
              hideFooter={false}

              /* Loading + basic table config */
              loading={loadingEmails}
              autoHeight={false}
              rowHeight={52}
              columnHeaderHeight={56}

              /* Selection: keep your custom click + drag behavior */
              onRowClick={handleRowClick}
              getRowClassName={(params) => (selectedRows.includes(params.id) ? 'row-selected' : '')}
              disableVirtualization={false}

              /* Toolbar (your CustomToolbar) */
              slots={{
                toolbar: () => (
                  <CustomToolbar
                    onAddFilter={handleAddFilter}
                    filterCount={filterModel.items.length}
                  />
                ),
              }}

              /* Client-side filtering (you already apply custom filters before passing rows) */
              filterMode="client"
              slotProps={{
                filterPanel: {
                  logicOperators: [GridLogicOperator.And, GridLogicOperator.Or],
                  columnsSort: 'asc',
                  filterFormProps: {
                    logicOperatorInputProps: { variant: 'outlined', size: 'small' },
                    columnInputProps: { variant: 'outlined', size: 'small' },
                    operatorInputProps: { variant: 'outlined', size: 'small' },
                    valueInputProps: { variant: 'outlined', size: 'small' },
                  },
                },
              }}

              /* Styling (kept from your original) */
              sx={{
                height: '600px',
                '& .MuiDataGrid-cell': { fontSize: '0.875rem' },
                '& .MuiDataGrid-row': {
                  cursor: 'pointer',
                  userSelect: 'none',
                  '&:hover': { backgroundColor: 'action.hover' },
                },
                '& .MuiDataGrid-virtualScroller': { overflowY: 'auto !important' },
                '& .row-selected': {
                  backgroundColor: 'rgba(25, 118, 210, 0.12) !important',
                  '&:hover': { backgroundColor: 'rgba(25, 118, 210, 0.24) !important' },
                },
                '& .MuiDataGrid-filterForm': { gap: 1 },
                '& .MuiDataGrid-filterFormLogicOperatorInput': { mr: 2 },
              }}
            />

            </Box>
          </CardContent>
        </Card>
      )}

      {/* Pipeline Configuration Dialog */}
      <Dialog open={pipelineDialog} onClose={() => setPipelineDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Configure Processing Pipeline</DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom sx={{ mt: 2 }}>
            Select the processing steps to run on your data:
          </Typography>
          
          <FormControlLabel
            control={
              <Checkbox
                checked={processingOptions.blog_check}
                onChange={(e) => setProcessingOptions(prev => ({
                  ...prev, blog_check: e.target.checked
                }))}
              />
            }
            label="Blog Detection - Check if domains have blogs"
          />
          
          <FormControlLabel
            control={
              <Checkbox
                checked={processingOptions.email_scrape}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setProcessingOptions((prev) => ({
                    ...prev,
                    email_scrape: checked,
                    email_verify: checked ? true : prev.email_verify,
                  }));
                }}
              />
            }
            label="Email Scraping - Extract additional emails from websites"
          />
          
          <FormControlLabel
            control={
              <Checkbox
                checked={processingOptions.email_verify}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setProcessingOptions((prev) => ({
                    ...prev,
                    email_verify: checked,
                    email_scrape: checked ? prev.email_scrape : false,
                  }));
                }}
              />
            }
            label="Email Verification - Verify email deliverability"
          />
          
          <Alert severity="info" sx={{ mt: 2 }}>
            The pipeline will process all {emailData.length} records in sequence. Email scraping automatically enables verification so deliverability is scored before saving. You can monitor progress in real time.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPipelineDialog(false)}>Cancel</Button>
          <Button
            onClick={startPipeline}
            variant="contained"
            startIcon={startingPipeline ? <CircularProgress size={20} color="inherit" /> : <PlayArrow />}
            disabled={startingPipeline}
          >
            {startingPipeline ? 'Starting...' : 'Start Pipeline'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Verification Results */}
      {verificationResults.length > 0 && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Verification Results
            </Typography>
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Email</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Quality</TableCell>
                    <TableCell>Deliverability Status</TableCell>
                    <TableCell>Notes</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {verificationResults.map((result, index) => (
                    <TableRow key={index}>
                      <TableCell>{result.email}</TableCell>
                      <TableCell>
                        <Chip
                          label={result.is_valid ? 'Valid' : 'Invalid'}
                          color={result.is_valid ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>{result.quality ?? '—'}</TableCell>
                      <TableCell>{result.status || '—'}</TableCell>
                      <TableCell>{result.notes || '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

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
            onClick={handleSaveEdit}
            variant="contained"
            startIcon={saveLoading ? <CircularProgress size={20} /> : <SaveIcon />}
            disabled={saveLoading}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
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
    </Container>
  );
};

export default EmailVerification;
