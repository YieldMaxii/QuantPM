import { useMemo } from 'react';

interface PriceChartProps {
    data: { timestamp: string; price: number }[];
    width?: number;
    height?: number;
    color?: string;
}

export const PriceChart = ({ data, width = 300, height = 150, color = '#3b82f6' }: PriceChartProps) => {
    const points = useMemo(() => {
        if (data.length < 2) return '';

        const maxPrice = Math.max(...data.map(d => d.price));
        const minPrice = Math.min(...data.map(d => d.price));
        const range = maxPrice - minPrice || 1;

        return data.map((d, i) => {
            const x = (i / (data.length - 1)) * width;
            // Invert Y because SVG 0 is top
            const y = height - ((d.price - minPrice) / range) * height;
            return `${x},${y}`;
        }).join(' ');
    }, [data, width, height]);

    if (data.length === 0) return null;

    return (
        <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ overflow: 'visible' }}>
            {/* Gradient Definition */}
            <defs>
                <linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity="0.2" />
                    <stop offset="100%" stopColor={color} stopOpacity="0" />
                </linearGradient>
            </defs>

            {/* Area Fill */}
            <path
                d={`M 0,${height} ${points} L ${width},${height} Z`}
                fill="url(#chartGradient)"
                stroke="none"
            />

            {/* Line */}
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
};

