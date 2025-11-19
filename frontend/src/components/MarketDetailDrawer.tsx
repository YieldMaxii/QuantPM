import type { Market } from '../models';

interface MarketDetailDrawerProps {
    market: Market | null;
    onClose: () => void;
    history?: { timestamp: string; price: number }[];
}

export const MarketDetailDrawer = ({ market, onClose, history = [] }: MarketDetailDrawerProps) => {
    if (!market) return null;

    return (
        <div style={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: '400px',
            height: '100%',
            background: 'rgba(255, 255, 255, 0.9)',
            backdropFilter: 'blur(20px)',
            boxShadow: '-10px 0 30px rgba(0,0,0,0.1)',
            padding: '32px',
            transform: market ? 'translateX(0)' : 'translateX(100%)',
            transition: 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            pointerEvents: 'auto',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1000,
            borderLeft: '1px solid rgba(255,255,255,0.5)'
        }}>
            {/* Header */}
            <div style={{ marginBottom: '24px' }}>
                <button 
                    onClick={onClose}
                    style={{
                        background: 'none',
                        border: 'none',
                        fontSize: '24px',
                        cursor: 'pointer',
                        padding: '0',
                        marginBottom: '16px',
                        color: '#6b7280'
                    }}
                >
                    ←
                </button>
                <h2 style={{ 
                    margin: 0, 
                    fontSize: '20px', 
                    fontWeight: '800', 
                    color: '#111',
                    lineHeight: '1.3'
                }}>
                    {market.name}
                </h2>
                <div style={{ 
                    marginTop: '8px',
                    fontSize: '14px',
                    color: '#6b7280',
                    fontFamily: 'monospace'
                }}>
                    ID: {market.market_id}
                </div>
            </div>

            {/* Current Stats */}
            <div style={{ 
                display: 'grid', 
                gridTemplateColumns: '1fr 1fr', 
                gap: '16px',
                marginBottom: '32px'
            }}>
                <div style={{ 
                    background: 'rgba(255,255,255,0.5)', 
                    padding: '16px', 
                    borderRadius: '12px',
                    border: '1px solid rgba(0,0,0,0.05)'
                }}>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>Probability</div>
                    <div style={{ fontSize: '24px', fontWeight: '800', color: '#111' }}>
                        {(market.outcome * 100).toFixed(1)}%
                    </div>
                </div>
                <div style={{ 
                    background: 'rgba(255,255,255,0.5)', 
                    padding: '16px', 
                    borderRadius: '12px',
                    border: '1px solid rgba(0,0,0,0.05)'
                }}>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>Volume</div>
                    <div style={{ fontSize: '24px', fontWeight: '800', color: '#111' }}>
                        --
                    </div>
                </div>
            </div>

            {/* Chart Placeholder */}
            <div style={{ flex: 1, minHeight: '200px', background: 'rgba(0,0,0,0.02)', borderRadius: '16px', padding: '16px' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#4b5563' }}>Price History</h3>
                {history.length > 0 ? (
                    <div style={{ width: '100%', height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {/* Chart will go here */}
                        Chart Component
                    </div>
                ) : (
                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: '13px' }}>
                        No history available
                    </div>
                )}
            </div>
        </div>
    );
};

