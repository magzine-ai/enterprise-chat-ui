/**
 * DataTable Component
 * 
 * Displays tabular data with sorting, filtering, and pagination capabilities.
 * Similar to Splunk's table visualization.
 * 
 * @example
 * ```tsx
 * <DataTable 
 *   columns={['name', 'value', 'timestamp']}
 *   rows={[
 *     ['Item 1', '100', '2024-01-15'],
 *     ['Item 2', '200', '2024-01-16'],
 *   ]}
 *   maxRows={100}
 * />
 * ```
 * 
 * @param columns - Array of column names
 * @param rows - Array of row data (each row is an array of cell values)
 * @param maxRows - Maximum rows to display before pagination (default: 100)
 * @param showRowNumbers - Whether to show row numbers (default: true)
 * @param sortable - Whether columns are sortable (default: true)
 */
import React, { useState, useMemo, useRef } from 'react';

interface DataTableProps {
  columns: string[];
  rows: any[][];
  maxRows?: number;
  showRowNumbers?: boolean;
  sortable?: boolean;
}

const DataTable: React.FC<DataTableProps> = ({
  columns,
  rows,
  maxRows = 100,
  showRowNumbers = true,
  sortable = true,
}) => {
  const [sortColumn, setSortColumn] = useState<number | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  const sortedRows = useMemo(() => {
    if (!sortable || sortColumn === null) return rows;
    
    return [...rows].sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];
      
      // Try to parse as numbers
      const aNum = parseFloat(aVal);
      const bNum = parseFloat(bVal);
      const isNumeric = !isNaN(aNum) && !isNaN(bNum);
      
      if (isNumeric) {
        return sortDirection === 'asc' ? aNum - bNum : bNum - aNum;
      }
      
      // String comparison
      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      if (sortDirection === 'asc') {
        return aStr < bStr ? -1 : aStr > bStr ? 1 : 0;
      } else {
        return aStr > bStr ? -1 : aStr < bStr ? 1 : 0;
      }
    });
  }, [rows, sortColumn, sortDirection, sortable]);

  const paginatedRows = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    return sortedRows.slice(0, maxRows).slice(start, end);
  }, [sortedRows, currentPage, maxRows]);

  const totalPages = Math.ceil(Math.min(sortedRows.length, maxRows) / rowsPerPage);

  const handleSort = (columnIndex: number) => {
    if (!sortable) return;
    
    if (sortColumn === columnIndex) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(columnIndex);
      setSortDirection('asc');
    }
  };

  const getSortIcon = (columnIndex: number) => {
    if (sortColumn !== columnIndex) return '⇅';
    return sortDirection === 'asc' ? '↑' : '↓';
  };

  if (rows.length === 0) {
    return <div className="data-table-empty">No data to display</div>;
  }

  const tableRef = React.useRef<HTMLDivElement>(null);

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    const tableHTML = tableRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Table View</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-table-container {
              background: white;
              padding: 20px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              height: calc(100vh - 80px);
              overflow: auto;
            }
            h2 { margin-bottom: 20px; color: #333; }
          </style>
        </head>
        <body>
          <div class="popup-table-container">
            <h2>Data Table</h2>
            ${tableHTML}
          </div>
        </body>
      </html>
    `;
    
    // Open as popup window
    const popup = window.open(
      '',
      'tablePopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no,status=no`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    } else {
      alert('Popup blocked. Opening in new tab instead.');
      handleOpenNewTab();
    }
  };

  const handleOpenNewTab = () => {
    const tableHTML = tableRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Table View</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-table-container {
              background: white;
              padding: 20px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              min-height: calc(100vh - 80px);
            }
            h2 { margin-bottom: 20px; color: #333; }
          </style>
        </head>
        <body>
          <div class="tab-table-container">
            <h2>Data Table</h2>
            ${tableHTML}
          </div>
        </body>
      </html>
    `;
    
    // Open in new tab (full browser tab)
    const newTab = window.open('', '_blank');
    if (newTab) {
      newTab.document.open();
      newTab.document.write(htmlContent);
      newTab.document.close();
    }
  };

  return (
    <div ref={tableRef} className="data-table-wrapper">
      <div className="data-table-header">
        <div className="data-table-title">Data Table</div>
        <div className="data-table-actions">
          <button className="table-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲 Popup
          </button>
          <button className="table-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑 New Tab
          </button>
        </div>
      </div>
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              {showRowNumbers && <th className="row-number-header">#</th>}
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  className={sortable ? 'sortable' : ''}
                  onClick={() => handleSort(idx)}
                >
                  {col}
                  {sortable && <span className="sort-icon">{getSortIcon(idx)}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row, rowIdx) => (
              <tr key={rowIdx}>
                {showRowNumbers && (
                  <td className="row-number">
                    {(currentPage - 1) * rowsPerPage + rowIdx + 1}
                  </td>
                )}
                {row.map((cell, cellIdx) => (
                  <td key={cellIdx}>{String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {totalPages > 1 && (
        <div className="data-table-pagination">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
          >
            ← Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
          >
            Next →
          </button>
        </div>
      )}
      
      {rows.length > maxRows && (
        <div className="data-table-info">
          Showing {Math.min(rows.length, maxRows)} of {rows.length} rows
        </div>
      )}
    </div>
  );
};

export default DataTable;

