/**
 * CodeBlock Component
 * 
 * Displays code snippets with syntax highlighting and copy functionality.
 * Supports multiple languages including SQL, SPL (Splunk), Python, JavaScript, etc.
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
import React, { useState } from 'react';

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

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
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
          <code>{code}</code>
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


