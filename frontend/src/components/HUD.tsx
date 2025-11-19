import type { SystemStatus, Performance, Trade } from '../models';

interface HUDProps {
    status: SystemStatus;
    performance: Performance[];
    recentTrades: Trade[];
    onReset: () => void;
}

export const HUD = ({ status, performance, recentTrades, onReset }: HUDProps) => {
    const totalPnL = performance.reduce((acc, curr) => acc + curr.total_pnl, 0);
    const totalTrades = performance.reduce((acc, curr) => acc + curr.n_trades, 0);

    return (
        <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            padding: '32px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            color: '#1f2937'
        }}>
            {/* Top Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', pointerEvents: 'auto', alignItems: 'flex-start' }}>
                {/* Brand & Status Card */}
                <div style={{ 
                    background: 'rgba(255, 255, 255, 0.85)', 
                    padding: '24px', 
                    borderRadius: '24px', 
                    boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                    backdropFilter: 'blur(12px)',
                    border: '1px solid rgba(255,255,255,0.6)',
                    minWidth: '240px'
                }}>
                    <h1 style={{ margin: '0 0 16px 0', fontSize: '20px', fontWeight: '800', letterSpacing: '-0.03em', color: '#111' }}>
                        QuantPM <span style={{ color: '#3b82f6' }}>Live</span>
                    </h1>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ 
                                width: '8px', height: '8px', borderRadius: '50%', 
                                background: status.is_running ? '#22c55e' : '#ef4444',
                                boxShadow: status.is_running ? '0 0 12px rgba(34, 197, 94, 0.6)' : 'none'
                            }} />
                            <span style={{ fontSize: '13px', fontWeight: '600', color: '#374151', letterSpacing: '0.02em' }}>
                                {status.is_running ? 'SYSTEM ACTIVE' : 'SYSTEM STOPPED'}
                            </span>
                        </div>
                        <div style={{ fontSize: '13px', color: '#6b7280', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                            T+{(status.elapsed / 3600).toFixed(4)}h
                        </div>
                    </div>
                </div>

                {/* Performance Card */}
                <div style={{ 
                    background: 'rgba(255, 255, 255, 0.85)', 
                    padding: '24px', 
                    borderRadius: '24px', 
                    boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                    textAlign: 'right',
                    backdropFilter: 'blur(12px)',
                    border: '1px solid rgba(255,255,255,0.6)',
                    minWidth: '200px'
                }}>
                    <div style={{ fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
                        Net Profit / Loss
                    </div>
                    <div style={{ 
                        fontSize: '32px', 
                        fontWeight: '800', 
                        color: totalPnL >= 0 ? '#059669' : '#dc2626',
                        fontVariantNumeric: 'tabular-nums',
                        letterSpacing: '-0.02em'
                    }}>
                        {totalPnL >= 0 ? '+' : ''}${Math.abs(totalPnL).toFixed(2)}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '12px', marginTop: '12px' }}>
                        <span style={{ fontSize: '13px', color: '#6b7280', fontWeight: '500' }}>
                            {totalTrades} trades
                        </span>
                        <button 
                            onClick={onReset}
                            style={{
                                background: '#fee2e2',
                                color: '#991b1b',
                                border: 'none',
                                padding: '6px 12px',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                fontSize: '11px',
                                fontWeight: '700',
                                textTransform: 'uppercase',
                                letterSpacing: '0.05em',
                                transition: 'all 0.2s'
                            }}
                            onMouseOver={(e) => {
                                e.currentTarget.style.background = '#fecaca';
                                e.currentTarget.style.transform = 'translateY(-1px)';
                            }}
                            onMouseOut={(e) => {
                                e.currentTarget.style.background = '#fee2e2';
                                e.currentTarget.style.transform = 'translateY(0)';
                            }}
                        >
                            Reset
                        </button>
                    </div>
                </div>
            </div>

            {/* Bottom Bar - Recent Trades */}
            <div style={{ 
                background: 'rgba(255, 255, 255, 0.85)', 
                padding: '24px', 
                borderRadius: '24px', 
                boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                maxHeight: '300px',
                overflowY: 'auto',
                pointerEvents: 'auto',
                width: '380px',
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(255,255,255,0.6)'
            }}>
                <h3 style={{ margin: '0 0 20px 0', fontSize: '14px', fontWeight: '700', color: '#111', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Live Feed
                </h3>
                {recentTrades.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '13px', textAlign: 'center', padding: '32px 0', fontStyle: 'italic' }}>
                        Waiting for market activity...
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {recentTrades.slice(0, 10).map((trade, i) => (
                            <div key={i} style={{ 
                                display: 'flex', 
                                justifyContent: 'space-between', 
                                alignItems: 'center',
                                paddingBottom: '16px',
                                borderBottom: i < recentTrades.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none'
                            }}>
                                <div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                        <span style={{ 
                                            fontSize: '10px', 
                                            fontWeight: '800', 
                                            padding: '3px 8px', 
                                            borderRadius: '12px',
                                            background: trade.side === 'buy' ? '#dcfce7' : '#fee2e2',
                                            color: trade.side === 'buy' ? '#15803d' : '#b91c1c',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.05em'
                                        }}>
                                            {trade.side}
                                        </span>
                                        <span style={{ fontSize: '13px', fontWeight: '600', color: '#374151' }}>
                                            {trade.strategy_name}
                                        </span>
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#6b7280', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                                        @ ${trade.entry_price.toFixed(3)}
                                    </div>
                                </div>
                                <div style={{ 
                                    fontWeight: '700', 
                                    fontSize: '14px',
                                    color: trade.pnl >= 0 ? '#059669' : '#dc2626',
                                    fontVariantNumeric: 'tabular-nums'
                                }}>
                                    {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
