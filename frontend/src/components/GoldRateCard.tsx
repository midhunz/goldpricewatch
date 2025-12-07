import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";

interface GoldRateCardProps {
    region: string;
    purity: string;
    price: number;
    currency: string;
    change: number;
    changePercent?: number;
    displayPrice?: React.ReactNode;
}

export default function GoldRateCard({ region, purity, price, currency, change, changePercent, displayPrice }: GoldRateCardProps) {
    const isPositive = change > 0;
    const isNeutral = change === 0;

    return (
        <Card className="hover:shadow-lg transition-shadow border-yellow-500/20 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                    {region} ({purity})
                </CardTitle>
                {isPositive ? (
                    <ArrowUp className="h-4 w-4 text-green-500" />
                ) : isNeutral ? (
                    <Minus className="h-4 w-4 text-gray-500" />
                ) : (
                    <ArrowDown className="h-4 w-4 text-red-500" />
                )}
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">
                    {displayPrice ? (
                        displayPrice
                    ) : (
                        <span>{currency} {price.toLocaleString()}</span>
                    )}
                </div>
                <div className={`text-xs flex items-center mt-1 font-medium ${isPositive ? "text-green-500" : isNeutral ? "text-gray-500" : "text-red-500"
                    }`}>
                    {isPositive ? "+" : ""}{change} {currency}
                    {changePercent !== undefined && (
                        <span className="ml-1 opacity-80">
                            ({isPositive ? "+" : ""}{changePercent}%)
                        </span>
                    )}
                    <span className="ml-1 text-muted-foreground font-normal">vs yesterday</span>
                </div>
            </CardContent>
        </Card>
    );
}
