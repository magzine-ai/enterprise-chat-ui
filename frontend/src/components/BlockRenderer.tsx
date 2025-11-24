/**
 * BlockRenderer Component
 * 
 * Dynamically renders different block types based on the block.type property.
 * This component acts as a router for all block types, making it easy to add new block types.
 * 
 * Supported Block Types:
 * - markdown: Renders markdown content
 * - list: Renders bulleted or numbered lists
 * - chart: Renders chart visualizations (legacy, use splunk-chart)
 * - splunk-chart: Renders Splunk-style charts (line, bar, area, pie, timechart)
 * - code: Renders code snippets with syntax highlighting
 * - query: Renders executable SQL/Splunk queries with results
 * - table: Renders data tables with sorting and pagination
 * - json-explorer: Interactive JSON data explorer with expand/collapse
 * - timeline: Displays events on a timeline visualization
 * - search-filter: Real-time search and filtering component
 * - alert: Alert/notification messages with severity levels
 * - collapsible: Expandable/collapsible content sections
 * - form-viewer: Displays structured form data (ServiceNow, tickets, etc.)
 * - file-upload-download: File upload with drag-drop and download functionality
 * - checklist: Interactive checklist with checkboxes and completion tracking
 * - diagram: Workflow, architecture, and AWS diagrams (Mermaid, SVG, etc.)
 * - async-placeholder: Shows loading state for async operations
 * - plugin-widget: Renders plugin iframe widgets
 * 
 * @example
 * ```tsx
 * // From API response:
 * {
 *   type: 'query',
 *   data: {
 *     query: 'index=web_logs | stats count by status',
 *     language: 'spl'
 *   }
 * }
 * 
 * <BlockRenderer block={block} />
 * ```
 */
import React from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { Block } from '@/types';
import ChartBlock from './ChartBlock';
import AsyncPlaceholder from './AsyncPlaceholder';
import PluginWidget from './PluginWidget';
import CodeBlock from './blocks/CodeBlock';
import QueryBlock from './blocks/QueryBlock';
import DataTable from './blocks/DataTable';
import SplunkChart from './blocks/SplunkChart';
import JsonExplorer from './blocks/JsonExplorer';
import TimelineViewer from './blocks/TimelineViewer';
import SearchFilter from './blocks/SearchFilter';
import AlertBlock from './blocks/AlertBlock';
import CollapsibleSection from './blocks/CollapsibleSection';
import FormViewer from './blocks/FormViewer';
import FileUploadDownload from './blocks/FileUploadDownload';
import Checklist from './blocks/Checklist';
import DiagramViewer from './blocks/DiagramViewer';

interface BlockRendererProps {
  block: Block;
}

