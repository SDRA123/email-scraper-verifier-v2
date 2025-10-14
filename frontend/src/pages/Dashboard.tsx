import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActionArea,
  Button,
  Box,
  LinearProgress,
  Chip,
  Alert,
  AlertTitle,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  Checkbox,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  IconButton,
  CircularProgress,
  TextField,
  FormControl,
  Select,
  MenuItem,
  InputLabel,
  Tooltip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from '@mui/material';
import {
  Email as EmailIcon,
  Upload as UploadIcon,
  Verified as VerifiedIcon,
  Assessment as AssessmentIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  Timeline as TimelineIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Pending as PendingIcon,
  Cancel as CancelIcon,
  Delete as DeleteIcon,
  Public as PublicIcon,
  Download as DownloadIcon,
} from '@mui/icons-material';
import apiService from '../services/apiService';
import { DashboardEntrySummary, DashboardEmailSummary, DashboardSummary } from '../types';

interface UploadHistory {
  id: number;
  filename: string;
  created_at: string;
  total_emails: number;
  verified_count: number;
  invalid_count: number;
  pending_count: number;
  unique_emails: number;
  unique_websites: number;
}

interface ProcessInfo {
  process_id: string;
  status: string;
  current_step: string;
  progress: number;
  total_items: number;
  processed_items: number;
  start_time: string;
  end_time?: string;
}

type DetailType = 'entries' | 'emails' | 'verified' | 'invalid';

interface DetailViewState {
  open: boolean;
  title: string;
  type: DetailType;
  rows: (DashboardEntrySummary | DashboardEmailSummary)[];
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [uploads, setUploads] = useState<UploadHistory[]>([]);
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [pipelineDialog, setPipelineDialog] = useState(false);
  const [selectedUpload, setSelectedUpload] = useState<UploadHistory | null>(null);
  const [pipelineSteps, setPipelineSteps] = useState({
    blog_check: false,
    email_scrape: false,
    email_verify: false,
  });
  const [processingSteps, setProcessingSteps] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [showAllUploads, setShowAllUploads] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'all' | 'verified' | 'invalid' | 'pending'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [detailView, setDetailView] = useState<DetailViewState>({ open: false, title: '', type: 'entries', rows: [] });
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [deletingUploadId, setDeletingUploadId] = useState<number | null>(null);
  const [downloadingCategory, setDownloadingCategory] = useState<DetailType | null>(null);

  const filteredUploads = useMemo(() => {
    const normalizedQuery = searchTerm.trim().toLowerCase();

    return uploads.filter((upload) => {
      const matchesSearch = normalizedQuery
        ? upload.filename.toLowerCase().includes(normalizedQuery)
        : true;

      let matchesStatus = true;
      switch (statusFilter) {
        case 'verified':
          matchesStatus = upload.verified_count > 0 && upload.invalid_count === 0 && upload.pending_count === 0;
          break;
        case 'invalid':
          matchesStatus = upload.invalid_count > 0;
          break;
        case 'pending':
          matchesStatus = upload.pending_count > 0;
          break;
        default:
          matchesStatus = true;
      }

      return matchesSearch && matchesStatus;
    });
  }, [uploads, searchTerm, statusFilter]);

  const visibleUploads = useMemo(
    () => (showAllUploads ? filteredUploads : filteredUploads.slice(0, 6)),
    [filteredUploads, showAllUploads]
  );

  const hasMoreUploads = filteredUploads.length > 6;

  const fetchDashboard = useCallback(async () => {
    try {
      setLoadingSummary(true);
      const [historyResponse, summaryResponse] = await Promise.all([
        apiService.getDataHistory(),
        apiService.getDashboardSummary(),
      ]);

      setUploads(historyResponse.data);
      setSummary(summaryResponse.data);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      setFeedback({ type: 'error', text: 'Failed to refresh dashboard data' });
    } finally {
      setLoadingSummary(false);
    }
  }, []);

  const fetchProcesses = useCallback(async () => {
    try {
      const response = await apiService.get('/pipeline/processes');
      setProcesses(response.data);
    } catch (error) {
      console.error('Error fetching processes:', error);
    }
  }, []);

