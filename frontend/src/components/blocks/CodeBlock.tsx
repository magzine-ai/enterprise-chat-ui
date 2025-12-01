/**
 * CodeBlock Component
 * 
 * Displays code snippets with syntax highlighting and copy functionality.
 * Supports multiple languages including SQL, SPL (Splunk), Python, JavaScript, etc.
 * Automatically formats Splunk queries for better readability.
 * 
 * @example
 * ```tsx
 * <CodeBlock 
 *   code="SELECT * FROM users WHERE active = true"
 *   language="sql"
 *   title="User Query"
 * />
 * ```
 * 
 * @param code - The code string to display
 * @param language - Programming language for syntax highlighting (sql, spl, python, javascript, etc.)
 * @param title - Optional title for the code block
 * @param showCopyButton - Whether to show copy button (default: true)
 */
import React, { useState, useMemo } from 'react';
import { formatSplunkQuery } from '@/utils/splunkFormatter';

interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  showCopyButton?: boolean;
}

const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = 'text',
  title,
  showCopyButton = true,
}) => {
  const [copied, setCopied] = useState(false);

  // Format Splunk queries automatically
  const formattedCode = useMemo(() => {
    if (language === 'spl' || language === 'splunk') {
      return formatSplunkQuery(code);
    }
    return code;
  }, [code, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code); // Copy original, not formatted
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  return (
    <div className="code-block-wrapper">
      {title && <div className="code-block-title">{title}</div>}
      <div className="code-block-container">
        <pre className={`code-block language-${language}`}>
          <code>{formattedCode}</code>
        </pre>
        {showCopyButton && (
          <button className="code-copy-button" onClick={handleCopy} title="Copy code">
            {copied ? '✓ Copied' : '📋 Copy'}
          </button>
        )}
      </div>
    </div>
  );
};

export default CodeBlock;


