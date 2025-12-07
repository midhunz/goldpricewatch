import { Coins } from "lucide-react";

export default function Footer() {
    return (
        <footer className="border-t bg-muted/40">
            <div className="container mx-auto py-10 px-4">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 font-bold text-lg">
                            <Coins className="h-5 w-5 text-yellow-500" />
                            <span>GoldPriceWatch</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Real-time gold rates for India and the Middle East. Trusted by thousands of investors.
                        </p>
                    </div>

                    <div>
                        <h3 className="font-semibold mb-3">Platform</h3>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><a href="#" className="hover:text-foreground">Live Rates</a></li>
                            <li><a href="#" className="hover:text-foreground">Historical Data</a></li>
                            <li><a href="#" className="hover:text-foreground">Calculator</a></li>
                        </ul>
                    </div>

                    <div>
                        <h3 className="font-semibold mb-3">Company</h3>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><a href="#" className="hover:text-foreground">About Us</a></li>
                            <li><a href="#" className="hover:text-foreground">Contact</a></li>
                            <li><a href="#" className="hover:text-foreground">Privacy Policy</a></li>
                        </ul>
                    </div>

                    <div>
                        <h3 className="font-semibold mb-3">Connect</h3>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><a href="#" className="hover:text-foreground">Twitter</a></li>
                            <li><a href="#" className="hover:text-foreground">Instagram</a></li>
                            <li><a href="#" className="hover:text-foreground">LinkedIn</a></li>
                        </ul>
                    </div>
                </div>
                <div className="mt-10 pt-6 border-t text-center text-sm text-muted-foreground">
                    © {new Date().getFullYear()} GoldPriceWatch. All rights reserved.
                </div>
            </div>
        </footer>
    );
}
