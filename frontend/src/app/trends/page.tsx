"use client";

import { useState, useEffect, useMemo } from "react";
import { useGoldRates } from "@/hooks/useGoldRates";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, TrendingUp, Calendar } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend
} from "recharts";

interface HistoryPoint {
    timestamp: string;
    price: number;
    currency: string;
}

interface RegionData {
    region: string;
    data: HistoryPoint[];
    color: string;
}

// Color mapping for regions
const REGION_COLORS: Record<string, string> = {
    "India": "#22c55e",      // Green
    "UAE": "#3b82f6",        // Blue
    "Saudi Arabia": "#eab308", // Yellow
    "Qatar": "#a855f7",      // Purple
    "Oman": "#f97316",       // Orange
    "Bahrain": "#ec4899",    // Pink
    "Kuwait": "#14b8a6",     // Teal
};

export default function TrendsPage() {
    const { data: currentRates, isLoading: isLoadingRates } = useGoldRates();

    // State
    const [selectedRegions, setSelectedRegions] = useState<string[]>(["India"]);
    const [selectedPurity, setSelectedPurity] = useState<string>("");
    const [duration, setDuration] = useState<string>("7"); // days
    const [regionDataList, setRegionDataList] = useState<RegionData[]>([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

    // Derived Options
    const regions = useMemo(() => {
        if (!currentRates) return [];
        return Array.from(new Set(currentRates.map(r => r.region)));
    }, [currentRates]);

    const availablePurities = useMemo(() => {
        if (!currentRates) return [];
        // Get purities that exist across all selected regions
        const puritySets = selectedRegions.map(region =>
            new Set(currentRates.filter(r => r.region === region).map(r => r.purity))
        );
        if (puritySets.length === 0) return [];

        // Find common purities
        const commonPurities = Array.from(puritySets[0]).filter(purity =>
            puritySets.every(set => set.has(purity))
        );

        return commonPurities;
    }, [currentRates, selectedRegions]);

    // Set defaults
    useEffect(() => {
        if (regions.length > 0 && selectedRegions.length === 0) {
            setSelectedRegions(["India"]);
        }
    }, [regions]);

    useEffect(() => {
        if (availablePurities.length > 0) {
            if (!selectedPurity || !availablePurities.includes(selectedPurity)) {
                const defaultPurity = availablePurities.find(p => p.includes("22")) || availablePurities[0];
                setSelectedPurity(defaultPurity);
            }
        }
    }, [availablePurities]);

    // Fetch History for all selected regions
    useEffect(() => {
        async function fetchHistory() {
            if (selectedRegions.length === 0 || !selectedPurity) return;

            setIsLoadingHistory(true);
            try {
                const promises = selectedRegions.map(async (region) => {
                    const res = await fetch(
                        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/rates/history?region=${encodeURIComponent(region)}&purity=${encodeURIComponent(selectedPurity)}&days=${duration}`
                    );
                    if (res.ok) {
                        const data = await res.json();
                        return {
                            region,
                            data,
                            color: REGION_COLORS[region] || "#888888"
                        };
                    }
                    return null;
                });

                const results = await Promise.all(promises);
                setRegionDataList(results.filter(r => r !== null) as RegionData[]);
            } catch (error) {
                console.error("Failed to fetch history", error);
            } finally {
                setIsLoadingHistory(false);
            }
        }

        fetchHistory();
    }, [selectedRegions, selectedPurity, duration]);

    // Merge chart data
    const chartData = useMemo(() => {
        if (regionDataList.length === 0) return [];

        // Get all unique timestamps
        const timestampSet = new Set<string>();
        regionDataList.forEach(rd => {
            rd.data.forEach(point => timestampSet.add(point.timestamp));
        });

        const timestamps = Array.from(timestampSet).sort();

        // Build chart data
        return timestamps.map(timestamp => {
            const point: any = {
                timestamp,
                date: new Date(timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
                fullDate: new Date(timestamp).toLocaleString()
            };

            regionDataList.forEach(rd => {
                const dataPoint = rd.data.find(p => p.timestamp === timestamp);
                if (dataPoint) {
                    point[rd.region] = dataPoint.price;
                }
            });

            return point;
        });
    }, [regionDataList]);

    // Toggle region selection
    const toggleRegion = (region: string) => {
        setSelectedRegions(prev => {
            if (prev.includes(region)) {
                return prev.filter(r => r !== region);
            } else {
                return [...prev, region];
            }
        });
    };

    if (isLoadingRates) {
        return (
            <div className="container py-20 flex justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
            </div>
        );
    }

    return (
        <div className="container mx-auto py-10 px-4 max-w-6xl">
            <div className="flex flex-col items-center text-center space-y-4 mb-10">
                <h1 className="text-4xl font-bold tracking-tight flex items-center gap-2">
                    <TrendingUp className="h-8 w-8 text-yellow-500" />
                    Historical Price Trends
                </h1>
                <p className="text-muted-foreground max-w-2xl">
                    Compare gold price movements across countries to find the best buying opportunities.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                {/* Controls Sidebar */}
                <div className="lg:col-span-1 space-y-6">
                    <Card className="border-yellow-500/20 bg-card/50 backdrop-blur">
                        <CardHeader>
                            <CardTitle className="text-lg">Configuration</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Countries (Select Multiple)</label>
                                <div className="space-y-2">
                                    {regions.map(region => (
                                        <div key={region} className="flex items-center space-x-2">
                                            <Checkbox
                                                id={region}
                                                checked={selectedRegions.includes(region)}
                                                onCheckedChange={() => toggleRegion(region)}
                                            />
                                            <Label
                                                htmlFor={region}
                                                className="text-sm font-normal cursor-pointer flex items-center gap-2"
                                            >
                                                <span
                                                    className="w-3 h-3 rounded-full"
                                                    style={{ backgroundColor: REGION_COLORS[region] || "#888" }}
                                                />
                                                {region}
                                            </Label>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium">Purity</label>
                                <Select value={selectedPurity} onValueChange={setSelectedPurity}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Purity" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {availablePurities.map(p => (
                                            <SelectItem key={p} value={p}>{p}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium">Duration</label>
                                <Tabs value={duration} onValueChange={setDuration} className="w-full">
                                    <TabsList className="grid w-full grid-cols-3">
                                        <TabsTrigger value="7">1W</TabsTrigger>
                                        <TabsTrigger value="30">1M</TabsTrigger>
                                        <TabsTrigger value="90">3M</TabsTrigger>
                                    </TabsList>
                                </Tabs>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Chart Area */}
                <div className="lg:col-span-3">
                    <Card className="h-[500px] border-yellow-500/20 bg-card/50 backdrop-blur flex flex-col">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                {selectedPurity} Gold Price Comparison
                                <span className="text-sm font-normal text-muted-foreground ml-auto flex items-center gap-1">
                                    <Calendar className="h-4 w-4" /> Last {duration} Days
                                </span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="flex-1 min-h-0">
                            {isLoadingHistory ? (
                                <div className="h-full flex items-center justify-center">
                                    <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
                                </div>
                            ) : chartData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                        <XAxis
                                            dataKey="date"
                                            stroke="#666"
                                            tick={{ fill: '#888', fontSize: 12 }}
                                            tickMargin={10}
                                        />
                                        <YAxis
                                            stroke="#666"
                                            tick={{ fill: '#888', fontSize: 12 }}
                                            domain={['auto', 'auto']}
                                            tickFormatter={(value) => `${value.toLocaleString()}`}
                                        />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#1a1a1a', borderColor: '#333', borderRadius: '8px' }}
                                            labelStyle={{ color: '#888', marginBottom: '4px' }}
                                            labelFormatter={(label, payload) => {
                                                if (payload && payload.length > 0) {
                                                    return payload[0].payload.fullDate;
                                                }
                                                return label;
                                            }}
                                        />
                                        <Legend />
                                        {regionDataList.map(rd => (
                                            <Line
                                                key={rd.region}
                                                type="monotone"
                                                dataKey={rd.region}
                                                stroke={rd.color}
                                                strokeWidth={2}
                                                dot={false}
                                                name={rd.region}
                                            />
                                        ))}
                                    </LineChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                                    <TrendingUp className="h-12 w-12 mb-4 opacity-20" />
                                    <p>No historical data available for this selection yet.</p>
                                    <p className="text-sm mt-2">Data collection started recently.</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
