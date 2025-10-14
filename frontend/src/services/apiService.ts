import axios, { AxiosInstance, AxiosResponse } from 'axios';
import { 
  LoginCredentials, 
  RegisterData, 
  User, 
  EmailData, 
  ExcelUploadResponse, 
  VerificationResult,
  AuthResponse,
  DashboardSummary,
  PipelineResponse,
  BlogCheckResponse
} from '../types';

class ApiService {
  private api: AxiosInstance;
  private baseURL = 'http://localhost:8000/api';

  constructor() {
    this.api = axios.create({
      baseURL: this.baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add request interceptor to ensure token is always sent
    this.api.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('token');
        console.log('Request interceptor:', {
          url: config.url,
          method: config.method,
          hasToken: !!token,
          hasAuthHeader: !!config.headers['Authorization']
        });
        
        if (token && !config.headers['Authorization']) {
          config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
      },
      (error) => {
        console.error('Request error:', error);
        return Promise.reject(error);
      }
    );

    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        console.error('API Error:', {
          url: error.config?.url,
          method: error.config?.method,
          status: error.response?.status,
          message: error.message,
          hasToken: !!localStorage.getItem('token')
        });
        
        if (error.response?.status === 401) {
          console.warn('401 Unauthorized - clearing token and redirecting to login');
          localStorage.removeItem('token');
          this.setAuthToken(null);
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
  }

  private parseFilename(contentDisposition?: string): string | null {
    if (!contentDisposition) {
      return null;
    }

    const utfMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch && utfMatch[1]) {
      try {
        return decodeURIComponent(utfMatch[1]);
      } catch (error) {
        console.warn('Failed to decode UTF-8 filename', error);
        return utfMatch[1];
      }
    }

    const simpleMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
    if (simpleMatch && simpleMatch[1]) {
      return simpleMatch[1];
    }

    return null;
  }

  setAuthToken(token: string | null) {
    console.log('Setting auth token:', token ? 'present' : 'null');
    if (token) {
      this.api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete this.api.defaults.headers.common['Authorization'];
    }
  }

  // Auth endpoints
  async login(credentials: LoginCredentials): Promise<AxiosResponse<AuthResponse>> {
    const formData = new FormData();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);
    
    return this.api.post('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
  }

  async register(data: RegisterData): Promise<AxiosResponse<any>> {
    return this.api.post('/auth/register', data);
  }

  async getCurrentUser(): Promise<AxiosResponse<User>> {
    return this.api.get('/auth/me');
  }

  // User management endpoints
  async getUsers(): Promise<AxiosResponse<User[]>> {
    return this.api.get('/users/');
  }

  async createUser(userData: RegisterData): Promise<AxiosResponse<User>> {
    return this.api.post('/users/', userData);
  }

  async updateUser(userId: number, userData: Partial<User>): Promise<AxiosResponse<User>> {
    return this.api.put(`/users/${userId}`, userData);
  }

  async deleteUser(userId: number): Promise<AxiosResponse<any>> {
    return this.api.delete(`/users/${userId}`);
  }

  // Email verification endpoints
  async uploadExcelFile(file: File): Promise<AxiosResponse<ExcelUploadResponse>> {
    const formData = new FormData();
    formData.append('file', file);
    
    return this.api.post('/email/upload-excel', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  }

  async verifyEmails(dataId: number, payload?: any): Promise<AxiosResponse<VerificationResult[] | PipelineResponse>> {
    if (payload) {
      // If payload is provided, send it in the request body
      return this.api.post(`/email/verify/${dataId}`, payload);
    }
    // Default behavior with query params
    return this.api.post(`/email/verify/${dataId}`, null, {
      params: { enable_smtp: true, max_workers: 8 }
    });
  }

  async verifySingleEmail(email: string, enableSmtp: boolean = true): Promise<AxiosResponse<VerificationResult>> {
    return this.api.post('/email/verify-single', { email, enable_smtp: enableSmtp });
  }

  async scrapeEmails(domain: string, maxWorkers: number = 16): Promise<AxiosResponse<any>> {
    return this.api.post('/email/scrape', { domain, max_workers: maxWorkers, verify_emails: true });
  }

  async scrapeMultipleDomains(domains: string[], maxWorkers: number = 16): Promise<AxiosResponse<any>> {
    return this.api.post('/email/scrape-multiple', { domains, max_workers: maxWorkers, verify_emails: true });
  }

  // Blog checking endpoints  
  async checkSingleBlog(url: string): Promise<AxiosResponse<any>> {
    return this.api.post('/blog/check-single', { url });
  }

  async checkMultipleBlogs(urls: string[], maxWorkers: number = 8): Promise<AxiosResponse<any>> {
    return this.api.post('/blog/check', { urls, max_workers: maxWorkers });
  }

  async checkAndUpdateBlogStatus(dataId: number, payload?: any): Promise<AxiosResponse<BlogCheckResponse>> {
    if (payload) {
      // If payload is provided, send it in the request body
      return this.api.post(`/blog/check-upload/${dataId}`, payload);
    }
    // Default behavior
    return this.api.post(`/blog/check-upload/${dataId}`);
  }

  // Pipeline endpoints
  async startPipeline(dataId: number, steps: string[]): Promise<AxiosResponse<any>> {
    return this.api.post('/pipeline/start', { data_id: dataId, steps });
  }

  async getPipelineStatus(processId: string): Promise<AxiosResponse<any>> {
    return this.api.get(`/pipeline/status/${processId}`);
  }

  async getActiveProcesses(): Promise<AxiosResponse<any[]>> {
    return this.api.get('/pipeline/processes');
  }

  async stopProcess(processId: string): Promise<AxiosResponse<any>> {
    return this.api.post(`/pipeline/stop/${processId}`);
  }

  async uploadAndProcess(file: File, processingSteps?: string[]): Promise<AxiosResponse<any>> {
    const formData = new FormData();
    formData.append('file', file);
    if (processingSteps && processingSteps.length > 0) {
      formData.append('processing_steps', JSON.stringify(processingSteps));
    }
    
    return this.api.post('/upload-and-process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  }

  // Generic HTTP methods for new endpoints
  async get<T = any>(url: string): Promise<AxiosResponse<T>> {
    return this.api.get(url);
  }

  async post<T = any>(url: string, data?: any, config?: any): Promise<AxiosResponse<T>> {
    return this.api.post(url, data, config);
  }

  async put<T = any>(url: string, data?: any): Promise<AxiosResponse<T>> {
    return this.api.put(url, data);
  }

  async delete<T = any>(url: string): Promise<AxiosResponse<T>> {
    return this.api.delete(url);
  }

  async getEmailData(
    dataId: number,
    options?: { status?: string; search?: string; sortBy?: string; sortOrder?: 'asc' | 'desc' }
  ): Promise<AxiosResponse<EmailData[]>> {
    const params: Record<string, string> = {};

    if (options?.status && options.status !== 'all') {
      params.status = options.status;
    }
    if (options?.search) {
      params.search = options.search;
    }
    if (options?.sortBy) {
      params.sort_by = options.sortBy;
    }
    if (options?.sortOrder) {
      params.sort_order = options.sortOrder;
    }

    return this.api.get(`/email/data/${dataId}`, { params });
  }

  async downloadExcel(dataId: number): Promise<{ blob: Blob; filename: string | null }> {
    const response = await this.api.get(`/email/download-excel/${dataId}`, {
      responseType: 'blob',
    });
    const filename = this.parseFilename(response.headers['content-disposition']);
    return { blob: response.data, filename };
  }

  async downloadDashboard(category: 'entries' | 'emails' | 'verified' | 'invalid'): Promise<{ blob: Blob; filename: string | null }> {
    const response = await this.api.get('/dashboard/download', {
      params: { category },
      responseType: 'blob',
    });
    const filename = this.parseFilename(response.headers['content-disposition']);
    return { blob: response.data, filename };
  }

  async getDataHistory(): Promise<AxiosResponse<any[]>> {
    return this.api.get('/email/history');
  }

  async getDashboardSummary(): Promise<AxiosResponse<DashboardSummary>> {
    return this.api.get('/dashboard/summary');
  }

  async deleteUpload(uploadId: number): Promise<AxiosResponse<any>> {
    return this.api.delete(`/email/uploads/${uploadId}`);
  }
}

const apiService = new ApiService();
export default apiService;