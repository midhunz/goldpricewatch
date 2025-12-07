"use client";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import GoldRateCard from "@/components/GoldRateCard";
import { ArrowRight, TrendingUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useGoldRates } from "@/hooks/useGoldRates";
import { useState, useRef } from "react";

export default function Home() {
  const { data: rates, isLoading, error } = useGoldRates();

  const indiaRates = rates?.filter((r) => r.region === "India") || [];
  const middleEastRates = rates?.filter((r) => r.region !== "India") || [];

  // Helper to parse price string to number for change calculation (mock change for now)
  const parsePrice = (priceStr: string) => {
    let clean = priceStr;
    // Handle India format: "12,791₹127,910/ 10g" - take the first part (per gram)
    if (priceStr.includes("₹")) {
      clean = priceStr.split("₹")[0];
    }
    clean = clean.replace(/[^0-9.]/g, "");
    return parseFloat(clean) || 0;
  };

  const [activeTab, setActiveTab] = useState("middle-east");
  const tabsRef = useRef<HTMLDivElement>(null);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    // Auto-scroll to tabs section with a slight offset
    if (tabsRef.current) {
      const yOffset = -20;
      const y = tabsRef.current.getBoundingClientRect().top + window.pageYOffset + yOffset;
      window.scrollTo({ top: y, behavior: 'smooth' });
    }
  };

  const countryFlags: Record<string, string> = {
    "India": "🇮🇳",
    "UAE": "🇦🇪",
    "Oman": "🇴🇲",
    "Qatar": "🇶🇦",
    "Saudi Arabia": "🇸🇦",
    "Bahrain": "🇧🇭",
    "Kuwait": "🇰🇼",
  };

  // Get last updated time from the first rate (assuming all are from same batch)
  const lastUpdated = rates && rates.length > 0 && rates[0].updated_at
    ? new Date(rates[0].updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null;

  return (
    <div className="container mx-auto py-8 px-4 space-y-10">
      {/* Hero Section */}
      <section className="text-center space-y-4 py-10">
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tighter bg-gradient-to-b from-foreground to-muted-foreground bg-clip-text text-transparent">
          Live Gold Prices <br />
          <span className="text-yellow-500">India & Middle East</span>
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          Track real-time gold prices, analyze historical trends, and calculate the value of your jewelry with precision.
        </p>
        <div className="flex justify-center gap-4 pt-4">
          <Button size="lg" className="bg-yellow-500 hover:bg-yellow-600 text-black font-semibold">
            Check Rates
          </Button>
          <Button size="lg" variant="outline">
            View Trends <TrendingUp className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </section>

      {/* Live Rates Section */}
      <section className="space-y-8" ref={tabsRef}>
        <div className="flex flex-col items-center justify-center space-y-2">
          <h2 className="text-3xl font-bold tracking-tight">Today's Rates</h2>
          <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/50 px-3 py-1 rounded-full">
            <span>Source: Gulf News</span>
            {lastUpdated && (
              <>
                <span>•</span>
                <span>Updated: {lastUpdated}</span>
              </>
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
          </div>
        ) : error ? (
          <div className="text-center py-10 text-red-500">
            Failed to load rates. Please try again later.
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
            <div className="flex justify-center mb-8">
              <TabsList className="grid w-full max-w-md grid-cols-2 h-12 p-1 rounded-full bg-muted/50 backdrop-blur border">
                <TabsTrigger
                  value="middle-east"
                  className="rounded-full text-base data-[state=active]:bg-yellow-500 data-[state=active]:text-black transition-all duration-300"
                >
                  🌍 Middle East
                </TabsTrigger>
                <TabsTrigger
                  value="india"
                  className="rounded-full text-base data-[state=active]:bg-yellow-500 data-[state=active]:text-black transition-all duration-300"
                >
                  🇮🇳 India
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="india" className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {indiaRates.map((rate, index) => {
                  let displayContent: React.ReactNode = null;

                  if (rate.region === "India" && rate.price.includes("₹")) {
                    const parts = rate.price.split("₹");
                    const perGram = parts[0].trim();
                    const per10Gram = parts[1] ? "₹" + parts[1].trim() : "";

                    displayContent = (
                      <div className="flex flex-col">
                        <span className="text-2xl font-bold">{rate.currency} {perGram} <span className="text-xs font-normal text-muted-foreground">/g</span></span>
                        {per10Gram && <span className="text-xs text-muted-foreground font-normal">{per10Gram}</span>}
                      </div>
                    );
                  } else {
                    displayContent = <span>{rate.currency} {rate.price}</span>;
                  }

                  return (
                    <GoldRateCard
                      key={index}
                      region={rate.region}
                      purity={rate.purity}
                      price={parsePrice(rate.price)}
                      currency={rate.currency}
                      change={rate.change || 0}
                      changePercent={rate.change_percent || 0}
                      displayPrice={displayContent}
                    />
                  );
                })}
              </div>
            </TabsContent>

            <TabsContent value="middle-east" className="space-y-8">
              {Object.entries(
                middleEastRates.reduce((acc, rate) => {
                  if (!acc[rate.region]) acc[rate.region] = [];
                  acc[rate.region].push(rate);
                  return acc;
                }, {} as Record<string, typeof middleEastRates>)
              ).map(([region, regionRates]) => (
                <div key={region} className="space-y-4">
                  <h3 className="text-xl font-bold text-yellow-500 border-b border-yellow-500/20 pb-2 flex items-center gap-2">
                    <span className="text-2xl">{countryFlags[region] || "🌍"}</span> {region}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {regionRates.map((rate, index) => (
                      <GoldRateCard
                        key={index}
                        region={rate.region}
                        purity={rate.purity}
                        price={parsePrice(rate.price)}
                        currency={rate.currency}
                        change={rate.change || 0}
                        changePercent={rate.change_percent || 0}
                        displayPrice={<span>{rate.currency} {rate.price}</span>}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </TabsContent>
          </Tabs>
        )}
      </section>

      {/* Features Grid */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 py-8">
        <div className="p-6 rounded-xl border bg-card/50 backdrop-blur hover:border-yellow-500/50 transition-colors">
          <h3 className="text-xl font-bold mb-2">Historical Trends</h3>
          <p className="text-muted-foreground mb-4">Analyze price movements over the last week, month, or year to make informed decisions.</p>
          <Link href="/trends" className="text-yellow-500 hover:underline flex items-center text-sm font-medium">
            Explore Charts <ArrowRight className="ml-1 h-4 w-4" />
          </Link>
        </div>
        <div className="p-6 rounded-xl border bg-card/50 backdrop-blur hover:border-yellow-500/50 transition-colors">
          <h3 className="text-xl font-bold mb-2">Gold Calculator</h3>
          <p className="text-muted-foreground mb-4">Calculate the exact price of your jewelry including making charges and taxes.</p>
          <Link href="/calculator" className="text-yellow-500 hover:underline flex items-center text-sm font-medium">
            Calculate Now <ArrowRight className="ml-1 h-4 w-4" />
          </Link>
        </div>
        <div className="p-6 rounded-xl border bg-card/50 backdrop-blur hover:border-yellow-500/50 transition-colors">
          <h3 className="text-xl font-bold mb-2">Price Alerts</h3>
          <p className="text-muted-foreground mb-4">Set target prices and get notified instantly when gold rates drop.</p>
          <Link href="#" className="text-yellow-500 hover:underline flex items-center text-sm font-medium">
            Set Alert <ArrowRight className="ml-1 h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
