"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAgentQuery, useAgentStatus } from "@/lib/hooks/useAgent";
import type { AgentMessage } from "@/lib/api/agent";
import {
  Zap,
  Send,
  Square,
  RotateCcw,
  AlertCircle,
  Bot,
  User,
} from "lucide-react";

const EXAMPLE_PROMPTS = [
  "What are the cheapest electricity rates in my area?",
  "When is the best time to run my dishwasher today?",
  "Compare my current supplier with alternatives",
  "Send me a weekly savings report via email",
];

function MessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.role === "user";
  const isError = message.role === "error";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100">
          <Bot className="h-4 w-4 text-primary-600" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? "bg-primary-600 text-white"
            : isError
              ? "bg-danger-50 text-danger-800 border border-danger-200"
              : "bg-gray-100 text-gray-900"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.model_used && !isUser && (
          <p className="mt-2 text-xs opacity-60">
            via {message.model_used}
            {message.duration_ms
              ? ` · ${(message.duration_ms / 1000).toFixed(1)}s`
              : ""}
          </p>
        )}
        {message.tools_used && message.tools_used.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.tools_used.map((tool) => (
              <span
                key={tool}
                className="inline-flex items-center rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700"
              >
                {tool}
              </span>
            ))}
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-200">
          <User className="h-4 w-4 text-gray-600" />
        </div>
      )}
    </div>
  );
}

export function AgentChat() {
  const { messages, isStreaming, error, sendQuery, cancel, reset } =
    useAgentQuery();
  const { data: usage } = useAgentStatus();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isStreaming || trimmed.length > 2000) return;
    setInput("");
    sendQuery(trimmed);
  };

  const handleExampleClick = (prompt: string) => {
    setInput("");
    sendQuery(prompt);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const charCount = input.length;
  const isOverLimit = charCount > 2000;

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-100">
            <Zap className="h-5 w-5 text-primary-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              RateShift AI
            </h2>
            <p className="text-xs text-gray-500">Energy savings assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {usage && (
            <span className="text-xs text-gray-500">
              {usage.limit === -1
                ? `${usage.used} queries today`
                : `${usage.used}/${usage.limit} queries today`}
            </span>
          )}
          {messages.length > 0 && (
            <button
              onClick={reset}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              title="New conversation"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-50">
              <Zap className="h-8 w-8 text-primary-500" />
            </div>
            <h3 className="mt-4 text-lg font-medium text-gray-900">
              How can I help you save on electricity?
            </h3>
            <p className="mt-2 max-w-sm text-sm text-gray-500">
              Ask about rates, savings, usage optimization, or have me send
              reports and manage your alerts.
            </p>
            <div className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleExampleClick(prompt)}
                  className="rounded-lg border border-gray-200 px-4 py-3 text-left text-sm text-gray-700 transition-colors hover:border-primary-300 hover:bg-primary-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isStreaming && (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <div className="flex gap-1">
                  <span
                    className="h-2 w-2 animate-bounce rounded-full bg-primary-400"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="h-2 w-2 animate-bounce rounded-full bg-primary-400"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="h-2 w-2 animate-bounce rounded-full bg-primary-400"
                    style={{ animationDelay: "300ms" }}
                  />
                </div>
                Thinking...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mb-2 flex items-center gap-2 rounded-lg bg-danger-50 px-4 py-2 text-sm text-danger-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Usage limit CTA */}
      {usage && usage.limit !== -1 && usage.remaining === 0 && (
        <div className="mx-6 mb-2 rounded-lg bg-warning-50 px-4 py-2 text-sm text-warning-800">
          Daily query limit reached. Upgrade to Pro for 20/day or Business for
          unlimited.
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-gray-200 p-4">
        <div className="flex items-end gap-3">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask RateShift AI..."
              rows={1}
              disabled={isStreaming}
              className="w-full resize-none rounded-xl border border-gray-300 px-4 py-3 pr-16 text-sm text-gray-900 placeholder-gray-400 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:opacity-50"
            />
            <span
              className={`absolute bottom-3 right-3 text-xs ${
                isOverLimit ? "text-danger-500" : "text-gray-400"
              }`}
            >
              {charCount}/2000
            </span>
          </div>
          {isStreaming ? (
            <button
              type="button"
              onClick={cancel}
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-gray-200 text-gray-600 transition-colors hover:bg-gray-300"
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || isOverLimit}
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-600 text-white transition-colors hover:bg-primary-700 disabled:opacity-50 disabled:hover:bg-primary-600"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
