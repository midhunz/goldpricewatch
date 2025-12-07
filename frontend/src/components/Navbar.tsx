import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Coins, Menu } from "lucide-react";

export default function Navbar() {
  return (
    <nav className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-bold text-xl tracking-tight">
          <Coins className="h-6 w-6 text-yellow-500" />
          <span className="bg-gradient-to-r from-yellow-600 to-yellow-400 bg-clip-text text-transparent">
            GoldPrice<span className="text-foreground">Watch</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">
            Dashboard
          </Link>
          <Link href="/trends" className="hover:text-foreground transition-colors">
            Trends
          </Link>
          <Link href="/calculator" className="hover:text-foreground transition-colors">
            Calculator
          </Link>
          <Link href="/gold-news-today" className="hover:text-foreground transition-colors">
            News
          </Link>
        </div>

        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" className="hidden md:flex">
            Sign In
          </Button>
          <Button size="sm" className="bg-yellow-500 hover:bg-yellow-600 text-black font-semibold">
            Get App
          </Button>
          <Button variant="ghost" size="icon" className="md:hidden">
            <Menu className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </nav>
  );
}