  const scrollToProcesses = useCallback(() => {
    const element = document.getElementById('active-processes');
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      fetchProcesses();
    }
  }, [fetchProcesses]);

  const fetchDashboardData = useCallback(async () => {
    await Promise.all([fetchDashboard(), fetchProcesses()]);
  }, [fetchDashboard, fetchProcesses]);

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchProcesses, 2000);
    return () => clearInterval(interval);
  }, [fetchDashboardData, fetchProcesses]);

  const downloadDashboardExcel = async (category: DetailType) => {
    if (!summary) {
      setFeedback({ type: 'info', text: 'No dashboard data available yet.' });
      return;
    }

    setDownloadingCategory(category);
    try {
      const { blob, filename } = await apiService.downloadDashboard(category);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      const timestamp = new Date().toISOString().replace(/[:.-]/g, '').slice(0, 15);
      anchor.download = filename || `dashboard_${category}_${timestamp}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading dashboard data:', error);
      setFeedback({ type: 'error', text: 'Failed to download dashboard data. Please try again.' });
    } finally {
      setDownloadingCategory(null);
    }
  };

  const downloadUploadExcel = async (uploadId: number, event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      const { blob, filename } = await apiService.downloadExcel(uploadId);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename || `upload_${uploadId}_data.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading upload data:', error);
      setFeedback({ type: 'error', text: 'Failed to download file. Please try again.' });
    }
  };

  const startPipeline = async () => {
    if (!selectedUpload) return;

    const selectedSteps = Object.entries(pipelineSteps)
      .filter(([_, enabled]) => enabled)
      .map(([step, _]) => step);

    if (selectedSteps.length === 0) {
      alert('Please select at least one processing step');
      return;
    }

    // Smart step filtering to avoid double verification
    let optimizedSteps = [...selectedSteps];
    let optimizationApplied = false;

    // If both email_scrape and email_verify are selected, remove email_verify
    // since email_scrape already does verification by default
    if (optimizedSteps.includes('email_scrape') && optimizedSteps.includes('email_verify')) {
      optimizedSteps = optimizedSteps.filter(step => step !== 'email_verify');
      optimizationApplied = true;
      console.log('Pipeline optimization: Removed email_verify since email_scrape includes verification');
    }

    setProcessingSteps(true);
    try {
      const response = await apiService.post('/pipeline/start', {
        data_id: selectedUpload.id,
        steps: optimizedSteps,
      });

      console.log('Pipeline started:', response.data);

      // Show optimization feedback if applied
      if (optimizationApplied) {
        setFeedback({
          type: 'info',
          text: `Pipeline optimized: Email scraping includes verification, so the separate verification step was skipped to prevent duplication. Processing ${response.data.total_items} items.`
        });
      } else {
        setFeedback({
          type: 'success',
          text: `Pipeline started successfully. Processing ${response.data.total_items} items.`
        });
      }

      setPipelineDialog(false);
      setSelectedUpload(null);
      setPipelineSteps({ blog_check: false, email_scrape: false, email_verify: false });
      
      // Refresh processes immediately
      await Promise.all([fetchProcesses(), fetchDashboard()]);
    } catch (error) {
      console.error('Error starting pipeline:', error);
      setFeedback({ type: 'error', text: 'Error starting pipeline. Please try again.' });
    } finally {
      setProcessingSteps(false);
    }
  };

  const stopProcess = async (processId: string) => {
    try {
      await apiService.post(`/pipeline/stop/${processId}`);
      await fetchProcesses();
    } catch (error) {
      console.error('Error stopping process:', error);
    }
  };

  const handleDeleteUpload = async (upload: UploadHistory) => {
    const confirmDelete = window.confirm(`Delete upload "${upload.filename}" and all associated data? This action cannot be undone.`);
    if (!confirmDelete) {
      return;
    }

    setDeletingUploadId(upload.id);
    try {
      await apiService.deleteUpload(upload.id);
      setFeedback({ type: 'success', text: `Removed ${upload.filename} from your workspace.` });
      await fetchDashboard();
    } catch (error) {
      console.error('Error deleting upload:', error);
      setFeedback({ type: 'error', text: 'Failed to delete upload. Please try again.' });
    } finally {
      setDeletingUploadId(null);
    }
  };

  const openSummaryDialog = (type: DetailType) => {
    if (!summary) return;

    let title = '';
    let rows: (DashboardEntrySummary | DashboardEmailSummary)[] = [];

    switch (type) {
      case 'entries':
        title = 'All Unique Entries';
        rows = summary.entries;
        break;
      case 'emails':
        title = 'All Unique Emails';
        rows = summary.emails;
        break;
      case 'verified':
        title = 'Verified Emails';
        rows = summary.verified_list;
        break;
      case 'invalid':
        title = 'Emails Requiring Attention';
        rows = summary.invalid_list;
        break;
      default:
        break;
    }

    setDetailView({ open: true, type, title, rows });
  };

  const closeDetailDialog = () => {
    setDetailView((prev) => ({ ...prev, open: false }));
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckIcon color="success" />;
      case 'running':
        return <CircularProgress size={20} />;
      case 'failed':
        return <ErrorIcon color="error" />;
      case 'stopped':
        return <StopIcon color="warning" />;
      default:
        return <PendingIcon />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'running':
        return 'primary';
      case 'failed':
        return 'error';
      case 'stopped':
        return 'warning';
      default:
        return 'default';
    }
  };

  const handleStatClick = (filterType: 'all' | 'verified' | 'invalid') => {
    navigate(`/data-management?filter=${filterType}`);
  };

  const StatButton = ({
    title,
    value,
    icon,
    color,
    onClick,
    onDownload,
    downloading = false,
  }: {
    title: string;
    value: number;
    icon: React.ReactNode;
    color: string;
    onClick?: () => void;
    onDownload?: () => void;
    downloading?: boolean;
  }) => (
    <Card sx={{ height: '100%' }}>
      <CardActionArea onClick={onClick} disabled={!onClick} sx={{ height: '100%' }}>
        <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box>
              <Typography color="textSecondary" gutterBottom variant="h6">
                {title}
              </Typography>
              <Typography variant="h4" component="div" sx={{ color }}>
                {value.toLocaleString()}
              </Typography>
              {onClick && (
                <Typography variant="caption" color="textSecondary">
                  Click to view in Data Management
                </Typography>
              )}
            </Box>
            <Box sx={{ color }}>{icon}</Box>
          </Box>
          {onDownload && (
            <Button
              variant="text"
              size="small"
              startIcon={downloading ? <CircularProgress size={16} /> : <DownloadIcon />}
              onClick={(event) => {
                event.stopPropagation();
                onDownload();
              }}
              disabled={downloading}
              sx={{ alignSelf: 'flex-start', mt: 0.5, px: 0 }}
            >
              {downloading ? 'Downloading…' : 'Download'}
            </Button>
          )}
        </CardContent>
      </CardActionArea>
    </Card>
  );

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">
          Dashboard
        </Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchDashboardData}
        >
          Refresh
        </Button>
      </Box>

          {feedback && (
            <Alert severity={feedback.type} sx={{ mb: 2 }} onClose={() => setFeedback(null)}>
              {feedback.text}
            </Alert>
          )}

          {loadingSummary && <LinearProgress sx={{ mb: 2 }} />}

      {/* Statistics Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
              <StatButton
                title="Total Entries"
                value={summary?.total_entries ?? 0}
                icon={<PublicIcon sx={{ fontSize: 40 }} />}
                color="#1976d2"
                onClick={() => handleStatClick('all')}
                onDownload={summary ? () => downloadDashboardExcel('entries') : undefined}
                downloading={downloadingCategory === 'entries'}
              />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
              <StatButton
                title="Total Emails"
                value={summary?.total_emails ?? 0}
                icon={<EmailIcon sx={{ fontSize: 40 }} />}
                color="#0288d1"
                onClick={() => handleStatClick('all')}
                onDownload={summary ? () => downloadDashboardExcel('emails') : undefined}
                downloading={downloadingCategory === 'emails'}
              />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
              <StatButton
                title="Verified Emails"
                value={summary?.verified_emails ?? 0}
                icon={<VerifiedIcon sx={{ fontSize: 40 }} />}
                color="#2e7d32"
                onClick={() => handleStatClick('verified')}
                onDownload={summary ? () => downloadDashboardExcel('verified') : undefined}
                downloading={downloadingCategory === 'verified'}
              />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
              <StatButton
                title="Invalid Emails"
                value={summary?.invalid_emails ?? 0}
                icon={<CancelIcon sx={{ fontSize: 40 }} />}
                color="#d32f2f"
                onClick={() => handleStatClick('invalid')}
                onDownload={summary ? () => downloadDashboardExcel('invalid') : undefined}
                downloading={downloadingCategory === 'invalid'}
              />
        </Grid>
      </Grid>

      {/* Active Processes */}
      {processes.length > 0 && (
        <Card id="active-processes" sx={{ mb: { xs: 4, md: 3 } }}>
          <CardContent>
            <Typography variant="h5" gutterBottom>
              Active Processes
            </Typography>
            <List>
              {processes.map((process) => (
                <ListItem key={process.process_id} divider>
                  <ListItemIcon>
                    {getStatusIcon(process.status)}
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="subtitle1">
                          Process {process.process_id.substring(0, 8)}...
                        </Typography>
                        <Chip
                          label={process.status}
                          size="small"
                          color={getStatusColor(process.status) as any}
                        />
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography variant="body2">
                          Step: {process.current_step || 'Initializing'}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={1} mt={1}>
                          <LinearProgress
                            variant="determinate"
                            value={process.progress || 0}
                            sx={{ flexGrow: 1, height: 6, borderRadius: 3 }}
                          />
                          <Typography variant="caption">
                            {process.processed_items || 0}/{process.total_items || 0}
                          </Typography>
                        </Box>
                      </Box>
                    }
                  />
                  {process.status === 'running' && (
                    <IconButton
                      onClick={() => stopProcess(process.process_id)}
                      color="error"
                    >
                      <StopIcon />
                    </IconButton>
                  )}
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}

      {/* Recent Uploads */}
      <Card sx={{ mb: { xs: 4, md: 3 } }}>
        <CardContent>
          <Typography variant="h5" gutterBottom>
            Recent Uploads & Processing
          </Typography>

          <Box
            display="flex"
            flexDirection={{ xs: 'column', md: 'row' }}
            alignItems={{ md: 'center' }}
            gap={2}
            mb={2}
          >
            <TextField
              label="Search uploads"
              size="small"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              sx={{ flexGrow: 1 }}
            />
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="upload-status-filter">Status</InputLabel>
              <Select
                labelId="upload-status-filter"
                label="Status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
              >
                <MenuItem value="all">All statuses</MenuItem>
                <MenuItem value="verified">Verified</MenuItem>
                <MenuItem value="invalid">Needs attention</MenuItem>
                <MenuItem value="pending">Pending</MenuItem>
              </Select>
            </FormControl>
            <Chip
              label={`Total uploads: ${uploads.length}`}
              color="primary"
              variant="outlined"
            />
          </Box>
          
          {filteredUploads.length === 0 ? (
            <Alert severity="info">
              {uploads.length === 0
                ? 'No uploads yet. Start by uploading an Excel file with email data.'
                : 'No uploads match your current filters.'}
            </Alert>
          ) : (
            <>
              <Grid container spacing={2}>
                {visibleUploads.map((upload) => (
                  <Grid item xs={12} md={6} lg={4} key={upload.id}>
                    <Card 
                      variant="outlined"
                      sx={{
                        height: '100%',
                        bgcolor: 'background.paper',
                        borderColor: 'divider',
                        boxShadow: 2,
                        cursor: 'pointer',
                        transition: 'all 0.2s ease-in-out',
                        '&:hover': {
                          boxShadow: 4,
                          transform: 'translateY(-2px)',
                          borderColor: 'primary.main',
                        },
                      }}
                      onClick={() => navigate(`/email-verification?upload_id=${upload.id}`)}
                    >
                      <CardContent>
                        <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={1}>
                          <Box>
                            <Typography variant="h6" noWrap title={upload.filename}>
                              {upload.filename}
                            </Typography>
                            <Typography color="textSecondary" variant="body2">
                              {new Date(upload.created_at).toLocaleString()}
                            </Typography>
                          </Box>
                          <Tooltip title="Delete upload">
                            <span>
                              <IconButton
                                color="error"
                                size="small"
                                disabled={deletingUploadId === upload.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteUpload(upload);
                                }}
                              >
                                {deletingUploadId === upload.id ? (
                                  <CircularProgress size={16} />
                                ) : (
                                  <DeleteIcon fontSize="small" />
                                )}
                              </IconButton>
                            </span>
                          </Tooltip>
                        </Box>

                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, my: 2 }}>
                          <Chip
                            label={`${upload.unique_websites || upload.total_emails} entries`}
                            size="small"
                            variant="outlined"
                          />
                          <Chip
                            label={`${upload.unique_emails} emails`}
                            size="small"
                            color="info"
                            variant="outlined"
                          />
                          <Chip
                            label={`${upload.verified_count} verified`}
                            size="small"
                            color="success"
                            variant="filled"
                          />
                          {upload.invalid_count > 0 && (
                            <Chip
                              label={`${upload.invalid_count} invalid`}
                              size="small"
                              color="error"
                              variant="filled"
                            />
                          )}
                          {upload.pending_count > 0 && (
                            <Chip
                              label={`${upload.pending_count} pending`}
                              size="small"
                              color="warning"
                              variant="filled"
                            />
                          )}
                        </Box>

                        <Box display="flex" gap={1} alignItems="center" justifyContent="flex-end">
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<DownloadIcon fontSize="small" />}
                            onClick={(e) => downloadUploadExcel(upload.id, e)}
                            sx={{
                              minWidth: 'auto',
                              px: 2,
                              py: 0.5,
                              '& .MuiButton-startIcon': {
                                marginRight: 0.5,
                              }
                            }}
                          >
                            Download
                          </Button>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {hasMoreUploads && (
                <Box display="flex" justifyContent="center" mt={3}>
                  <Button onClick={() => setShowAllUploads((prev) => !prev)}>
                    {showAllUploads ? 'Show Less' : 'View More'}
                  </Button>
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>

        <Dialog
          open={detailView.open}
          onClose={closeDetailDialog}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>{detailView.title}</DialogTitle>
          <DialogContent dividers>
            {detailView.rows.length === 0 ? (
              <Typography variant="body2">No data available.</Typography>
            ) : detailView.type === 'entries' ? (
              <TableContainer component={Paper} sx={{ maxHeight: 420 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Website</TableCell>
                      <TableCell align="right">Uploads</TableCell>
                      <TableCell align="right">Emails</TableCell>
                      <TableCell align="right">Last Upload</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(detailView.rows as DashboardEntrySummary[]).map((entry) => (
                      <TableRow key={entry.website} hover>
                        <TableCell>{entry.website}</TableCell>
                        <TableCell align="right">{entry.upload_ids.length}</TableCell>
                        <TableCell align="right">{entry.email_count}</TableCell>
                        <TableCell align="right">
                          {entry.last_upload ? new Date(entry.last_upload).toLocaleString() : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <TableContainer component={Paper} sx={{ maxHeight: 420 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Email</TableCell>
                      <TableCell>Website</TableCell>
                      <TableCell align="right">Quality</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Notes</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(detailView.rows as DashboardEmailSummary[]).map((item) => (
                      <TableRow key={`${item.email}-${item.website || 'na'}`} hover>
                        <TableCell>{item.email}</TableCell>
                        <TableCell>{item.website || '—'}</TableCell>
                        <TableCell align="right">
                          {item.quality !== undefined && item.quality !== null ? (
                            <Chip
                              size="small"
                              color={item.verified ? 'success' : item.quality >= 50 ? 'warning' : 'error'}
                              label={item.quality}
                            />
                          ) : (
                            '—'
                          )}
                        </TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            color={item.verified ? 'success' : 'default'}
                            label={item.status || (item.verified ? 'Verified' : 'Pending')}
                          />
                        </TableCell>
                        <TableCell>{item.notes || '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={closeDetailDialog}>Close</Button>
          </DialogActions>
        </Dialog>

      {/* Quick Actions */}
      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h5" gutterBottom>
            Quick Actions
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Button
                variant="contained"
                fullWidth
                startIcon={<UploadIcon />}
                onClick={() => navigate('/email-verification')}
                sx={{ py: 2 }}
              >
                Upload & Process
              </Button>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Button
                variant="outlined"
                fullWidth
                startIcon={<EmailIcon />}
                onClick={() => navigate('/email-verification?mode=single')}
                sx={{ py: 2 }}
              >
                Verify Single Email
              </Button>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Button
                variant="outlined"
                fullWidth
                startIcon={<TimelineIcon />}
                onClick={scrollToProcesses}
                sx={{ py: 2 }}
              >
                Pipeline Status
              </Button>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Button
                variant="outlined"
                fullWidth
                startIcon={<AssessmentIcon />}
                onClick={() => navigate('/users')}
                sx={{ py: 2 }}
              >
                Manage Users
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Pipeline Configuration Dialog */}
      <Dialog open={pipelineDialog} onClose={() => setPipelineDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Configure Processing Pipeline
          {selectedUpload && (
            <Typography variant="body2" color="textSecondary">
              File: {selectedUpload.filename}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            Select the processing steps to run:
          </Typography>
          
          <FormControlLabel
            control={
              <Checkbox
                checked={pipelineSteps.blog_check}
                onChange={(e) => setPipelineSteps({ ...pipelineSteps, blog_check: e.target.checked })}
              />
            }
            label={
              <Box>
                <Typography variant="body1">Blog Detection</Typography>
                <Typography variant="body2" color="text.secondary">
                  Check if domains are blogs and analyze recent content
                </Typography>
              </Box>
            }
          />
          
          <FormControlLabel
            control={
              <Checkbox
                checked={pipelineSteps.email_scrape}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setPipelineSteps((prev) => ({
                    ...prev,
                    email_scrape: checked,
                    // Auto-enable verification when scraping is enabled
                    email_verify: checked ? true : prev.email_verify,
                  }));
                }}
              />
            }
            label={
              <Box>
                <Typography variant="body1">Email Scraping + Verification</Typography>
                <Typography variant="body2" color="text.secondary">
                  Extract emails from websites and verify them automatically (recommended for new data)
                </Typography>
                <Typography variant="caption" color="success.main" sx={{ fontWeight: 'bold' }}>
                  ⚡ Includes automatic email verification
                </Typography>
              </Box>
            }
          />
          
          <FormControlLabel
            control={
              <Checkbox
                checked={pipelineSteps.email_verify}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setPipelineSteps((prev) => ({
                    ...prev,
                    email_verify: checked,
                    // Auto-enable scraping when verification is enabled (unless user explicitly disables it)
                    email_scrape: checked ? prev.email_scrape : false,
                  }));
                }}
              />
            }
            label={
              <Box>
                <Typography variant="body1">Email Verification Only</Typography>
                <Typography variant="body2" color="text.secondary">
                  Verify existing emails without scraping new ones (use only if you already have emails)
                </Typography>
                {pipelineSteps.email_scrape && (
                  <Typography variant="caption" color="warning.main">
                    ⚠️ Will be skipped if email scraping is selected (already included)
                  </Typography>
                )}
              </Box>
            }
          />
          
          {pipelineSteps.email_scrape && pipelineSteps.email_verify && (
            <Alert severity="success" sx={{ mt: 2 }}>
              <AlertTitle>Smart Optimization Active</AlertTitle>
              Email scraping includes verification by default. The separate email verification step will be automatically skipped to prevent duplication and speed up processing.
            </Alert>
          )}
          
          <Alert severity="info" sx={{ mt: 2 }}>
            The pipeline will process all records in the selected file.
            You can monitor progress in real-time on the dashboard.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPipelineDialog(false)}>Cancel</Button>
          <Button
            onClick={startPipeline}
            variant="contained"
            disabled={processingSteps}
            startIcon={processingSteps ? <CircularProgress size={20} /> : <PlayIcon />}
          >
            {processingSteps ? 'Starting...' : 'Start Pipeline'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Dashboard;