"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DownloadCloud, Settings, Link as LinkIcon, CheckCircle, XCircle, Loader2, Play } from "lucide-react";

type DownloadStatus = "pending" | "fetching" | "downloading" | "completed" | "error";

interface DownloadItem {
  id: string;
  originalUrl: string;
  status: DownloadStatus;
  progress: number;
  filename?: string;
  error?: string;
}

export default function Home() {
  const [inputText, setInputText] = useState("");
  const [downloads, setDownloads] = useState<DownloadItem[]>([]);
  const [isExtracting, setIsExtracting] = useState(false);

  const teraboxDomains = [
    "terabox.com",
    "teraboxapp.com",
    "1024tera.com",
    "nephobox.com",
    "4funbox.com",
    "mirrobox.com",
    "momerybox.com",
    "teraboxlink.com",
    "terafileshare.com"
  ];

  const handleExtractAndStart = () => {
    if (!inputText.trim()) return;
    
    setIsExtracting(true);
    
    // Complex regex to find URLs matching terabox domains
    const domainRegexPart = teraboxDomains.map(d => d.replace('.', '\\.')).join('|');
    const urlRegex = new RegExp(`https?:\\/\\/(www\\.)?(${domainRegexPart})[^\\s]+`, 'g');
    
    const matches = inputText.match(urlRegex) || [];
    
    const uniqueLinks = Array.from(new Set(matches));
    
    const newItems: DownloadItem[] = uniqueLinks.map((url, idx) => ({
      id: `${Date.now()}-${idx}`,
      originalUrl: url,
      status: "pending",
      progress: 0
    }));

    setDownloads(prev => [...prev, ...newItems]);
    setInputText("");
    setIsExtracting(false);

    // Start downloading new items immediately
    newItems.forEach(item => {
      processDownload(item);
    });
  };

  const processDownload = async (item: DownloadItem) => {
    updateItem(item.id, { status: "fetching", progress: 10 });
    
    try {
      const response = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: item.originalUrl })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to fetch download link");
      }

      if (data.directUrl) {
        updateItem(item.id, { status: "downloading", progress: 50, filename: data.filename || "video.mp4" });
        
        // Trigger native browser download by routing through our own proxy
        // This prevents the browser from blocking Cross-Origin downloads and forces a "Save As"
        const cookiesParam = data.cookies ? `&cookies=${encodeURIComponent(data.cookies)}` : '';
        const a = document.createElement("a");
        a.href = `/api/stream?url=${encodeURIComponent(data.directUrl)}${cookiesParam}`;
        a.download = data.filename || "video.mp4";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        updateItem(item.id, { status: "completed", progress: 100 });
      } else {
        throw new Error("No direct URL returned");
      }

    } catch (err: any) {
      updateItem(item.id, { status: "error", error: err.message });
    }
  };

  const updateItem = (id: string, updates: Partial<DownloadItem>) => {
    setDownloads(prev => prev.map(d => d.id === id ? { ...d, ...updates } : d));
  };

  return (
    <main className="flex-1 w-full max-w-5xl mx-auto px-6 py-12 md:py-24 flex flex-col items-center">
      
      {/* Header */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full flex justify-between items-center mb-16"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-xl border border-blue-500/20">
            <DownloadCloud className="w-6 h-6 text-blue-500" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">TeraFetch <span className="text-blue-500">Pro</span></h1>
        </div>
        
        <button className="p-2 rounded-full hover:bg-white/5 transition-colors text-zinc-400 hover:text-white">
          <Settings className="w-5 h-5" />
        </button>
      </motion.div>

      {/* Hero Input Area */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="w-full glass rounded-3xl p-6 md:p-8 shadow-2xl relative overflow-hidden"
      >
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-purple-500 to-blue-500"></div>
        
        <div className="mb-6">
          <h2 className="text-3xl font-semibold mb-2 text-white">Paste Links or Text</h2>
          <p className="text-zinc-400 text-sm">Paste a large block of text containing multiple Terabox links. We'll extract them and download the videos automatically.</p>
        </div>

        <div className="relative">
          <textarea 
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="e.g. Hey, check out these videos! https://terabox.com/s/1xyz... Also this one https://1024tera.com/s/2abc..."
            className="w-full h-48 bg-black/40 border border-white/10 rounded-2xl p-4 text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 resize-none font-mono text-sm"
          ></textarea>
        </div>

        <div className="mt-6 flex justify-end">
          <button 
            onClick={handleExtractAndStart}
            disabled={!inputText.trim() || isExtracting}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-xl font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)]"
          >
            {isExtracting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
            Extract & Download All
          </button>
        </div>
      </motion.div>

      {/* Queue Area */}
      {downloads.length > 0 && (
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full mt-12"
        >
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-semibold text-white flex items-center gap-2">
              Download Queue
              <span className="text-xs font-mono bg-blue-500/20 text-blue-400 px-2 py-1 rounded-full">{downloads.length}</span>
            </h3>
          </div>

          <div className="flex flex-col gap-3">
            <AnimatePresence>
              {downloads.map((item) => (
                <motion.div 
                  key={item.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className="glass rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="flex items-start gap-4 overflow-hidden">
                    <div className="mt-1">
                      {item.status === 'completed' && <CheckCircle className="w-5 h-5 text-emerald-500" />}
                      {item.status === 'error' && <XCircle className="w-5 h-5 text-red-500" />}
                      {item.status === 'pending' && <LinkIcon className="w-5 h-5 text-zinc-500" />}
                      {(item.status === 'fetching' || item.status === 'downloading') && <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate w-full">
                        {item.filename || item.originalUrl}
                      </p>
                      <p className="text-xs text-zinc-500 truncate mt-1">
                        {item.error || (item.status === 'fetching' ? 'Extracting URL...' : item.status === 'downloading' ? 'Native download triggered...' : item.status)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 w-full md:w-auto md:min-w-[200px]">
                    <div className="flex-1 md:flex-none w-full bg-black/50 rounded-full h-1.5 overflow-hidden">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${item.progress}%` }}
                        className={`h-full rounded-full ${item.status === 'error' ? 'bg-red-500' : item.status === 'completed' ? 'bg-emerald-500' : 'bg-blue-500'}`}
                      />
                    </div>
                    <span className="text-xs font-mono text-zinc-400 w-8 text-right">{item.progress}%</span>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </main>
  );
}
