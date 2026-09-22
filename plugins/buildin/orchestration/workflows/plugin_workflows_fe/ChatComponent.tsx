/**
 * WorkflowChatComponent — WebSocket design chat for workflow creation
 *
 * Phase 7 feature: real-time collaborative workflow design with Claude
 * - Connects to /workflows/{wid}/chat WebSocket endpoint
 * - Displays chat history
 * - Suggests workflow templates based on keywords
 * - Streams Claude responses
 * - Persists chat locally
 */

import React, { useState, useEffect, useRef } from 'react';
import { Send, Loader2, AlertCircle, Sparkles } from 'lucide-react';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  template_suggestion?: {
    name: string;
    steps: string;
    description: string;
  };
  timestamp: number;
}

export interface ChatComponentProps {
  workflowId: string;
  onTemplateSuggest?: (templateName: string) => void;
}

export const WorkflowChatComponent: React.FC<ChatComponentProps> = ({
  workflowId,
  onTemplateSuggest,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Connect to WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/v1/console/workflows/${workflowId}/chat`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'history') {
          // Initial history load
          setMessages(data.messages || []);
        } else if (data.type === 'message') {
          // Assistant response
          const assistantMsg: ChatMessage = {
            id: `msg-${Date.now()}`,
            role: 'assistant',
            content: data.content || '',
            template_suggestion: data.template_suggestion,
            timestamp: Date.now(),
          };

          setMessages((prev) => [...prev, assistantMsg]);

          // Notify parent of template suggestion
          if (data.template_suggestion && onTemplateSuggest) {
            onTemplateSuggest(data.template_suggestion.name);
          }

          setIsLoading(false);
        } else if (data.type === 'error') {
          setError(data.message || 'Chat error');
          setIsLoading(false);
        }
      } catch (e) {
        // Ignore parse errors (may be streaming text)
      }
    };

    ws.onerror = (event) => {
      setError('WebSocket connection failed');
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [workflowId, onTemplateSuggest]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || !isConnected || isLoading) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);

    // Send via WebSocket
    setIsLoading(true);
    wsRef.current?.send(JSON.stringify({
      content: input,
      role: 'user',
    }));

    setInput('');
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen max-h-[600px] bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <Sparkles className="w-5 h-5 text-blue-600" />
          <div>
            <h3 className="font-semibold text-gray-900">Workflow Designer</h3>
            <p className="text-xs text-gray-600">Chat with Claude to design your workflow</p>
          </div>
        </div>
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Sparkles className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-600">Start by describing your workflow.</p>
            <p className="text-sm text-gray-500 mt-2">
              For example: &quot;I need to send daily digest emails of top news stories&quot;
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-4 h-4 text-blue-600" />
              </div>
            )}

            <div
              className={`max-w-xs px-4 py-3 rounded-lg ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-none'
                  : msg.role === 'system'
                  ? 'bg-gray-100 text-gray-900 text-sm'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>

              {msg.template_suggestion && (
                <div className="mt-3 pt-3 border-t border-gray-300">
                  <p className="font-semibold text-xs mb-2">Template suggested: {msg.template_suggestion.name}</p>
                  <p className="text-xs opacity-90">{msg.template_suggestion.steps}</p>
                </div>
              )}
            </div>

            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                <span className="text-xs font-medium text-gray-700">You</span>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
              <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
            </div>
            <div className="bg-gray-100 px-4 py-3 rounded-lg">
              <p className="text-sm text-gray-600">Claude is thinking<span className="animate-bounce">…</span></p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-4 h-4 text-red-600" />
            </div>
            <div className="bg-red-50 px-4 py-3 rounded-lg">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-100 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Describe what your workflow should do..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 text-sm"
            disabled={!isConnected || isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!isConnected || isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title={isConnected ? 'Send message' : 'Connecting...'}
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        {!isConnected && (
          <p className="text-xs text-gray-500 mt-2">Connecting to chat...</p>
        )}
      </div>
    </div>
  );
};

export default WorkflowChatComponent;
