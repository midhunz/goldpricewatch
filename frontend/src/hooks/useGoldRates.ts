import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface GoldRate {
    region: string;
    purity: string;
    price: string;
    currency: string;
    change?: number;
    change_percent?: number;
    updated_at?: string;
}

export function useGoldRates() {
    return useQuery({
        queryKey: ["goldRates"],
        queryFn: async () => {
            const { data } = await axios.get<GoldRate[]>(`${API_URL}/api/rates`);
            return data;
        },
    });
}
