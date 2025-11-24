/**
 * FileUploadDownload Component
 * 
 * Provides file upload (with drag-and-drop) and download functionality.
 * Useful for sharing logs, configs, exports, and other files in conversations.
 * 
 * @example
 * ```tsx
 * <FileUploadDownload
 *   mode="upload" // or "download" or "both"
 *   files={[
 *     { name: 'config.json', size: 1024, url: '/files/config.json' },
 *     { name: 'logs.txt', size: 2048, url: '/files/logs.txt' }
 *   ]}
 *   onUpload={(files) => console.log('Uploaded:', files)}
 *   accept=".json,.txt,.log"
 *   maxSize={10485760} // 10MB
 * />
 * ```
 */
import React, { useState, useRef, DragEvent } from 'react';

export interface FileItem {
  name: string;
  size: number;
  url?: string;
  type?: string;
  uploadedAt?: string;
  description?: string;
}

interface FileUploadDownloadProps {
  mode?: 'upload' | 'download' | 'both';
  files?: FileItem[];
  title?: string;
  onUpload?: (files: File[]) => void;
  onDownload?: (file: FileItem) => void;
  accept?: string;
  maxSize?: number; // in bytes
  multiple?: boolean;
  showFileList?: boolean;
}

const FileUploadDownload: React.FC<FileUploadDownloadProps> = ({
  mode = 'both',
  files = [],
  title,
  onUpload,
  onDownload,
  accept,
  maxSize = 10485760, // 10MB default
  multiple = true,
  showFileList = true,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<FileItem[]>(files);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString?: string): string => {
    if (!dateString) return '';
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (mode === 'download') return;

    const droppedFiles = Array.from(e.dataTransfer.files);
    processFiles(droppedFiles);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      processFiles(selectedFiles);
    }
  };

  const processFiles = (fileList: File[]) => {
    const validFiles: File[] = [];
    const errors: string[] = [];

    fileList.forEach((file) => {
      // Check file size
      if (file.size > maxSize) {
        errors.push(`${file.name} exceeds maximum size of ${formatFileSize(maxSize)}`);
        return;
      }

      // Check file type if accept is specified
      if (accept) {
        const acceptedTypes = accept.split(',').map((t) => t.trim());
        const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase();
        const fileType = file.type;

        const isAccepted = acceptedTypes.some((type) => {
          if (type.startsWith('.')) {
            return fileExtension === type;
          }
          return fileType.match(type.replace('*', '.*'));
        });

        if (!isAccepted) {
          errors.push(`${file.name} is not an accepted file type`);
          return;
        }
      }

      validFiles.push(file);
    });

    if (errors.length > 0) {
      alert(errors.join('\n'));
    }

    if (validFiles.length > 0 && onUpload) {
      // Simulate upload progress
      validFiles.forEach((file) => {
        let progress = 0;
        const interval = setInterval(() => {
          progress += 10;
          setUploadProgress((prev) => ({ ...prev, [file.name]: progress }));
          if (progress >= 100) {
            clearInterval(interval);
            setUploadProgress((prev) => {
              const newProgress = { ...prev };
              delete newProgress[file.name];
              return newProgress;
            });
          }
        }, 100);
      });

      onUpload(validFiles);

      // Add to uploaded files list
      const newFiles: FileItem[] = validFiles.map((file) => ({
        name: file.name,
        size: file.size,
        type: file.type,
        uploadedAt: new Date().toISOString(),
      }));
      setUploadedFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleDownload = (file: FileItem) => {
    if (onDownload) {
      onDownload(file);
    } else if (file.url) {
      // Default download behavior
      const link = document.createElement('a');
      link.href = file.url;
      link.download = file.name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  const displayFiles = uploadedFiles.length > 0 ? uploadedFiles : files;

  return (
    <div className="file-upload-download-wrapper">
      {title && <h3 className="file-upload-download-title">{title}</h3>}

      {(mode === 'upload' || mode === 'both') && (
        <div
          className={`file-upload-zone ${isDragging ? 'dragging' : ''}`}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleBrowseClick}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={accept}
            multiple={multiple}
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          <div className="file-upload-content">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p className="file-upload-text">
              {isDragging ? 'Drop files here' : 'Drag and drop files here, or click to browse'}
            </p>
            {accept && (
              <p className="file-upload-hint">Accepted: {accept}</p>
            )}
            {maxSize && (
              <p className="file-upload-hint">Max size: {formatFileSize(maxSize)}</p>
            )}
          </div>
        </div>
      )}

      {showFileList && displayFiles.length > 0 && (
        <div className="file-list">
          <h4 className="file-list-title">Files</h4>
          {displayFiles.map((file, index) => (
            <div key={index} className="file-item">
              <div className="file-item-info">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="file-icon"
                >
                  <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                  <polyline points="13 2 13 9 20 9" />
                </svg>
                <div className="file-item-details">
                  <span className="file-name">{file.name}</span>
                  <span className="file-meta">
                    {formatFileSize(file.size)}
                    {file.uploadedAt && ` • ${formatDate(file.uploadedAt)}`}
                  </span>
                  {file.description && (
                    <span className="file-description">{file.description}</span>
                  )}
                </div>
              </div>
              <div className="file-item-actions">
                {uploadProgress[file.name] !== undefined && (
                  <div className="file-upload-progress">
                    <div
                      className="file-upload-progress-bar"
                      style={{ width: `${uploadProgress[file.name]}%` }}
                    />
                    <span>{uploadProgress[file.name]}%</span>
                  </div>
                )}
                {(mode === 'download' || mode === 'both') && (
                  <button
                    className="file-download-button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDownload(file);
                    }}
                    title="Download"
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default FileUploadDownload;

