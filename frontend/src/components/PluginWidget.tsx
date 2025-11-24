/** Plugin iframe widget with secure postMessage handshake. */
import React, { useEffect, useRef } from 'react';

interface PluginWidgetProps {
  config?: {
    url?: string;
    pluginId?: string;
  };
}

const PluginWidget: React.FC<PluginWidgetProps> = ({ config }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const originRef = useRef<string | null>(null);

  useEffect(() => {
    if (!iframeRef.current || !config?.url) return;

    const iframe = iframeRef.current;
    const handleMessage = (event: MessageEvent) => {
      // Security: Verify origin
      if (originRef.current && event.origin !== originRef.current) {
        console.warn('Rejected message from unauthorized origin:', event.origin);
        return;
      }

      if (event.data.type === 'plugin.ready') {
        originRef.current = event.origin;
        // Send handshake confirmation
        iframe.contentWindow?.postMessage(
          { type: 'plugin.handshake', status: 'confirmed' },
          event.origin
        );
      }

      // Handle other plugin messages
      console.log('Plugin message:', event.data);
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [config?.url]);

  if (!config?.url) {
    return <div>No plugin URL configured</div>;
  }

  return (
    <div className="plugin-widget">
      <iframe
        ref={iframeRef}
        src={config.url}
        sandbox="allow-scripts allow-same-origin allow-forms"
        style={{ width: '100%', height: '400px', border: '1px solid #ccc' }}
        title={`Plugin: ${config.pluginId || 'unknown'}`}
      />
    </div>
  );
};

export default PluginWidget;


