import React, { useState, useEffect } from 'react';
import { TrendingUp, Activity, Scale, Globe, Sun, Zap, Wind, Trophy, AlertCircle, Clock, Play, RefreshCw } from 'lucide-react';
import axios from 'axios';

// --- Types ---

interface Strategy {
  id: string;
  name: string;
  pnl: number;
  trades: number;
  icon?: any;
  rank?: number;
}

interface DashboardState {
  strategies: Strategy[];
  competition_time: string | null;
  is_active: boolean;
}

// --- Icons Mapping ---
const STRATEGY_ICONS: Record<string, any> = {
  "Trend Fast": TrendingUp,
  "Trend Slow": Activity,
  "Mean Reversion": Scale,
  "Range Reversion": Globe,
  "Cross Section": Zap,
};

// --- Data & Logic ---

const useLiveMarketData = () => {
  const [data, setData] = useState<Strategy[]>([]);
  const [isActive, setIsActive] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState<string>("--:--:--");
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const response = await axios.get('http://localhost:8002/stats');
      const state: DashboardState = response.data;
      
      setIsActive(state.is_active);
      
      // Map strategies to include icons and calculate rank
      const mappedStrategies = state.strategies.map((s, index) => ({
        ...s,
        icon: STRATEGY_ICONS[s.name] || Sun,
        rank: index + 1
      }));
      
      setData(mappedStrategies);
      setError(null);

      // Calculate time remaining
      if (state.competition_time) {
          const start = new Date(state.competition_time).getTime();
          const now = new Date().getTime();
          const elapsed = now - start;
          const totalDuration = 24 * 60 * 60 * 1000; // 24 hours
          const remaining = Math.max(0, totalDuration - elapsed);
          
          const hours = Math.floor(remaining / (1000 * 60 * 60));
          const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
          const seconds = Math.floor((remaining % (1000 * 60)) / 1000);
          
          setTimeRemaining(`${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);
      } else {
        setTimeRemaining("--:--:--");
      }

    } catch (err) {
      console.error("Failed to fetch stats:", err);
      setError("Connection lost. Retrying...");
    }
  };

  useEffect(() => {
    fetchData(); // Initial fetch
    const interval = setInterval(fetchData, 1000); // Poll every 1s
    return () => clearInterval(interval);
  }, []);

  return { strategies: data, isActive, timeRemaining, error, refresh: fetchData };
};

// --- Components ---

const KeyRow = ({ rank, strategy, icon: Icon, isHeader = false }: { rank?: number, strategy?: Strategy, icon?: any, isHeader?: boolean }) => {
  const isTop3 = rank && rank <= 3 && !isHeader;
  
  const formatPNL = (val: number) => {
    const sign = val >= 0 ? '+' : '-';
    return `${sign}$${Math.abs(Math.floor(val)).toLocaleString()}`;
  };

  if (isHeader) {
    return (
      <div className="flex items-center px-8 pb-4 text-gray-400 font-bold text-xs uppercase tracking-[0.2em]">
        <div className="w-16 text-center">Rank</div>
        <div className="flex-1 pl-4">Strategy</div>
        <div className="w-32 text-right">PNL</div>
      </div>
    );
  }

  if (!strategy) return null;

  return (
    <div className="relative mb-4 group">
      {/* THE 3D KEY STRUCTURE */}
      <div className="
        relative z-20
        flex items-center px-6 h-16
        rounded-xl
        bg-gradient-to-b from-white to-gray-50
        border border-white
        shadow-[0_6px_0_#cbd5e1,0_12px_15px_-5px_rgba(0,0,0,0.1)]
        transition-all duration-100 ease-out
        group-hover:translate-y-[3px]
        group-hover:shadow-[0_3px_0_#cbd5e1,0_6px_8px_-5px_rgba(0,0,0,0.1)]
      ">
        
        {/* Rank */}
        <div className={`w-16 text-center font-bold text-xl ${isTop3 ? 'text-blue-500' : 'text-gray-400'}`}>
          {rank}
        </div>

        {/* Strategy */}
        <div className="flex-1 flex items-center gap-4 pl-4">
          <div className={`
            p-2 rounded-lg shadow-inner
            ${isTop3 ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-500'}
          `}>
            {Icon && <Icon size={20} strokeWidth={2.5} />}
          </div>
          <span className="font-bold text-gray-700 text-lg">
            {strategy.name}
          </span>
        </div>

        {/* PNL */}
        <div className="w-32 text-right">
           <div className={`font-bold text-lg font-mono tracking-tight ${strategy.pnl >= 0 ? 'text-green-600' : 'text-red-500'}`}>
            {formatPNL(strategy.pnl)}
          </div>
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
            {strategy.trades} Trades
          </div>
        </div>

        {/* Glossy Highlight on top of key */}
        <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-white/80 to-transparent opacity-50 pointer-events-none" />
      </div>
    </div>
  );
};

const App = () => {
  const { strategies, isActive, timeRemaining, error, refresh } = useLiveMarketData();
  const [isProcessing, setIsProcessing] = useState(false);

  const handleStartCompetition = async () => {
    setIsProcessing(true);
    try {
      await axios.post('http://localhost:8002/start');
      refresh();
    } catch (err) {
      console.error("Failed to start competition:", err);
      alert("Failed to start competition. Check console for details.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleResetCompetition = async () => {
    if (!confirm("Are you sure you want to reset the competition? This will clear all trade history.")) {
        return;
    }
    setIsProcessing(true);
    try {
      await axios.post('http://localhost:8002/reset');
      refresh();
    } catch (err) {
      console.error("Failed to reset competition:", err);
      alert("Failed to reset competition. Check console for details.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#ced4da] flex items-center justify-center overflow-hidden font-sans">
      
      <div className="w-full max-w-2xl p-6">
        
        {/* Timer / Status Banner */}
        <div className="mb-6 flex justify-between items-center">
            <div className="bg-white/50 backdrop-blur-sm px-4 py-2 rounded-full shadow-sm border border-white/50 flex items-center gap-2">
                <Clock size={16} className="text-gray-600" />
                <span className="font-mono font-bold text-gray-700">{timeRemaining}</span>
            </div>
            
            {error && (
                <div className="bg-red-100 px-4 py-2 rounded-full text-red-600 text-sm font-bold flex items-center gap-2 border border-red-200">
                    <AlertCircle size={16} />
                    {error}
                </div>
            )}
            
            {!error && (
                <div className="flex gap-2">
                    {!isActive ? (
                        <button 
                        onClick={handleStartCompetition}
                        disabled={isProcessing}
                        className="
                            bg-green-500 hover:bg-green-600 active:translate-y-1 
                            text-white px-6 py-2 rounded-full 
                            font-bold shadow-[0_4px_0_#15803d] hover:shadow-[0_2px_0_#15803d]
                            transition-all duration-100
                            flex items-center gap-2
                            disabled:opacity-70 disabled:cursor-not-allowed
                        "
                        >
                        {isProcessing ? "Starting..." : (
                            <>
                            <Play size={16} fill="currentColor" />
                            Start Competition
                            </>
                        )}
                        </button>
                    ) : (
                        <button 
                        onClick={handleResetCompetition}
                        disabled={isProcessing}
                        className="
                            bg-gray-500 hover:bg-gray-600 active:translate-y-1 
                            text-white px-4 py-2 rounded-full 
                            font-bold shadow-[0_4px_0_#4b5563] hover:shadow-[0_2px_0_#4b5563]
                            transition-all duration-100
                            flex items-center gap-2
                            text-sm
                            disabled:opacity-70 disabled:cursor-not-allowed
                        "
                        >
                        {isProcessing ? "Resetting..." : (
                            <>
                            <RefreshCw size={14} />
                            Reset
                            </>
                        )}
                        </button>
                    )}
                </div>
            )}
        </div>

        {/* The 'Base' Chassis */}
        <div 
          className="
            relative
            bg-[#e9ecef]
            rounded-[30px]
            p-8
            shadow-[
              inset_0_1px_0_rgba(255,255,255,0.8),
              0_20px_40px_-10px_rgba(0,0,0,0.2),
              0_0_0_1px_rgba(0,0,0,0.05)
            ]
            border-b-8 border-[#d1d5db]
          "
        >
          {/* Industrial details / bolts */}
          <div className="absolute top-4 left-4 w-3 h-3 rounded-full bg-gray-300 shadow-[inset_0_1px_3px_rgba(0,0,0,0.2)]" />
          <div className="absolute top-4 right-4 w-3 h-3 rounded-full bg-gray-300 shadow-[inset_0_1px_3px_rgba(0,0,0,0.2)]" />
          <div className="absolute bottom-4 left-4 w-3 h-3 rounded-full bg-gray-300 shadow-[inset_0_1px_3px_rgba(0,0,0,0.2)]" />
          <div className="absolute bottom-4 right-4 w-3 h-3 rounded-full bg-gray-300 shadow-[inset_0_1px_3px_rgba(0,0,0,0.2)]" />

          {/* Header */}
          <KeyRow isHeader />

          {/* Keys Container */}
          <div className="flex flex-col gap-1">
            {strategies.length > 0 ? (
                strategies.map((strategy, index) => (
                <KeyRow 
                    key={strategy.id} 
                    rank={index + 1} 
                    strategy={strategy} 
                    icon={strategy.icon || Trophy} 
                />
                ))
            ) : (
                <div className="text-center py-10 text-gray-400 font-bold">
                    {isActive ? "Loading Strategy Data..." : "Ready to Start"}
                </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        body {
          background-color: #ced4da;
          background-image: 
            linear-gradient(rgba(255,255,255,0.3) 2px, transparent 2px),
            linear-gradient(90deg, rgba(255,255,255,0.3) 2px, transparent 2px);
          background-size: 40px 40px;
        }
      `}</style>
    </div>
  );
};

export default App;
