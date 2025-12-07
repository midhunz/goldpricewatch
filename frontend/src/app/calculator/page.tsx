"use client";

import { useState, useEffect, useMemo } from "react";
import { useGoldRates } from "@/hooks/useGoldRates";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Calculator, RefreshCcw } from "lucide-react";

export default function CalculatorPage() {
    const { data: rates, isLoading } = useGoldRates();

    // State
    const [selectedRegion, setSelectedRegion] = useState<string>("");
    const [selectedPurity, setSelectedPurity] = useState<string>("");
    const [weight, setWeight] = useState<number>(10);
    const [stoneWeight, setStoneWeight] = useState<number>(0);
    const [makingChargesPercent, setMakingChargesPercent] = useState<number>(10);
    const [taxPercent, setTaxPercent] = useState<number>(5);

    // Derived Data
    const regions = useMemo(() => {
        if (!rates) return [];
        return Array.from(new Set(rates.map(r => r.region)));
    }, [rates]);

    const availablePurities = useMemo(() => {
        if (!rates || !selectedRegion) return [];
        return rates
            .filter(r => r.region === selectedRegion)
            .map(r => r.purity);
    }, [rates, selectedRegion]);

    const currentRate = useMemo(() => {
        if (!rates || !selectedRegion || !selectedPurity) return null;
        return rates.find(r => r.region === selectedRegion && r.purity === selectedPurity);
    }, [rates, selectedRegion, selectedPurity]);

    // Set defaults when data loads
    useEffect(() => {
        if (regions.length > 0 && !selectedRegion) {
            setSelectedRegion("India"); // Default to India
        }
    }, [regions]);

    useEffect(() => {
        if (availablePurities.length > 0) {
            // Default to 22K if available, else first option
            const defaultPurity = availablePurities.find(p => p.includes("22")) || availablePurities[0];
            setSelectedPurity(defaultPurity);
        }
    }, [availablePurities]);

    // Helper to parse price string
    const parsePrice = (priceStr: string) => {
        if (!priceStr) return 0;
        let clean = priceStr;
        if (priceStr.includes("₹")) {
            clean = priceStr.split("₹")[0];
        }
        clean = clean.replace(/[^0-9.]/g, "");
        return parseFloat(clean) || 0;
    };

    // Calculation
    const ratePerGram = currentRate ? parsePrice(currentRate.price) : 0;
    const netWeight = Math.max(0, weight - stoneWeight);
    const goldCost = ratePerGram * netWeight;

    // Making charges usually on gross weight gold value
    const grossGoldValue = ratePerGram * weight;
    const makingChargesAmount = grossGoldValue * (makingChargesPercent / 100);

    const subTotal = goldCost + makingChargesAmount;
    const taxAmount = subTotal * (taxPercent / 100);
    const totalCost = subTotal + taxAmount;
    const currency = currentRate?.currency || "";

    if (isLoading) {
        return (
            <div className="container py-20 flex justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
            </div>
        );
    }

    return (
        <div className="container mx-auto py-10 px-4 max-w-5xl">
            <div className="flex flex-col items-center text-center space-y-4 mb-10">
                <h1 className="text-4xl font-bold tracking-tight flex items-center gap-2">
                    <Calculator className="h-8 w-8 text-yellow-500" />
                    Gold Price Calculator
                </h1>
                <p className="text-muted-foreground max-w-2xl">
                    Estimate the final price of your jewelry by adding making charges and taxes to the live gold rate.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Input Section */}
                <Card className="border-yellow-500/20 bg-card/50 backdrop-blur">
                    <CardHeader>
                        <CardTitle>Enter Details</CardTitle>
                        <CardDescription>Configure your purchase details below.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="space-y-2">
                            <Label>Region</Label>
                            <Select value={selectedRegion} onValueChange={setSelectedRegion}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select Region" />
                                </SelectTrigger>
                                <SelectContent>
                                    {regions.map(region => (
                                        <SelectItem key={region} value={region}>{region}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label>Purity</Label>
                            <Select value={selectedPurity} onValueChange={setSelectedPurity}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select Purity" />
                                </SelectTrigger>
                                <SelectContent>
                                    {availablePurities.map(purity => (
                                        <SelectItem key={purity} value={purity}>{purity}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Gross Weight (g)</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    value={weight}
                                    onChange={(e) => setWeight(parseFloat(e.target.value) || 0)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Stone Weight (g)</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    value={stoneWeight}
                                    onChange={(e) => setStoneWeight(parseFloat(e.target.value) || 0)}
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Making Charges (%)</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    value={makingChargesPercent}
                                    onChange={(e) => setMakingChargesPercent(parseFloat(e.target.value) || 0)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Tax / VAT (%)</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    value={taxPercent}
                                    onChange={(e) => setTaxPercent(parseFloat(e.target.value) || 0)}
                                />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Summary Section */}
                <Card className="border-yellow-500 bg-yellow-500/5 backdrop-blur h-fit">
                    <CardHeader>
                        <CardTitle className="flex items-center justify-between">
                            <span>Price Breakdown</span>
                            <span className="text-xs font-normal text-muted-foreground bg-background/50 px-2 py-1 rounded-full">
                                Live Rate: {currency} {ratePerGram.toLocaleString()} /g
                            </span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Net Gold Weight</span>
                                <span className="font-medium">{netWeight.toFixed(2)} g</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Gold Price ({netWeight}g)</span>
                                <span className="font-medium">{currency} {goldCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Making Charges ({makingChargesPercent}%)</span>
                                <span className="font-medium text-red-500">+{currency} {makingChargesAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between text-sm border-b pb-3">
                                <span className="text-muted-foreground">Tax ({taxPercent}%)</span>
                                <span className="font-medium text-red-500">+{currency} {taxAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between items-end pt-2">
                                <span className="font-bold text-lg">Total Estimate</span>
                                <span className="font-bold text-3xl text-yellow-500">
                                    {currency} {totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                            </div>
                        </div>

                        <div className="bg-background/50 p-4 rounded-lg text-xs text-muted-foreground">
                            <p>
                                <strong>Note:</strong> This is an estimate based on the current live gold rate.
                                Final prices at jewelry stores may vary depending on the design complexity (making charges)
                                and specific store policies.
                            </p>
                        </div>

                        <Button className="w-full bg-yellow-500 hover:bg-yellow-600 text-black font-bold" onClick={() => window.print()}>
                            Print Estimate
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
