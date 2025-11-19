export interface Market {
    market_id: string;
    name: string;
    outcome: number;
    event_slug?: string;
    slug?: string;
    last_updated?: string;
}

export interface EventGroup {
    event_slug: string;
    name: string; // Derived from slug or first market
    markets: Market[];
}

// Trade interface for live feed
export interface Trade {
    strategy_name: string;
    market_id: string;
    entry_time: string;
    side: string;
    entry_price: number;
    size: number;
    pnl: number;
    capital_at_entry: number;
}

export interface SystemStatus {
    is_running: boolean;
    start_time?: string;
    elapsed: number;
}

export interface Performance {
    strategy_name: string;
    total_pnl: number;
    n_trades: number;
}
