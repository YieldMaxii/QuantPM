import { useEffect, useState } from 'react';
import { VoxelWorld } from './components/VoxelWorld';
import { HUD } from './components/HUD';
import { MarketDetailDrawer } from './components/MarketDetailDrawer';
import { fetchMarkets, fetchPerformance, fetchStatus, fetchTrades, resetSystem } from './api';
import type { Market, Performance, SystemStatus, Trade } from './models';

function App() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [status, setStatus] = useState<SystemStatus>({ is_running: false, elapsed: 0 });
  const [performance, setPerformance] = useState<Performance[]>([]);
  
  // Selection state
  const [selectedMarket, setSelectedMarket] = useState<Market | null>(null);
  const [marketHistory, setMarketHistory] = useState<{ timestamp: string; price: number }[]>([]);

  const refreshData = async () => {
    try {
      const [m, t, s, p] = await Promise.all([
        fetchMarkets(),
        fetchTrades(),
        fetchStatus(),
        fetchPerformance()
      ]);
      setMarkets(m);
      setTrades(t);
      setStatus(s);
      setPerformance(p);
    } catch (e) {
      console.error("Failed to fetch data", e);
    }
  };

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 2000); // Poll every 2s
    return () => clearInterval(interval);
  }, []);

  // Mock history fetcher (replace with real API later)
  useEffect(() => {
    if (selectedMarket) {
      // In a real app, fetch history from API
      // For now, generate mock history based on current outcome
      const mockHistory = Array.from({ length: 20 }, (_, i) => ({
        timestamp: new Date(Date.now() - (20 - i) * 60000).toISOString(),
        price: Math.max(0, Math.min(1, selectedMarket.outcome + (Math.random() - 0.5) * 0.1))
      }));
      setMarketHistory(mockHistory);
    }
  }, [selectedMarket]);

  const handleReset = async () => {
    if (confirm("Are you sure you want to reset the system? This will delete all data.")) {
      await resetSystem();
      await refreshData();
    }
  };

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#111', position: 'relative', overflow: 'hidden' }}>
      <VoxelWorld 
        markets={markets} 
        trades={trades}
        onMarketClick={setSelectedMarket}
      />
      
      <HUD 
        status={status} 
        performance={performance} 
        recentTrades={trades} 
        onReset={handleReset} 
      />

      <MarketDetailDrawer 
        market={selectedMarket} 
        onClose={() => setSelectedMarket(null)}
        history={marketHistory}
      />
    </div>
  );
}

export default App;
