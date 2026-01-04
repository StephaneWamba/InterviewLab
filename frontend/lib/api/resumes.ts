/**
 * Resumes API endpoints
 */

import { apiClient } from './client';

export interface Resume {
  id: number;
  user_id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  file_type: string;
  extracted_data?: any;
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed';
  analysis_error?: string;
  created_at: string;
  updated_at: string;
}

export const resumesApi = {
  list: async (): Promise<Resume[]> => {
    return apiClient.get<Resume[]>('/api/v1/resumes');
  },

  get: async (id: number): Promise<Resume> => {
    return apiClient.get<Resume>(`/api/v1/resumes/${id}`);
  },

  upload: async (file: File, onProgress?: (progress: number) => void): Promise<{ resume_id: number; file_name: string; message: string }> => {
    return apiClient.uploadFile('/api/v1/resumes/upload', file, onProgress);
  },

  delete: async (id: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/resumes/${id}`);
  },
};