const BlockRenderer: React.FC<BlockRendererProps> = ({ block }) => {
  switch (block.type) {
    case 'markdown': {
      const markdownContent = block.data?.content || '';
      // Parse markdown synchronously
      let htmlContent: string;
      try {
        htmlContent = marked(markdownContent, { breaks: true, gfm: true }) as string;
      } catch (e) {
        console.error('Markdown parsing error:', e);
        htmlContent = markdownContent; // Fallback to plain text
      }
      const sanitizedHtml = DOMPurify.sanitize(htmlContent);
      return (
        <div 
          className="block-markdown"
          dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
        />
      );
    }

    case 'list':
      return (
        <ul className="block-list">
          {block.data?.items?.map((item: string, idx: number) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      );

    case 'chart':
      // Legacy chart block (for backward compatibility)
      return <ChartBlock data={block.data} />;

        case 'splunk-chart':
          return (
            <SplunkChart
              type={block.data?.type || 'line'}
              data={block.data?.data || []}
              title={block.data?.title}
              xAxis={block.data?.xAxis}
              yAxis={block.data?.yAxis}
              series={block.data?.series}
              showLegend={block.data?.showLegend !== false}
              height={block.data?.height || 300}
              allowChartTypeSwitch={block.data?.allowChartTypeSwitch || block.data?.isTimeSeries || false}
              isTimeSeries={block.data?.isTimeSeries || false}
            />
          );

    case 'code':
      return (
        <CodeBlock
          code={block.data?.code || ''}
          language={block.data?.language || 'text'}
          title={block.data?.title}
          showCopyButton={block.data?.showCopyButton !== false}
        />
      );

    case 'query':
      return (
        <QueryBlock
          query={block.data?.query || ''}
          language={block.data?.language || 'sql'}
          onExecute={block.data?.onExecute}
          title={block.data?.title}
          autoExecute={block.data?.autoExecute || false}
        />
      );

    case 'table':
      return (
        <DataTable
          columns={block.data?.columns || []}
          rows={block.data?.rows || []}
          maxRows={block.data?.maxRows}
          showRowNumbers={block.data?.showRowNumbers !== false}
          sortable={block.data?.sortable !== false}
        />
      );

    case 'json-explorer':
      return (
        <JsonExplorer
          data={block.data?.data || {}}
          title={block.data?.title}
          collapsed={block.data?.collapsed || false}
          maxDepth={block.data?.maxDepth || 3}
        />
      );

    case 'timeline':
      return (
        <TimelineViewer
          events={block.data?.events || []}
          title={block.data?.title}
          showTime={block.data?.showTime !== false}
          orientation={block.data?.orientation || 'vertical'}
        />
      );

    case 'search-filter':
      return (
        <SearchFilter
          data={block.data?.data || []}
          searchKeys={block.data?.searchKeys}
          onFiltered={block.data?.onFiltered}
          placeholder={block.data?.placeholder}
          showResultsCount={block.data?.showResultsCount !== false}
          renderResult={block.data?.renderResult}
        />
      );

    case 'alert':
      return (
        <AlertBlock
          type={block.data?.type || 'info'}
          title={block.data?.title}
          message={block.data?.message || ''}
          dismissible={block.data?.dismissible || false}
          onDismiss={block.data?.onDismiss}
        />
      );

    case 'collapsible':
      return (
        <CollapsibleSection
          title={block.data?.title || 'Section'}
          defaultExpanded={block.data?.defaultExpanded || false}
          icon={block.data?.icon}
        >
          {block.data?.children ? (
            Array.isArray(block.data.children) ? (
              <div>
                {block.data.children.map((childBlock: Block, idx: number) => (
                  <BlockRenderer key={idx} block={childBlock} />
                ))}
              </div>
            ) : (
              <div>{block.data.children}</div>
            )
          ) : (
            <div>{block.data?.content || 'No content'}</div>
          )}
        </CollapsibleSection>
      );

    case 'form-viewer':
      return (
        <FormViewer
          title={block.data?.title}
          fields={block.data?.fields || []}
          sections={block.data?.sections}
          metadata={block.data?.metadata}
          actions={block.data?.actions}
        />
      );

    case 'file-upload-download':
      return (
        <FileUploadDownload
          mode={block.data?.mode || 'both'}
          files={block.data?.files || []}
          title={block.data?.title}
          onUpload={block.data?.onUpload}
          onDownload={block.data?.onDownload}
          accept={block.data?.accept}
          maxSize={block.data?.maxSize}
          multiple={block.data?.multiple !== false}
          showFileList={block.data?.showFileList !== false}
        />
      );

    case 'checklist':
      return (
        <Checklist
          title={block.data?.title}
          items={block.data?.items || []}
          onToggle={block.data?.onToggle}
          onItemUpdate={block.data?.onItemUpdate}
          showProgress={block.data?.showProgress !== false}
          showPriority={block.data?.showPriority !== false}
          showDueDate={block.data?.showDueDate !== false}
          allowEdit={block.data?.allowEdit || false}
          collapsible={block.data?.collapsible || false}
        />
      );

    case 'diagram':
      return (
        <DiagramViewer
          type={block.data?.type || 'mermaid'}
          diagram={block.data?.diagram || ''}
          title={block.data?.title}
          description={block.data?.description}
          width={block.data?.width}
          height={block.data?.height}
          interactive={block.data?.interactive !== false}
          showControls={block.data?.showControls !== false}
          theme={block.data?.theme || 'light'}
        />
      );

    case 'async-placeholder':
      return <AsyncPlaceholder jobId={block.data?.jobId} />;

    case 'plugin-widget':
      return <PluginWidget config={block.data} />;

    default:
      return (
        <div className="block-unknown">
          Unknown block type: {block.type}
          {block.data && (
            <pre>{JSON.stringify(block.data, null, 2)}</pre>
          )}
        </div>
      );
  }
};

export default BlockRenderer;
