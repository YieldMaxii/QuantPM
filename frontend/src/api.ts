import axios from 'axios';
import type { Market, Trade, SystemStatus, Performance } from './models';

const API_URL = 'http://localhost:8000/api';

export const fetchMarkets = async (): Promise<Market[]> => {
    const response = await axios.get(`${API_URL}/markets`);
    return response.data;
};

export const fetchTrades = async (): Promise<Trade[]> => {
    const response = await axios.get(`${API_URL}/trades`);
    return response.data;
};

export const fetchStatus = async (): Promise<SystemStatus> => {
    const response = await axios.get(`${API_URL}/status`);
    return response.data;
};

export const fetchPerformance = async (): Promise<Performance[]> => {
    const response = await axios.get(`${API_URL}/performance`);
    return response.data;
};

export const resetSystem = async (): Promise<void> => {
    await axios.post(`${API_URL}/control/reset`);
};

